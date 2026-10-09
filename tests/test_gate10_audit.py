"""Gate 10 regressions and adversarial checks using small, named fixtures."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, asdict, replace
import csv
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading

from fastapi.testclient import TestClient
import pytest

from mimic.api import create_app
from mimic.application import (GenerationRequest, GenerationService, IntelligenceOptions,
    SourceOptions, GenerationLimits, MutationOptions, RankingOptions)
from mimic.cli import main
from mimic.core.candidate import Candidate, Origin
from mimic.domain.models import Organization
from mimic.intelligence import catalog
from mimic.intelligence.builtins import SERVICE_PROFILES
from mimic.intelligence.planning import plan_intelligence
from mimic.web.i18n import TRANSLATIONS, translate


@pytest.mark.parametrize('change', [
    {'source_url': 'http://example.test/docs'},
    {'source_url': 'data:text/html,hello'},
    {'source_url': 'https://example.test:invalid/docs'},
    {'source_url': 'https://example.test:65536/docs'},
    {'source_url': 'https://@example.test/docs'},
    {'source_url': 'https://bad..host/docs'},
    {'source_url': 'https://bad<host>/docs'},
    {'password': 'pass\x00word'},
    {'password': 'pass\u0085word'},
    {'applicability': 'line\u2028break'},
    {'applicability': 'x' * 4097},
    {'catalog_version': 'not a version'},
    {'record_version': '-1'},
    {'record_version': '1.5'},
], ids=['http', 'data', 'port-text', 'port-range', 'empty-userinfo', 'host-labels',
        'host-punctuation', 'nul', 'c1', 'line-separator', 'oversize', 'catalog-version',
        'record-negative', 'record-fraction'])
def test_catalog_rejects_malformed_metadata(change):
    with pytest.raises((ValueError, TypeError)):
        replace(catalog.DEFAULT_CREDENTIALS[0], **change)


def test_all_catalog_models_bound_metadata_and_detach_mutable_inputs():
    for value, change in ((catalog.SERVICES[0], {'description': 'x' * 4097}),
                          (catalog.COMMON_VOCABULARY, {'description': 'x' * 4097}),
                          (catalog.COMMON_VOCABULARY, {'version': 'invalid version'}),
                          (catalog.COMMON_VOCABULARY, {'passwords': ()})):
        with pytest.raises(ValueError):
            replace(value, **change)
    refs = [['Title', 'https://example.test/docs']]
    aliases = ['fixture']
    service = replace(catalog.SERVICES[0], references=refs, aliases=aliases)
    refs[0][0] = 'changed'; aliases.append('changed')
    assert service.references == (('Title', 'https://example.test/docs'),)
    assert service.aliases == ('fixture',)
    decoded = service.to_dict(); decoded['references'] = []
    assert service.references
    with pytest.raises(FrozenInstanceError):
        service.references = ()


def test_common_values_keep_exact_spaces_and_unicode_without_normalization():
    values = [' pass ', 'senha🔑', 'café', 'cafe\u0301']
    vocabulary = replace(catalog.COMMON_VOCABULARY, passwords=values)
    values[0] = 'changed'
    assert vocabulary.passwords == (' pass ', 'senha🔑', 'café', 'cafe\u0301')
    assert type(vocabulary)(**json.loads(json.dumps(vocabulary.to_dict()))) == vocabulary
    for invalid in [('same', 'same'), ('   ',), ('bad\ud800',), ('bad\nvalue',)]:
        with pytest.raises(ValueError):
            replace(vocabulary, passwords=invalid)
    assert catalog.COMMON_VOCABULARY.version == 'common-v1'
    assert catalog.COMMON_VOCABULARY.usernames == ('admin', 'root', 'administrator', 'guest', 'support', 'test')
    assert catalog.COMMON_VOCABULARY.passwords == ('admin', 'password', 'changeme', 'welcome', '123456', 'mudar')


def test_catalog_rejects_unrelated_evidence_and_unsupported_catalog_versions():
    with pytest.raises(ValueError, match='evidence'):
        catalog.validate_catalog(credentials=(replace(catalog.DEFAULT_CREDENTIALS[0],
            source_url='https://example.test/unrelated'),))
    with pytest.raises(ValueError, match='version'):
        catalog.validate_catalog(services=(replace(catalog.SERVICES[0], catalog_version='service-catalog-v2'),))


def test_failed_export_leaves_no_partial_publication(tmp_path, monkeypatch, capsys):
    destination = tmp_path / 'export.csv'
    original = io.open
    class BrokenWriter:
        def __init__(self, stream): self.stream = stream
        def __enter__(self): return self
        def __exit__(self, *args): return self.stream.__exit__(*args)
        def write(self, value):
            self.stream.write(value[:10]); self.stream.flush()
            raise OSError('simulated disk full')
    def broken_open(*args, **kwargs):
        stream = original(*args, **kwargs)
        mode = args[1] if len(args) > 1 else kwargs.get('mode', 'r')
        return BrokenWriter(stream) if mode in ('x', 'w') else stream
    monkeypatch.setattr(io, 'open', broken_open)
    assert main(['credentials', 'export', '--output', str(destination)]) == 2
    assert 'simulated disk full' in capsys.readouterr().err
    assert not destination.exists()
    assert list(tmp_path.iterdir()) == []


def test_export_publication_failure_and_concurrent_destination_preserve_files(tmp_path, monkeypatch):
    destination = tmp_path / 'export.csv'
    def fail_publish(source, target):
        Path(target).write_text('operator content', encoding='utf-8')
        raise FileExistsError('concurrent destination')
    monkeypatch.setattr(os, 'link', fail_publish)
    assert main(['credentials', 'export', '--output', str(destination)]) == 2
    assert destination.read_text() == 'operator content'
    assert list(tmp_path.iterdir()) == [destination]


def test_export_symlinks_directories_and_missing_parent_are_safe(tmp_path):
    original = tmp_path / 'operator.csv'; original.write_bytes(b'operator content')
    link = tmp_path / 'link.csv'; link.symlink_to(original)
    dangling = tmp_path / 'dangling.csv'; dangling.symlink_to(tmp_path / 'absent.csv')
    directory = tmp_path / 'directory'; directory.mkdir()
    for destination in (link, dangling, directory, tmp_path / 'missing' / 'export.csv'):
        assert main(['credentials', 'export', '--output', str(destination)]) == 2
    assert original.read_bytes() == b'operator content'
    assert link.is_symlink() and dangling.is_symlink() and not (tmp_path / 'absent.csv').exists()
    assert not list(tmp_path.glob('.mimic-catalog-*'))


@pytest.mark.parametrize('prefix', ['=', '+', '-', '@', '  ='], ids=['equals', 'plus', 'minus', 'at', 'spaces'])
def test_csv_formula_representation_preserves_canonical_value(prefix):
    credential = replace(catalog.DEFAULT_CREDENTIALS[0], username=prefix + '1', password='á,"🔑"')
    row, = csv.DictReader(io.StringIO(catalog._credential_rows_csv((credential,))))
    assert credential.username == prefix + '1'
    assert row['username'] == "'" + credential.username and row['password'] == credential.password
    with pytest.raises(ValueError):
        replace(credential, password='line\nbreak')


def test_cli_search_and_errors_are_bounded_by_small_catalog(capsys):
    for query, count in [('', 7), (' GrAfAnA ', 1), ('AMQP', 1), ('🐇', 0), ('x' * 10000, 0)]:
        assert main(['services', 'list', '--search', query]) == 0
        assert len(capsys.readouterr().out.splitlines()) == count + 1
    assert main(['services', 'show', 'postgresql']) == 0
    assert 'No universal' not in capsys.readouterr().err
    assert main(['services', 'show', 'nonexistent']) == 1
    assert 'Traceback' not in capsys.readouterr().err
    for service in ('grafana', 'rabbitmq', 'wordpress'):
        assert main(['credentials', 'list', '--service', service]) == 0
        text = capsys.readouterr().out
        if service == 'wordpress': assert 'in this catalog' in text
        elif service == 'rabbitmq': assert 'localhost' in text and 'definitions' in text
        else: assert 'admin / admin' in text and 'password change' in text


@pytest.mark.parametrize('enabled', [False, True], ids=['intelligence-off', 'intelligence-on'])
def test_common_as_sole_source_with_default_and_explicit_intelligence(enabled, tmp_path):
    request = GenerationRequest(sources=SourceOptions(include_common_passwords=True),
        intelligence=IntelligenceOptions(enabled=enabled, reference_year=2026),
        mutations=MutationOptions('full', True, '!'))
    candidates = list(GenerationService().prepare(request).iter_candidates())
    assert [c.value for c in candidates] == list(catalog.COMMON_VOCABULARY.passwords)
    assert all(c.origins == (Origin('knowledge', 'common_password', c.value),) and not c.transformations for c in candidates)
    output = tmp_path / 'common.txt'
    assert main(['generate', '--include-common-passwords', '--reference-year', '2026', '--quiet', '-o', str(output)]) == 0
    assert output.read_text().splitlines() == list(catalog.COMMON_VOCABULARY.passwords)


def test_old_profiles_and_repeated_multiple_service_selection():
    expected = [
        ('wordpress', 'WordPress', ('WordPress', 'wp'), ('admin', 'editor')),
        ('mysql', 'MySQL', ('mysql', 'sql', 'db'), ('root', 'dba')),
        ('postgresql', 'PostgreSQL', ('postgresql', 'postgres', 'db'), ('postgres', 'dba')),
        ('mssql', 'Microsoft SQL Server', ('mssql', 'sql', 'db'), ('sa', 'dba')),
        ('windows-ad', 'Windows / Active Directory', ('windows', 'AD'), ('administrator', 'svc')),
    ]
    assert [(p.id, p.display_name, p.tokens, p.roles) for p in SERVICE_PROFILES[:5]] == expected
    assert all(p.version == 'knowledge-v1' for p in SERVICE_PROFILES[:5])
    options = IntelligenceOptions(reference_year=2026, corporate_roles=False,
        service_profiles=('grafana', 'rabbitmq', 'grafana'))
    assert options.service_profiles == ('grafana', 'rabbitmq')
    plan = plan_intelligence(options)
    assert len(plan.seeds) == 14
    fields = {o.field for seed in plan.seeds for o in seed.candidate.origins}
    assert all(f.startswith(('service.grafana.', 'service.rabbitmq.')) for f in fields)


def test_documented_common_and_generated_categories_never_gain_associations(monkeypatch):
    assert len(catalog.DEFAULT_CREDENTIALS) == 2
    assert [(c.service_id, c.username, c.password, c.type) for c in catalog.DEFAULT_CREDENTIALS] == [
        ('grafana', 'admin', 'admin', 'documented_default'),
        ('rabbitmq', 'guest', 'guest', 'documented_default')]
    assert not any(c.password == 'grafana123' for c in catalog.DEFAULT_CREDENTIALS)
    assert not catalog.list_credentials('postgresql')
    def forbidden(*args, **kwargs): raise AssertionError('pair consulted by engine')
    monkeypatch.setattr(catalog, 'list_credentials', forbidden)
    request = GenerationRequest(intelligence=IntelligenceOptions(reference_year=2026,
        corporate_roles=False, service_profiles=('grafana',)), limits=GenerationLimits(20),
        sources=SourceOptions(include_common_passwords=True))
    common = [c for c in GenerationService().prepare(request).iter_candidates()
              if any(o.field == 'common_password' for o in c.origins)]
    assert common and all(not c.transformations and len(c.origins) == 1 for c in common)


@pytest.mark.parametrize('common', [False, True], ids=['old-sources', 'common-sources'])
def test_api_job_roundtrip_persistence_preview_and_download(common, tmp_path):
    request = GenerationRequest(intelligence=IntelligenceOptions(reference_year=2026, service_profiles=('grafana',)),
        sources=SourceOptions(include_common_passwords=common), limits=GenerationLimits(20), ranking=RankingOptions(True, 10))
    encoded = json.loads(json.dumps(request.to_dict()))
    assert json.loads(json.dumps(GenerationRequest.from_dict(encoded).to_dict())) == encoded
    if common: assert encoded['sources']['common_passwords_version'] == 'common-v1'
    else: assert 'include_common_passwords' not in encoded['sources']
    expected = list(GenerationService().prepare(request).iter_results())
    with TestClient(create_app(data_dir=tmp_path)) as client:
        response = client.post('/api/jobs', json={'request': encoded})
        assert response.status_code == 201
        job_id = response.json()['id']
        assert client.app.state.job_manager.wait(job_id, 10)['status'] == 'completed'
        assert client.get('/api/jobs/' + job_id).json()['request'] == encoded
        assert client.get('/api/jobs/' + job_id + '/download').content == ''.join(r.candidate.value + '\n' for r in expected).encode()
        previews = client.get('/api/jobs/' + job_id + '/candidates').json()
        assert len(previews) == len(expected)
        assert previews[0]['origins'] == [asdict(o) for o in expected[0].candidate.origins]
        assert previews[0]['score'] == expected[0].score.total
        assert previews[0]['score_version'] == expected[0].score.version
        assert previews[0]['score_components'] == expected[0].score.to_dict()['components']
        assert previews[0]['rank'] == expected[0].rank
    with TestClient(create_app(data_dir=tmp_path)) as client:
        assert client.get('/api/jobs/' + job_id).json()['request'] == encoded
        assert client.get('/api/jobs/' + job_id + '/download').status_code == 200


@pytest.mark.parametrize('change', [
    {'sources': {'include_common_passwords': 'true'}},
    {'sources': {'include_common_passwords': 1}},
    {'sources': {'include_common_passwords': None}},
    {'sources': {'include_common_passwords': True, 'common_passwords_version': 'common-v0'}},
    {'sources': {'include_common_passwords': True, 'common_passwords_version': 'common-v2'}},
    {'sources': {'include_common_passwords': True, 'common_passwords_version': []}},
    {'sources': {'include_common_passwords': False, 'common_passwords_version': 'common-v1'}},
    {'intelligence': {'enabled': True, 'service_profiles': ['nonexistent']}},
], ids=['bool-string', 'bool-int', 'bool-null', 'old-version', 'future-version', 'version-type', 'disabled-version', 'service'])
def test_api_invalid_new_configuration_creates_no_job(change, tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as client:
        response = client.post('/api/jobs', json={'request': change})
        assert response.status_code == 422
        assert client.get('/api/jobs').json() == []


def test_common_job_cancel_preserves_snapshot_without_publishing_output(tmp_path):
    entered = threading.Event(); release = threading.Event()
    class PausedService(GenerationService):
        def prepare(self, request):
            entered.set(); assert release.wait(10)
            return super().prepare(request)
    app = create_app(data_dir=tmp_path); app.state.job_manager.service = PausedService()
    payload = GenerationRequest(sources=SourceOptions(include_common_passwords=True)).to_dict()
    with TestClient(app) as client:
        job_id = client.post('/api/jobs', json={'request': payload}).json()['id']
        try:
            assert entered.wait(10)
            assert client.get('/api/jobs/' + job_id + '/download').status_code == 409
            assert client.post('/api/jobs/' + job_id + '/cancel').status_code == 200
            release.set()
            assert app.state.job_manager.wait(job_id, 10)['status'] == 'cancelled'
            assert client.get('/api/jobs/' + job_id).json()['request']['sources']['common_passwords_version'] == 'common-v1'
            assert client.get('/api/jobs/' + job_id + '/download').status_code == 409
        finally: release.set()


def test_web_empty_state_is_explicitly_scoped_to_catalog_and_errors_preserve_selection(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as client:
        for locale, phrase in [('pt-BR', 'neste catálogo'), ('en', 'in this catalog')]:
            client.cookies.set('mimic_locale', locale)
            for service in ('postgresql', 'wordpress'):
                assert phrase in client.get('/services/' + service).text
        page = client.get('/generate?service=grafana')
        token = re.search(r'name="csrf_token" value="([^"]+)"', page.text)[1]
        response = client.post('/generate', data={'csrf_token': token, 'mode': 'quick', 'nome': 'Alice',
            'service_profiles': 'grafana', 'include_common_passwords': 'on', 'min_len': 'invalid', 'intent': 'preview'})
        assert response.status_code == 422
        assert re.search(r'name="service_profiles" value="grafana"\s+checked', response.text)
        assert re.search(r'name="include_common_passwords"[^>]*checked', response.text)
        assert 'value="Alice"' in response.text
        assert client.get('/api/jobs').json() == []


def test_two_concurrent_web_locales_and_all_catalog_placeholders(tmp_path):
    assert len(TRANSLATIONS['pt-BR']) == len(TRANSLATIONS['en']) == 512
    with TestClient(create_app(data_dir=tmp_path / 'pt')) as pt, TestClient(create_app(data_dir=tmp_path / 'en')) as en:
        pt.cookies.set('mimic_locale', 'pt-BR'); en.cookies.set('mimic_locale', 'en')
        def read(client): return client.get('/services/rabbitmq')
        with ThreadPoolExecutor(2) as pool:
            a, b = list(pool.map(read, (pt, en)))
        assert a.headers['Content-Language'] == 'pt-BR' and b.headers['Content-Language'] == 'en'
        assert 'localhost' in a.text and 'localhost' in b.text
        assert 'guest' in a.text and 'guest' in b.text
        assert translate('pt-BR', 'catalog.credential.rabbitmq-initial-guest.restriction.2') in a.text
        assert translate('en', 'catalog.credential.rabbitmq-initial-guest.restriction.2') in b.text


@pytest.mark.parametrize('scenario', ['grafana', 'two-services', 'organization', 'common', 'pack', 'duplicates', 'quick'],
                         ids=['grafana', 'two-services', 'organization', 'common', 'pack', 'duplicates', 'quick'])
def test_full_metadata_hashseed_equivalence(scenario, tmp_path):
    script = '''
import hashlib,io,json,logging,sys
from dataclasses import asdict
from mimic.application import *
from mimic.core.candidate import Candidate,Origin
from mimic.domain.models import Organization
from mimic.packs import PackRegistry
logging.disable(logging.CRITICAL)
scenario=sys.argv[1]
profiles=('grafana','rabbitmq') if scenario=='two-services' else ('grafana',)
sources=SourceOptions(include_common_passwords=scenario in ('common','duplicates'))
registry=None
if scenario=='pack':
 registry=PackRegistry(sys.argv[2]);registry.import_stream(io.BytesIO(b'Ready!\\nadmin\\n'),id='fixture',version='1',kind='ready',filename='fixture.txt')
 sources=SourceOptions(packs=(registry.reference('fixture@1'),))
request=GenerationRequest(organization=Organization('ACME') if scenario=='organization' else None,
 intelligence=IntelligenceOptions(reference_year=2026,service_profiles=profiles),sources=sources,
 base_candidates=(Candidate('changeme',(Origin('manual','name','changeme'),)),) if scenario=='duplicates' else (),
 mutations=MutationOptions('partial',True,'!'),limits=GenerationLimits(20),
 ranking=RankingOptions.from_budget('quick') if scenario=='quick' else RankingOptions(True,30))
prepared=GenerationService(registry).prepare(request);results=list(prepared.iter_results())
print(json.dumps({'results':[asdict(r) for r in results],'evaluated':prepared.evaluated_count,
 'bytes':hashlib.sha256(''.join(r.candidate.value+'\\n' for r in results).encode()).hexdigest()},sort_keys=True,ensure_ascii=False))
'''
    outputs = [subprocess.check_output([sys.executable, '-B', '-c', script, scenario, str(tmp_path / seed)],
        env={**os.environ, 'PYTHONHASHSEED': seed, 'PYTHONDONTWRITEBYTECODE': '1'}) for seed in ('1', '42', '777')]
    assert outputs[0] == outputs[1] == outputs[2]
