"""Independent Gate 12 adversarial cases; all evidence and sentinels fictitious."""
from dataclasses import replace
from fractions import Fraction
from importlib.resources import files
import io
import json
import os
from pathlib import Path
import traceback

import pytest

from mimic.frequencies import FrequencyDataset, FrequencyError, FrequencyRegistry, Measurement
from mimic.frequencies.models import PATTERN_IDS, FrequencyRecord, dataset_bytes
from mimic.frequencies.registry import load_dataset


def fixture():
    with files('mimic.data.frequencies').joinpath('synthetic-a.json').open('rb') as stream:
        return load_dataset(stream)


def test_conflicting_link_race_has_no_foreign_sensitive_exception(tmp_path, monkeypatch):
    registry = FrequencyRegistry(tmp_path)
    original = os.link
    a = fixture(); b = replace(a, source=replace(a.source, title='Different synthetic evidence'))
    def winner(*args, **kwargs):
        with monkeypatch.context() as patch:
            patch.setattr(os, 'link', original)
            registry.import_dataset(b)
        raise FileExistsError('Gate12-Fictitious-PrivateFilesystemMarker')
    monkeypatch.setattr(os, 'link', winner)
    with pytest.raises(FrequencyError) as caught:
        registry.import_dataset(a)
    assert caught.value.code == 'conflict'
    assert caught.value.__context__ is None
    assert 'Gate12-Fictitious-PrivateFilesystemMarker' not in ''.join(traceback.format_exception(caught.value))
    assert registry.get(a.identity) == b
    assert len(list(registry.root.iterdir())) == 1


@pytest.mark.parametrize('primitive', ['link', 'scandir'], ids=['no-link','no-fd-scan'])
def test_unsupported_posix_primitive_is_fixed_and_cleans_stage(tmp_path, monkeypatch, primitive):
    registry = FrequencyRegistry(tmp_path); registry.import_dataset(fixture())
    def unavailable(*args, **kwargs):
        raise NotImplementedError('Gate12-Fictitious-PrivateFilesystemMarker')
    monkeypatch.setattr(os, primitive, unavailable)
    with pytest.raises(FrequencyError) as caught:
        if primitive == 'link': registry.import_dataset(replace(fixture(), dataset_id='another'))
        else: registry.list()
    assert caught.value.__context__ is None
    assert 'Gate12-Fictitious-PrivateFilesystemMarker' not in ''.join(traceback.format_exception(caught.value))
    monkeypatch.undo()
    assert not any(p.name.startswith('.import-') for p in registry.root.iterdir())


def test_standalone_ratio_refuses_incompatible_denominator():
    row = fixture().patterns[0]  # 30 observed; using another sample of 5 is invalid.
    with pytest.raises(FrequencyError):
        row.ratio(Measurement(5, 'observations', '15.1.0'))


def test_stream_setup_error_is_fixed_and_closes_owned_descriptor(tmp_path, monkeypatch):
    from mimic.frequencies.registry import load_dataset_file
    path = tmp_path / 'synthetic.json'; path.write_bytes(dataset_bytes(fixture()))
    original_open = os.open; descriptors = []
    def track(*args, **kwargs):
        descriptor = original_open(*args, **kwargs); descriptors.append(descriptor); return descriptor
    def failed(*args, **kwargs): raise OSError('Gate12-Fictitious-PrivateFilesystemMarker')
    monkeypatch.setattr(os, 'open', track); monkeypatch.setattr(os, 'fdopen', failed)
    with pytest.raises(FrequencyError) as caught: load_dataset_file(path)
    assert caught.value.__context__ is None
    assert 'Gate12-Fictitious-PrivateFilesystemMarker' not in ''.join(traceback.format_exception(caught.value))
    assert len(descriptors) == 1
    with pytest.raises(OSError): os.fstat(descriptors[0])


@pytest.mark.parametrize('unit', ['observations', 'unique-passwords'])
def test_hand_calculated_counts_zero_unknown_and_maximum(unit):
    from mimic.frequencies.models import MAX_COUNT
    d = fixture()
    d = replace(d, measurement=replace(d.measurement, sample_size=7, sample_unit=unit),
                patterns=(FrequencyRecord(PATTERN_IDS[0], 5), FrequencyRecord(PATTERN_IDS[1], 0)))
    assert d.patterns[0].ratio(d.measurement) == Fraction(5, 7)
    assert d.evidence()['frequencies'] == [dict(id=PATTERN_IDS[0], numerator=5, denominator=7),
                                           dict(id=PATTERN_IDS[1], numerator=0, denominator=7)]
    assert sum(p.count for p in d.patterns) == 5  # Remaining 2 are unspecified, never renormalized.
    assert d.measurement.sample_unit == unit
    boundary = replace(d, measurement=replace(d.measurement, sample_size=MAX_COUNT),
                       patterns=(FrequencyRecord(PATTERN_IDS[0], MAX_COUNT),))
    assert boundary.patterns[0].ratio(boundary.measurement) == 1
    with pytest.raises(FrequencyError): replace(boundary, patterns=boundary.patterns + (FrequencyRecord(PATTERN_IDS[1], 5),))


@pytest.mark.parametrize('change', ['count', 'denominator', 'license', 'source', 'version', 'period', 'limitations'])
def test_material_changes_change_content_digest(change):
    d = fixture()
    variants = dict(count=lambda: replace(d, patterns=(replace(d.patterns[0], count=31),)+d.patterns[1:]),
        denominator=lambda: replace(d, measurement=replace(d.measurement, sample_size=101)),
        license=lambda: replace(d, source=replace(d.source, license='CC-BY-4.0')),
        source=lambda: replace(d, source=replace(d.source, title='Another fictitious source')),
        version=lambda: replace(d, dataset_version='2'),
        period=lambda: replace(d, source=replace(d.source, collection_start='2026-01-01')),
        limitations=lambda: replace(d, source=replace(d.source, limitations=('Another limitation',))))
    assert variants[change]().sha256 != d.sha256


def test_canonical_equivalence_escaping_and_unicode_spelling():
    d = replace(fixture(), source=replace(fixture().source, title='Ação Café'))
    data = d.to_dict(); data['patterns'].reverse(); data = dict(reversed(list(data.items())))
    for escaped in (False, True):
        for indent in (None, 4):
            variant = load_dataset(io.BytesIO(json.dumps(data, ensure_ascii=escaped, indent=indent).encode()))
            assert dataset_bytes(variant) == dataset_bytes(d) and variant.sha256 == d.sha256
    # No normalization contract: different code points are different evidence.
    decomposed = replace(d, source=replace(d.source, title='Ac\u0327a\u0303o Cafe\u0301'))
    assert decomposed.sha256 != d.sha256


@pytest.mark.parametrize('value', ['grammar_version', 'extractor_version'])
def test_incompatible_grammar_and_extractor_are_refused_at_import(value):
    data = fixture().to_dict(); data['measurement'][value] = 'future-v2'
    with pytest.raises(FrequencyError): load_dataset(io.BytesIO(json.dumps(data).encode()))


@pytest.mark.parametrize('tail', [b'\xef\xbb\xbf', b'junk', b'\x00', b'[]'], ids=['bom','text','nul','array'])
def test_complete_json_prefix_cannot_hide_invalid_tail(tail):
    with pytest.raises(FrequencyError): load_dataset(io.BytesIO(dataset_bytes(fixture()) + tail))


@pytest.mark.parametrize('count', [0, 1, 4, 5, 6], ids=['empty','one','four','five','six'])
def test_bridge_threshold_denominator_and_versions(count):
    from mimic.application.observations import PatternAnalysisService
    from mimic.frequencies.models import from_observation
    report = PatternAnalysisService().analyze(io.BytesIO(b'GateFictionalValue2026\n' * count), authorized=True,
                                             reference_year=2026, min_occurrences=1)
    options = dict(dataset_id='gate-bridge', dataset_version='1', source=fixture().source, metadata_non_sensitive=True)
    if count < 5:
        with pytest.raises(FrequencyError): from_observation(report, **options)
    else:
        d = from_observation(report, **options)
        assert d.patterns[0].count == d.measurement.sample_size == count
        assert d.measurement.min_occurrences == 5 and d.measurement.year_max == 2026
        assert d.measurement.unicode_version == report.unicode_version
        assert d.measurement.grammar_version == report.grammar_version and d.measurement.extractor_version == report.extractor_version
        assert 'GateFictionalValue' not in dataset_bytes(d).decode()


def test_bridge_never_recovers_originally_suppressed_family_and_validates_report():
    from mimic.application.observations import ObservationError, PatternAnalysisService
    from mimic.frequencies.models import from_observation
    report = PatternAnalysisService().analyze(io.BytesIO(b'GateFictionalWord\n' * 6 + b'TI!\n' * 8),
                                             authorized=True, min_occurrences=7)
    options = dict(dataset_id='gate-bridge', dataset_version='1', source=fixture().source, metadata_non_sensitive=True)
    d = from_observation(report, **options)
    assert d.measurement.sample_size == 14 and d.measurement.min_occurrences == 7
    assert [(p.id, p.count) for p in d.patterns] == [('observed-pattern.acronym-special.v1', 8)]
    with pytest.raises(ObservationError): from_observation(replace(report, sample_size=15), **options)


def test_residual_complementary_disclosure_is_not_anonymity():
    from mimic.application.observations import PatternAnalysisService
    from mimic.frequencies.models import from_observation
    values = ('Fictional', 'Fictional!', 'Fictional2026', 'Fictional7777', 'Fictional_2026', 'Fictional_7777',
              'TI', 'TI!', 'TI2026', 'TI7777', 'TI_2026', 'TI_7777')
    raw = ''.join((value+'\n')*(5 if i < 11 else 4) for i,value in enumerate(values)).encode()
    report = PatternAnalysisService().analyze(io.BytesIO(raw), authorized=True)
    assert report.unmatched_count == 0 and report.suppressed_count == 4
    d = from_observation(report, dataset_id='gate-complement', dataset_version='1', source=fixture().source, metadata_non_sensitive=True)
    assert len(d.patterns) == 11 and d.measurement.sample_size - sum(p.count for p in d.patterns) == 4
    assert PATTERN_IDS[-1] not in dataset_bytes(d).decode()
    # Knowing externally that every observation matched permits inferring the last family.
    assert 'not anonymity' in ' '.join(d.evidence()['warnings'])


def test_overlap_scope_period_methodology_and_exact_differences():
    from mimic.frequencies.comparison import compare
    a = replace(fixture(), patterns=(FrequencyRecord(PATTERN_IDS[0], 5),FrequencyRecord(PATTERN_IDS[1], 0)),
                measurement=replace(fixture().measurement, sample_size=7))
    b = replace(a, dataset_id='gate-b', patterns=(FrequencyRecord(PATTERN_IDS[0], 6),),
                measurement=replace(a.measurement, sample_size=10),
                source=replace(a.source, population='Different population', methodology='Another method',
                               collection_start='2026-01-01', collection_end='2026-02-01'))
    comparison = compare(a,b)
    assert comparison['patterns'][0]['right_minus_left'] == dict(numerator=-4,denominator=35)
    assert comparison['patterns'][1]['left'] == dict(numerator=0,denominator=7)
    assert comparison['patterns'][1]['right'] is None and comparison['patterns'][1]['right_minus_left'] is None
    assert {'population','methodology','collection_start','collection_end'} <= set(comparison['sampling_differences'])
    assert comparison['population_comparability'] == 'different-declared-scopes'
    assert 'Shared sample identifier' in ' '.join(comparison['warnings'])
    other = replace(b, source=replace(b.source, sample_id='different-id', population=None))
    result = compare(a,other)
    assert result['population_comparability'] == 'unknown' and 'population' in result['unknown_sampling_fields']
    assert 'do not prove independence' in ' '.join(result['warnings'])


def test_fixed_evaluation_hits_and_counterexample_to_improvement():
    from mimic.frequencies.evaluation import evaluate
    d = fixture(); result = evaluate(d)
    assert [(r['baseline_hits'],r['experimental_hits']) for r in result['coverage']] == [(2,2),(5,8),(8,8),(12,12)]
    assert result['coverage'][1]['experimental'] == dict(numerator=2,denominator=3)
    tied = replace(d, patterns=tuple(FrequencyRecord(pid, 5) for pid in PATTERN_IDS))
    assert evaluate(tied)['baseline'] == evaluate(tied)['experimental']
    # Holdout has zero mass on all odd slots. Ranking one first makes the method worse.
    adverse = replace(d, patterns=(FrequencyRecord(PATTERN_IDS[1], 100),))
    assert evaluate(adverse)['coverage'][0]['experimental_hits'] == 0
    assert evaluate(adverse)['coverage'][0]['baseline_hits'] == 2


def test_external_digest_detects_self_consistent_replacement_and_object_stays_immutable(tmp_path):
    r = FrequencyRegistry(tmp_path); original = fixture(); r.import_dataset(original)
    snapshot = r.get(original.identity); encoded = dataset_bytes(snapshot)
    changed = replace(original, source=replace(original.source, title='Different declared evidence'))
    path = r.root/(original.identity+'.json'); envelope = json.loads(path.read_bytes())
    envelope['dataset'] = changed.to_dict(); envelope['sha256'] = changed.sha256; path.write_text(json.dumps(envelope))
    assert r.get(original.identity) == changed  # A checksum is not authentication.
    with pytest.raises(FrequencyError): r.get(original.identity, expected_digest=original.sha256)
    assert dataset_bytes(snapshot) == encoded
    path.unlink(); assert dataset_bytes(snapshot) == encoded


def test_publication_parent_substitution_uses_pinned_directory(tmp_path, monkeypatch):
    r = FrequencyRegistry(tmp_path/'data'); r.root.mkdir(parents=True)
    outsider = tmp_path/'outside'; outsider.mkdir(); pinned = tmp_path/'data'/'pinned'
    original = os.link
    def swap(*args, **kwargs):
        r.root.rename(pinned); r.root.symlink_to(outsider)
        return original(*args, **kwargs)
    monkeypatch.setattr(os,'link',swap)
    r.import_dataset(fixture())
    assert not list(outsider.iterdir())
    assert [p.name for p in pinned.iterdir()] == [fixture().identity+'.json']


def test_registry_entry_ceiling_and_idempotency_at_the_limit(tmp_path):
    r=FrequencyRegistry(tmp_path); d=fixture(); r.import_dataset(d)
    for i in range(127): (r.root/f'.import-abandoned-{i}').touch()
    assert r.list() == (d,) and r.import_dataset(d) == d
    with pytest.raises(FrequencyError): r.import_dataset(replace(d,dataset_id='new'))
    (r.root/'.import-overflow').touch()
    with pytest.raises(FrequencyError): r.list()


def test_publication_stream_setup_failure_closes_stage_descriptor(tmp_path, monkeypatch):
    r=FrequencyRegistry(tmp_path); d=fixture(); original=os.open; descriptors=[]
    def track(path,*args,**kwargs):
        fd=original(path,*args,**kwargs)
        if str(path).startswith('.import-'): descriptors.append(fd)
        return fd
    def failed(*args,**kwargs): raise OSError('Gate12-Fictitious-PrivateFilesystemMarker')
    monkeypatch.setattr(os,'open',track);monkeypatch.setattr(os,'fdopen',failed)
    with pytest.raises(FrequencyError) as caught:r.import_dataset(d)
    assert caught.value.code=='write' and caught.value.__context__ is None
    assert len(descriptors)==1 and not list(r.root.iterdir())
    with pytest.raises(OSError):os.fstat(descriptors[0])


def test_real_cli_help_missing_example_name_and_sanitized_arguments(tmp_path):
    import subprocess,sys
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
    for argv,code in [(['--help'],0),(['example'],2),*[( [name,'--help'],0) for name in ('import','list','show','verify','compare','evaluate')],
                      (['example','Gate12-Fictitious-PrivateArgument'],2)]:
        result=subprocess.run([sys.executable,'-B','-c','from mimic.cli import main;raise SystemExit(main())','frequencies',*argv],
                              cwd=Path.cwd(),env=env,capture_output=True,text=True)
        assert result.returncode==code
        assert 'Gate12-Fictitious-PrivateArgument' not in result.stdout+result.stderr
        assert 'Traceback' not in result.stderr


def test_canonical_size_failure_does_not_create_registry(tmp_path):
    # Input fits 32 KiB, canonical ASCII escaping does not; publication must refuse.
    d=fixture(); prose='測'*512
    source=replace(d.source,title=prose,methodology=prose,attribution=prose,limitations=(prose,)*8,
                   population=prose,geography=prose,sector=prose,coverage_evidence=prose)
    d=replace(d,source=source)
    encoded=json.dumps(d.to_dict(),ensure_ascii=False,separators=(',',':')).encode()
    assert len(encoded)<32768
    loaded=load_dataset(io.BytesIO(encoded));r=FrequencyRegistry(tmp_path)
    with pytest.raises(FrequencyError):r.import_dataset(loaded)
    assert not r.root.exists()


@pytest.mark.parametrize('cause', ['fdopen','scandir'], ids=['stream-setup','fd-scan'])
def test_web_filesystem_failures_are_422_without_marker_log(tmp_path,monkeypatch,caplog,cause):
    from fastapi.testclient import TestClient
    from mimic.api import create_app
    r=FrequencyRegistry(tmp_path);r.import_dataset(fixture())
    with TestClient(create_app(data_dir=tmp_path),raise_server_exceptions=False) as client:
        original=getattr(os,cause)
        def failed(*args,**kwargs):
            if cause=='fdopen' and len(args)>1 and args[1]=='rb':
                raise OSError('Gate12-Fictitious-PrivateFilesystemMarker')
            if cause=='scandir' and isinstance(args[0],int):
                raise NotImplementedError('Gate12-Fictitious-PrivateFilesystemMarker')
            return original(*args,**kwargs)
        monkeypatch.setattr(os,cause,failed)
        response=client.get('/frequencies/'+fixture().identity)
        assert response.status_code==422 and response.headers['Cache-Control']=='no-store'
        assert 'Gate12-Fictitious-PrivateFilesystemMarker' not in response.text+caplog.text
        assert client.get('/api/jobs').json()==[]


@pytest.mark.parametrize('locale',['pt-BR','en'])
def test_zero_absence_suppression_cli_and_web(tmp_path,capsys,locale):
    from fastapi.testclient import TestClient
    from mimic.api import create_app
    from mimic.cli import main
    from mimic.web.i18n import translate
    d=replace(fixture(),patterns=(FrequencyRecord(PATTERN_IDS[0],5),FrequencyRecord(PATTERN_IDS[1],0)))
    r=FrequencyRegistry(tmp_path);r.import_dataset(d)
    assert main(['frequencies','--data-dir',str(tmp_path),'show',d.identity])==0
    evidence=json.loads(capsys.readouterr().out)
    assert evidence['frequencies'][1]['numerator']==0 and evidence['frequencies'][1]['denominator']==100
    assert all(row['id']!=PATTERN_IDS[2] for row in evidence['frequencies'])
    with TestClient(create_app(data_dir=tmp_path)) as client:
        client.cookies.set('mimic_locale',locale)
        response=client.get('/frequencies/'+d.identity)
        assert '0/100' in response.text and PATTERN_IDS[1] in response.text
        assert PATTERN_IDS[2] not in response.text and translate(locale,'frequency.missing') in response.text
        # Missing may be undeclared or suppressed; no per-family cause is invented.
        assert not (tmp_path/'uploads').exists() and client.get('/api/jobs').json()==[]


def test_knowledge_never_enters_api_job_snapshot_or_restart_download(tmp_path):
    from fastapi.testclient import TestClient
    from mimic.api import create_app
    from mimic.application import GenerationRequest,GenerationService,MutationOptions,RankingOptions
    from mimic.core.candidate import Candidate,Origin
    d=replace(fixture(),source=replace(fixture().source,title='Gate12-Fictitious-AggregateEvidenceOnly'))
    FrequencyRegistry(tmp_path).import_dataset(d)
    request=GenerationRequest(base_candidates=(Candidate('Fictitious',(Origin('manual','name','Fictitious'),)),),
                              mutations=MutationOptions('none',False,'_'),ranking=RankingOptions(True,5))
    expected=''.join(result.candidate.value+'\n' for result in GenerationService().prepare(request).iter_results()).encode()
    app=create_app(data_dir=tmp_path)
    with TestClient(app) as client:
        assert client.get('/frequencies/'+d.identity).status_code==200
        response=client.post('/api/jobs',json=dict(request=request.to_dict()));assert response.status_code==201
        job_id=response.json()['id'];assert app.state.job_manager.wait(job_id)['status']=='completed'
        record=client.get('/api/jobs/'+job_id).json()
        encoded=json.dumps(record)
        assert 'AggregateEvidenceOnly' not in encoded and 'frequency-knowledge' not in encoded
        assert client.get('/api/jobs/'+job_id+'/download').content==expected
    with TestClient(create_app(data_dir=tmp_path)) as client:
        assert client.get('/api/jobs/'+job_id+'/download').content==expected


def test_gate_hashseed_ties_missing_unicode_and_complete_evidence():
    import subprocess,sys
    code='''import json
from dataclasses import replace
from tests.test_gate12_audit import fixture
from mimic.frequencies.models import FrequencyRecord,PATTERN_IDS,dataset_bytes
from mimic.frequencies.comparison import compare
from mimic.frequencies.evaluation import evaluate
a=fixture(); a=replace(a,source=replace(a.source,title="Ação synthetic"),patterns=(FrequencyRecord(PATTERN_IDS[0],5),FrequencyRecord(PATTERN_IDS[2],5),FrequencyRecord(PATTERN_IDS[1],0)))
b=replace(a,dataset_id="other",measurement=replace(a.measurement,sample_size=101))
print(dataset_bytes(a).hex(),a.sha256)
print(json.dumps(dict(comparison=compare(a,b),evaluation=evaluate(a)),sort_keys=True))
'''
    results=[subprocess.check_output([sys.executable,'-B','-c',code],env=dict(os.environ,PYTHONHASHSEED=seed,PYTHONDONTWRITEBYTECODE='1')) for seed in ('1','42','777')]
    assert results[0]==results[1]==results[2]


def test_schema_declares_the_actual_bounded_contract():
    from mimic.frequencies.models import MAX_COUNT
    schema=json.loads(files('mimic.data.frequencies').joinpath('frequency-knowledge-v1.schema.json').read_text())
    props=schema['properties']; actual=fixture().to_dict()
    assert set(schema['required'])==set(actual)==set(props)
    assert props['patterns']['maxItems']==12
    assert tuple(props['patterns']['items']['properties']['id']['enum'])==PATTERN_IDS
    assert props['patterns']['items']['properties']['count']['maximum']==MAX_COUNT
    assert props['measurement']['properties']['sample_size']['minimum']==5
    assert set(props['measurement']['required'])==set(actual['measurement'])
    assert set(props['source']['required'])=={'title','category','methodology','attribution','license',
                                              'local_use_authorized','redistribution','limitations','sample_id'}
    assert 'strict duplicate keys' in schema['$comment'] and 'count >= min_occurrences' in schema['$comment']
