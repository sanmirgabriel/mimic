"""Small synthetic aggregate regressions, no credential corpora."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
from fractions import Fraction
from importlib.resources import files
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

import pytest

from mimic.cli import main
from mimic.frequencies import FrequencyDataset, FrequencyError, FrequencyRegistry
from mimic.frequencies.comparison import compare
from mimic.frequencies.evaluation import evaluate, FIXTURE_ID, HOLDOUT, UNIVERSE
from mimic.frequencies.models import (MAX_BYTES, PATTERN_IDS, dataset_bytes, from_observation)
from mimic.frequencies.registry import load_dataset, load_dataset_file


def example(name='synthetic-a'):
    with files('mimic.data.frequencies').joinpath(name + '.json').open('rb') as stream:
        return load_dataset(stream)


def test_exact_counts_canonical_order_identity_and_immutable_provenance():
    d = example()
    assert d.identity == 'synthetic-a@1'
    assert d.patterns[0].ratio(d.measurement) == Fraction(3, 10)
    assert d.evidence()['frequencies'][0] == dict(id=PATTERN_IDS[0], numerator=30, denominator=100)
    assert d.source.attribution == 'MIMIC synthetic examples'
    assert d.source.collection_start is None and d.source.geography is None
    assert FrequencyDataset.from_dict(d.to_dict()) == d
    assert dataset_bytes(replace(d, patterns=tuple(reversed(d.patterns)))) == dataset_bytes(d)
    with pytest.raises(FrozenInstanceError): d.source.title = 'changed'
    assert len(d.sha256) == 64 and replace(d, source=replace(d.source, title='Another source')).sha256 != d.sha256


BAD_FIELDS = [
    ('schema_version', 'future'), ('schema_version', None), ('unexpected', 'PrivateSentinel'),
    ('metadata_non_sensitive', False), ('dataset_id', '../outside'), ('dataset_version', 'a/b'),
    ('measurement.sample_size', -1), ('measurement.sample_size', 0), ('measurement.sample_size', True),
    ('measurement.sample_size', 2**63), ('measurement.sample_size', 1.5),
    ('measurement.sample_unit', 'users'), ('measurement.grammar_version', 'future'),
    ('measurement.extractor_version', 'other'), ('measurement.unicode_version', 'unknown'),
    ('measurement.year_max', 1899), ('measurement.year_max', 10000),
    ('measurement.min_occurrences', 1), ('measurement.min_occurrences', True),
    ('source.title', ''), ('source.attribution', ''), ('source.methodology', ''),
    ('source.category', 'leaked-plaintext'), ('source.local_use_authorized', False),
    ('source.license', 'invented-license'), ('source.license', 'NOASSERTION'),
    ('source.redistribution', 'yes'), ('source.population', 'x\x00PrivateSentinel'),
    ('source.geography', 'Unsupported region'), ('source.sample_id', '../private'),
    ('source.title', 'x' * 513), ('source.title', 'line\u2028PrivateSentinel'),
    ('source.title', 'rtl\u202ePrivateSentinel'), ('source.limitations', []),
    ('source.limitations', ['ok'] * 9), ('source.limitations', ['']),
    ('source.collection_start', '2026-02-30'), ('source.collection_start', True),
    ('source.reference_url', 'http://example.test'), ('source.reference_url', 'https://@example.test'),
    ('source.reference_url', 'https://bad..host/'), ('source.reference_url', 'https://host:65536/'),
    ('source.reference_url', 'https://host:bad/'), ('source.reference_url', 'https://host/%0aPrivateSentinel'),
    ('source.reference_url', 'https://host\\evil/'), ('source.reference_url', 'https://host/<script>'),
    ('source.reference_url', 'https://host/ space'), ('source.reference_url', 'https://host/%xx'),
]


@pytest.mark.parametrize('field,value', BAD_FIELDS, ids=[f'field-{i:02}' for i in range(len(BAD_FIELDS))])
def test_invalid_schema_never_reflects_rejected_metadata(field, value):
    data = example().to_dict()
    parent = data
    names = field.split('.')
    for key in names[:-1]: parent = parent[key]
    parent[names[-1]] = value
    with pytest.raises(FrequencyError) as caught:
        FrequencyDataset.from_dict(data)
    assert 'PrivateSentinel' not in str(caught.value)
    assert caught.value.__context__ is None


@pytest.mark.parametrize('field', ['source', 'patterns', 'metadata_non_sensitive', 'schema_version',
                                 'source.title', 'source.attribution', 'source.methodology', 'source.license',
                                 'measurement.grammar_version', 'measurement.sample_unit', 'measurement.unicode_version'])
def test_required_fields(field):
    data = example().to_dict(); keys = field.split('.')
    parent = data if len(keys) == 1 else data[keys[0]]
    del parent[keys[-1]]
    with pytest.raises(FrequencyError): FrequencyDataset.from_dict(data)


@pytest.mark.parametrize('mode', ['duplicate', 'unknown', 'negative', 'boolean', 'overflow', 'exceeds', 'sum', 'small'])
def test_record_counts_and_exclusive_partitions(mode):
    data = example().to_dict()
    if mode == 'duplicate': data['patterns'].append(data['patterns'][0])
    elif mode == 'unknown': data['patterns'][0]['id'] = 'WORD'
    elif mode == 'sum': data['patterns'][0]['count'] = 100
    else: data['patterns'][0]['count'] = {'negative':-1, 'boolean':True, 'overflow':2**63, 'exceeds':101, 'small':4}[mode]
    with pytest.raises(FrequencyError): FrequencyDataset.from_dict(data)


def test_unknown_license_local_use_and_redistribution_are_distinct():
    d = example()
    for license in ('NOASSERTION', 'LicenseRef-Local'):
        allowed = replace(d, source=replace(d.source, license=license, redistribution='unknown'))
        assert allowed.source.local_use_authorized
        with pytest.raises(FrequencyError): replace(allowed.source, redistribution='permitted')
    local = replace(d.source, license='CC-BY-4.0', redistribution='forbidden', reference_url='https://example.test/source')
    assert local.redistribution == 'forbidden'
    with pytest.raises(FrequencyError): replace(local, collection_start='2026-10-01', collection_end='2026-01-01')
    assert replace(local, geography='Synthetic region', coverage_evidence='Invented fixture scope').geography


@pytest.mark.parametrize('payload', [b'PrivateSentinel', b'{}garbage', b'[]', b'\xff', b'{"x":1,"x":2}',
    b'{"x":NaN}', b'[' * 2000 + b']' * 2000, b'x' * (MAX_BYTES + 1)],
    ids=['plaintext','trailing','array','utf8','duplicate-key','nan','depth','oversize'])
def test_bounded_malformed_json(payload):
    with pytest.raises(FrequencyError) as caught: load_dataset(io.BytesIO(payload))
    assert 'PrivateSentinel' not in str(caught.value) and caught.value.__context__ is None


@pytest.mark.parametrize('size', [1, 7, 97])
def test_short_reads_consume_through_eof_and_reject_trailing_bytes(size):
    class Short(io.BytesIO):
        def read(self, requested=-1): return super().read(min(size, requested))
    d = example(); payload = dataset_bytes(d)
    assert load_dataset(Short(payload)) == d
    for tail in (b'PrivateSentinel', b' ' * MAX_BYTES):
        with pytest.raises(FrequencyError): load_dataset(Short(payload + tail))


def test_reader_failure_sanitized_and_size_probe_bounded():
    class Broken:
        def read(self, size): raise OSError('PrivateSentinel')
    with pytest.raises(FrequencyError) as caught: load_dataset(Broken())
    assert caught.value.__context__ is None and 'PrivateSentinel' not in str(caught.value)
    stream = io.BytesIO(b'x' * (MAX_BYTES * 2))
    with pytest.raises(FrequencyError): load_dataset(stream)
    assert stream.tell() == MAX_BYTES + 1 and not stream.closed


def test_block11_bridge_preserves_denominator_and_never_unsuppresses():
    from mimic.application.observations import PatternAnalysisService
    report = PatternAnalysisService().analyze(io.BytesIO(b'Fictional\n' * 6 + b'TI!\n' * 4 + b'123\n'), authorized=True)
    d = from_observation(report, dataset_id='bridge', dataset_version='1', source=example().source, metadata_non_sensitive=True)
    assert d.measurement.sample_size == 11
    assert [(p.id, p.count) for p in d.patterns] == [(PATTERN_IDS[0], 6)]
    assert 'Fictional' not in dataset_bytes(d).decode()
    low = PatternAnalysisService().analyze(io.BytesIO(b'Fictional\n' * 6 + b'TI!\n'), authorized=True, min_occurrences=1)
    assert len(from_observation(low, dataset_id='bridge', dataset_version='1', source=d.source, metadata_non_sensitive=True).patterns) == 1


def test_registry_idempotency_conflict_digest_pin_and_missing(tmp_path):
    r = FrequencyRegistry(tmp_path); d = example()
    assert r.list() == () and not r.root.exists()
    assert r.import_dataset(d) == r.import_dataset(d) == r.get(d.identity) == r.verify(d.identity, expected_digest=d.sha256)
    assert r.list('methodology') == (d,) and r.list('not-present') == ()
    with pytest.raises(FrequencyError, match='different'): r.import_dataset(replace(d, source=replace(d.source, title='Other')))
    with pytest.raises(FrequencyError): r.verify(d.identity, expected_digest='0' * 64)
    assert [p.name for p in r.root.iterdir()] == [d.identity + '.json']
    path = r.root / (d.identity + '.json'); data = json.loads(path.read_bytes())
    data['dataset']['patterns'][0]['count'] = 31; path.write_text(json.dumps(data))
    with pytest.raises(FrequencyError, match='modified'): r.get(d.identity)
    with pytest.raises(FrequencyError): r.list()
    path.unlink()
    with pytest.raises(FrequencyError): r.get(d.identity)


@pytest.mark.parametrize('operation', ['fsync', 'link', 'open', 'interrupt'])
def test_failed_publication_is_clean_and_aggregate_only(tmp_path, monkeypatch, operation):
    r = FrequencyRegistry(tmp_path); d = example(); original = getattr(os, 'open')
    def broken(*args, **kwargs):
        if operation == 'interrupt': raise KeyboardInterrupt()
        raise OSError('PrivateSentinel')
    if operation == 'open':
        def fail_stage(path, *args, **kwargs):
            if str(path).startswith('.import-'): return broken()
            return original(path, *args, **kwargs)
        monkeypatch.setattr(os, 'open', fail_stage)
    else: monkeypatch.setattr(os, 'fsync' if operation == 'interrupt' else operation, broken)
    with pytest.raises(KeyboardInterrupt if operation == 'interrupt' else FrequencyError) as caught:
        r.import_dataset(d)
    assert not list(r.root.iterdir())
    assert 'PrivateSentinel' not in str(caught.value) and caught.value.__context__ is None


def test_partial_write_does_not_publish(tmp_path, monkeypatch):
    r = FrequencyRegistry(tmp_path); original = os.fdopen
    class ShortWriter:
        def __init__(self, fd): self.stream = original(fd, 'wb')
        def __enter__(self): return self
        def __exit__(self, *exc): self.stream.close()
        def write(self, payload): return self.stream.write(payload[:20])
    monkeypatch.setattr(os, 'fdopen', lambda fd, *args, **kwargs: ShortWriter(fd))
    with pytest.raises(FrequencyError): r.import_dataset(example())
    assert not list(r.root.iterdir())


@pytest.mark.parametrize('different', [False, True], ids=['idempotent','conflict'])
def test_concurrent_publication(tmp_path, monkeypatch, different):
    r = FrequencyRegistry(tmp_path); d = example(); barrier = threading.Barrier(2); original = os.link
    def synchronized(*args, **kwargs):
        barrier.wait(timeout=10)
        return original(*args, **kwargs)
    monkeypatch.setattr(os, 'link', synchronized)
    def publish(index):
        candidate = replace(d, source=replace(d.source, title='Other')) if different and index else d
        try: return r.import_dataset(candidate)
        except FrequencyError as exc: return exc.code
    with ThreadPoolExecutor(2) as pool: results = list(pool.map(publish, (0, 1)))
    assert sum(isinstance(v, FrequencyDataset) for v in results) == (1 if different else 2)
    assert len(list(r.root.iterdir())) == 1
    if different: assert 'conflict' in results


def test_symlink_and_path_confinement(tmp_path):
    r = FrequencyRegistry(tmp_path / 'data'); d = example(); r.import_dataset(d)
    outside = tmp_path / 'outside.json'; outside.write_bytes(dataset_bytes(d))
    link = tmp_path / 'link.json'; link.symlink_to(outside)
    with pytest.raises(FrequencyError): load_dataset_file(link)
    for identity in ('../outside@1', '/absolute@1', 'x@../1', 'x@1.json/other', 'x' * 65 + '@1'):
        with pytest.raises(FrequencyError): r.get(identity)
    entry = r.root / (d.identity + '.json'); saved = entry.read_bytes(); entry.unlink(); outside.write_bytes(saved); entry.symlink_to(outside)
    with pytest.raises(FrequencyError): r.get(d.identity)
    alternate = tmp_path / 'alternate'; alternate.mkdir(); (alternate / 'frequencies').symlink_to(r.root)
    with pytest.raises(FrequencyError): FrequencyRegistry(alternate).list()
    fifo = tmp_path / 'fifo'; os.mkfifo(fifo)
    with pytest.raises(FrequencyError): load_dataset_file(fifo)


def test_parent_substitution_reads_pinned_directory(tmp_path, monkeypatch):
    r = FrequencyRegistry(tmp_path); d = example(); r.import_dataset(d)
    outside = tmp_path / 'outside'; outside.mkdir()
    backup = tmp_path / 'pinned'; original = os.open
    def swap(path, *args, **kwargs):
        if path == d.identity + '.json':
            r.root.rename(backup); r.root.symlink_to(outside)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(os, 'open', swap)
    assert r.get(d.identity) == d


def test_registry_bounds_and_no_creation_for_invalid_import(tmp_path):
    r = FrequencyRegistry(tmp_path / 'root'); bad = tmp_path / 'input.json'; bad.write_bytes(b'PrivateSentinel')
    with pytest.raises(FrequencyError): r.import_file(bad)
    assert not r.root.exists()
    r.root.mkdir(parents=True)
    for index in range(129): (r.root / f'{index}.json').touch()
    with pytest.raises(FrequencyError, match='128'): r.list()
    with pytest.raises(FrequencyError): r.import_dataset(example())


def test_comparison_exact_differences_missing_scope_and_overlap():
    a = example(); b = example('synthetic-b'); result = compare(a, b)
    assert result['compatible'] and result['population_comparability'] == 'same-declared-scope'
    assert result['patterns'][0]['right_minus_left'] == dict(numerator=-1, denominator=10)
    assert result['patterns'][-1]['right_minus_left'] is None and result['patterns'][-1]['left'] is None
    assert result['left']['sha256'] == a.sha256
    assert 'Shared sample' in ' '.join(compare(a, a)['warnings'])
    assert compare(a, replace(b, source=replace(b.source, population=None)))['population_comparability'] == 'unknown'
    assert compare(a, replace(b, source=replace(b.source, population='Another scope')))['population_comparability'] == 'different-declared-scopes'


@pytest.mark.parametrize('field,value', [('sample_unit','unique-passwords'),('year_max',2026),('unicode_version','14.0.0')], ids=['unit','years','unicode'])
def test_incompatible_comparisons_never_compute_deltas(field, value):
    a = example(); b = replace(example('synthetic-b'), measurement=replace(a.measurement, **{field:value}))
    result = compare(a, b)
    assert result['incompatible_fields'] == [field] and not result['compatible']
    assert all(row['right_minus_left'] is None for row in result['patterns'])


def test_synthetic_holdout_is_frozen_separate_and_reproducible():
    a = example(); result = evaluate(a)
    assert result == evaluate(a)
    assert result['holdout']['identity'] != a.source.sample_id
    assert result['holdout']['universe'] == UNIVERSE and result['holdout']['holdout_slot_indices'] == HOLDOUT
    assert result['coverage'][0]['baseline_hits'] == 2
    assert result['coverage'][-1]['experimental_hits'] == len(HOLDOUT)
    assert result['reference']['sha256'] == a.sha256
    for source in (replace(a.source, sample_id=FIXTURE_ID), replace(a.source, category='authorized-local')):
        with pytest.raises(FrequencyError): evaluate(replace(a, source=source))
    with pytest.raises(FrequencyError): evaluate(replace(a, measurement=replace(a.measurement, year_max=2026)))
    assert example().sha256 == a.sha256


def test_cli_import_inspect_search_compare_verify_evaluate_and_errors(tmp_path, capsys):
    prefix = ['frequencies', '--data-dir', str(tmp_path / 'data')]
    assert main(prefix + ['example','synthetic-a']) == 0
    raw = capsys.readouterr().out; source = tmp_path / 'input.json'; source.write_text(raw)
    assert main(prefix + ['import', str(source)]) == 0
    output = json.loads(capsys.readouterr().out); digest = output['sha256']
    for command in ('show', 'verify', 'evaluate'):
        assert main(prefix + [command, 'synthetic-a@1', '--sha256', digest]) == 0
        assert digest in capsys.readouterr().out
    assert main(prefix + ['list','--query','WORD']) == 0
    assert json.loads(capsys.readouterr().out)  # searchable canonical IDs
    assert main(prefix + ['compare', 'synthetic-a@1', 'synthetic-a@1']) == 0
    assert json.loads(capsys.readouterr().out)['compatible']
    assert main(prefix + ['verify','synthetic-a@1','--sha256','wrong']) == 2
    capsys.readouterr()
    assert main(prefix + ['import', str(tmp_path / 'PrivateSentinel')]) == 2
    captured = capsys.readouterr(); assert 'PrivateSentinel' not in captured.err + captured.out
    with pytest.raises(SystemExit) as caught: main(prefix + ['PrivateSentinel'])
    assert caught.value.__context__ is None and caught.value.code == 2
    assert 'PrivateSentinel' not in capsys.readouterr().err


def test_hashseed_full_artifacts_comparison_and_evaluation():
    code = '''import json
from tests.test_frequencies import example
from mimic.frequencies.comparison import compare
from mimic.frequencies.evaluation import evaluate
from mimic.frequencies.models import dataset_bytes
a=example();b=example('synthetic-b')
print(a.sha256, dataset_bytes(a).hex())
print(json.dumps(dict(comparison=compare(a,b),evaluation=evaluate(a)),sort_keys=True))
'''
    outputs = [subprocess.check_output([sys.executable, '-B', '-c', code], env=dict(os.environ, PYTHONHASHSEED=seed, PYTHONDONTWRITEBYTECODE='1')) for seed in ('1','42','777')]
    assert outputs[0] == outputs[1] == outputs[2]


def test_packaged_schema_matches_canonical_evidence_and_never_fetches_urls(monkeypatch, tmp_path):
    import socket
    def forbidden(*args, **kwargs): raise AssertionError('network requested')
    monkeypatch.setattr(socket, 'socket', forbidden)
    schema = json.loads(files('mimic.data.frequencies').joinpath('frequency-knowledge-v1.schema.json').read_text())
    d = example(); encoded = d.to_dict()
    assert set(schema['properties']) == set(encoded)
    assert set(schema['properties']['measurement']['properties']) == set(encoded['measurement'])
    assert set(schema['properties']['source']['properties']) == set(encoded['source'])
    assert schema['additionalProperties'] is False
    r = FrequencyRegistry(tmp_path); r.import_dataset(d)
    assert r.get(d.identity) == d
    assert compare(d,d)['compatible'] and evaluate(d)['reference']['sha256'] == d.sha256


def test_frequency_registry_never_changes_generation_results_or_request_shape(tmp_path):
    from mimic.application import GenerationRequest, GenerationService, IntelligenceOptions, RankingOptions
    request = GenerationRequest(intelligence=IntelligenceOptions(reference_year=2026, service_profiles=('wordpress',)),
                                ranking=RankingOptions.from_budget('quick'))
    baseline = list(GenerationService().prepare(request).iter_results())
    r = FrequencyRegistry(tmp_path); r.import_dataset(example()); r.import_dataset(example('synthetic-b'))
    compare(*r.list()); evaluate(example())
    assert list(GenerationService().prepare(request).iter_results()) == baseline
    assert all(word not in json.dumps(request.to_dict()) for word in ('frequency', 'synthetic-a', 'sha256'))


def test_explicit_zero_is_evidence_and_missing_patterns_sort_last():
    d = example(); result = evaluate(d)
    zero_slot = UNIVERSE[5][0]; missing_slot = UNIVERSE[6][0]
    assert result['experimental'].index(zero_slot) < result['experimental'].index(missing_slot)
    assert compare(d, d)['patterns'][5]['left'] == dict(numerator=0, denominator=100)


def test_invalid_data_directory_has_no_sensitive_exception_chain():
    with pytest.raises(FrequencyError) as caught:
        FrequencyRegistry('PrivateSentinel\x00directory')
    assert caught.value.__context__ is None and 'PrivateSentinel' not in str(caught.value)
