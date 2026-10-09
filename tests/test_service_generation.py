"""Minimal service/common inputs through the existing engine and snapshots."""
from dataclasses import asdict, replace
import json
import os
import subprocess
import sys
import threading

from fastapi.testclient import TestClient
import pytest

from mimic.api import create_app
from mimic.application import (GenerationRequest, GenerationService, SourceOptions, IntelligenceOptions,
    MutationOptions, PolicyOptions, GenerationLimits, RankingOptions, InvalidGenerationRequest)
from mimic.core.candidate import Candidate, Origin
from mimic.domain.models import Organization
from mimic.intelligence import catalog
from mimic.intelligence.planning import plan_intelligence
from mimic.ranking.scoring import score_candidate
from mimic.cli import main


def service_request(service='grafana', **changes):
    return GenerationRequest(intelligence=IntelligenceOptions(reference_year=2026, service_profiles=(service,)),
        limits=GenerationLimits(20), mutations=MutationOptions('partial', True, '!'), **changes)


@pytest.mark.parametrize('service', ['grafana', 'rabbitmq'])
def test_service_only_uses_selected_profile_and_existing_pipeline(service):
    req = service_request(service, ranking=RankingOptions(True, 10))
    prepared = GenerationService().prepare(req)
    results = list(prepared.iter_results())
    assert len(results) == 10 and prepared.evaluated_count > 10
    assert req.target is req.organization is None
    fields = {o.field for r in results for o in r.candidate.origins if o.field.startswith('service.')}
    assert fields and all(f.startswith('service.' + service + '.') for f in fields)
    assert any(f.endswith('.token') for f in fields)
    assert all(r.rank is not None for r in results)
    assert all(r.score == score_candidate(r.candidate, 2026) for r in results)


def test_organization_service_has_bounded_contextual_templates():
    req = service_request(organization=Organization('ACME'))
    prepared = GenerationService().prepare(req)
    candidates = list(prepared.iter_candidates())
    candidate = next(c for c in candidates if c.value == 'ACMEgrafana')
    assert candidate.origins == (Origin('organization', 'name', 'ACME'),
        Origin('knowledge', 'service.grafana.token', 'grafana'))
    assert any(t.kind == 'knowledge_template' for t in candidate.transformations)
    assert not any(o.field.startswith('service.rabbitmq.') for c in candidates for o in c.origins)
    assert prepared.summary().knowledge_template_seed_count < 100


def test_common_opt_in_ready_noncombinable_and_no_cartesian_product():
    disabled = GenerationRequest(base_candidates=(Candidate('Alice'),),
        mutations=MutationOptions('full', True, '!'), limits=GenerationLimits(3))
    assert 'changeme' not in list(GenerationService().prepare(disabled).iter_values())
    enabled = replace(disabled, sources=SourceOptions(include_common_passwords=True))
    prepared = GenerationService().prepare(enabled)
    candidates = list(prepared.iter_candidates())
    common = [c for c in candidates if c.origins and c.origins[0].field == 'common_password']
    assert [c.value for c in common] == list(catalog.COMMON_VOCABULARY.passwords)
    assert all(c.origins == (Origin('knowledge', 'common_password', c.value),) and c.transformations == () for c in common)
    assert not any(c.value in ('rootwelcome', 'administratoradmin', 'Alicechangeme', 'changemeAlice') for c in candidates)
    # Common passwords are neither numeric operands nor mutable seeds.
    assert not any('changeme' in c.value and c.value != 'changeme' for c in candidates)
    seeds = list(GenerationService()._extra_seeds(enabled, plan_intelligence(IntelligenceOptions(enabled=False))))
    assert len(seeds) == 6 and all(not s.mutable and not s.combinable for s in seeds)
    assert prepared.summary().common_password_count == 6


def test_common_alone_policy_dedup_and_ranking_use_canonical_scoring():
    req = GenerationRequest(sources=SourceOptions(include_common_passwords=True),
        policy=PolicyOptions(min_len=7), ranking=RankingOptions(True, 2))
    prepared = GenerationService().prepare(req)
    results = list(prepared.iter_results())
    assert [r.candidate.value for r in results] == ['password', 'changeme']
    assert prepared.evaluated_count == 3
    assert all(r.score.total == 0 and r.score.components == () for r in results)
    explicit = Candidate('changeme', (Origin('manual', 'nome', 'changeme'),))
    req = replace(req, policy=PolicyOptions(), ranking=RankingOptions(), base_candidates=(explicit,))
    candidates = list(GenerationService().prepare(req).iter_candidates())
    assert sum(c.value == 'changeme' for c in candidates) == 1
    assert next(c for c in candidates if c.value == 'changeme').origins == explicit.origins


def test_old_request_and_summary_contract_and_opt_in_json_roundtrip():
    old = GenerationRequest.from_dict({'base_candidates': [{'value': 'Old'}]})
    assert old.sources.to_dict() == {'dataset_paths': (), 'ready_candidate_paths': (), 'include_ptbr': False}
    assert 'include_common_passwords' not in old.to_dict()['sources']
    assert 'common_password_count' not in GenerationService().prepare(old).summary().to_dict()
    req = service_request(sources=SourceOptions(include_common_passwords=True))
    serialized = json.loads(json.dumps(req.to_dict()))
    assert serialized['sources']['common_passwords_version'] == 'common-v1'
    assert GenerationRequest.from_dict(serialized).to_dict() == req.to_dict()
    assert GenerationRequest.from_dict({'sources': {'include_common_passwords': True}}).sources.common_passwords_version == 'common-v1'


@pytest.mark.parametrize('sources', [dict(include_common_passwords='yes'), dict(include_common_passwords=1),
    dict(include_common_passwords=True, common_passwords_version='missing'),
    dict(common_passwords_version='common-v1')], ids=['string', 'integer', 'version', 'disabled-version'])
def test_invalid_common_configuration_is_rejected(sources):
    with pytest.raises(InvalidGenerationRequest):
        GenerationRequest.from_dict({'sources': sources})


def test_documented_pairs_never_become_generation_sources(monkeypatch):
    def forbidden(*a, **kw):
        raise AssertionError('generation consulted documented pairs')
    monkeypatch.setattr(catalog, 'list_credentials', forbidden)
    candidates = list(GenerationService().prepare(service_request()).iter_candidates())
    assert candidates
    assert not any(c.value == 'password' for c in candidates)
    assert not any(o.field == 'common_password' for c in candidates for o in c.origins)


def test_cli_service_only_and_explicit_common(tmp_path, capsys):
    output = tmp_path / 'grafana.txt'
    assert main(['generate', '--service', 'grafana', '--reference-year', '2026', '--budget', 'focused',
        '--max-per-word', '20', '--quiet', '-o', str(output)]) == 0
    assert output.read_text() and len(output.read_text().splitlines()) <= 1000
    common = tmp_path / 'common.txt'
    assert main(['generate', '--include-common-passwords', '--no-intelligence', '--quiet', '-o', str(common)]) == 0
    assert common.read_text().splitlines() == list(catalog.COMMON_VOCABULARY.passwords)
    assert not capsys.readouterr().err


@pytest.mark.parametrize('organization', [False, True], ids=['service-only', 'organization-service'])
def test_new_features_hashseed_determinism(organization):
    script = '''
import json
from dataclasses import asdict
from mimic.application import *
from mimic.domain.models import Organization
req=GenerationRequest(organization=Organization('ACME') if ORGANIZATION else None,
    intelligence=IntelligenceOptions(reference_year=2026,service_profiles=('grafana','rabbitmq')),
    sources=SourceOptions(include_common_passwords=True), mutations=MutationOptions('partial',True,'!'),
    limits=GenerationLimits(20),ranking=RankingOptions(True,30))
p=GenerationService().prepare(req)
results=list(p.iter_results())
print(json.dumps({'results':[asdict(r) for r in results],'evaluated':p.evaluated_count,'wordlist':'\\n'.join(r.candidate.value for r in results)},sort_keys=True,ensure_ascii=False))
'''.replace('ORGANIZATION', repr(organization))
    outputs = [subprocess.check_output([sys.executable, '-B', '-c', script],
        env={**os.environ, 'PYTHONHASHSEED': seed, 'PYTHONDONTWRITEBYTECODE': '1'}) for seed in ('1', '42', '777')]
    assert outputs[0] == outputs[1] == outputs[2]


def test_job_snapshot_freezes_service_and_common_option(tmp_path):
    entered = threading.Event(); release = threading.Event()
    class PausedService(GenerationService):
        def prepare(self, req):
            entered.set()
            assert release.wait(5)
            return super().prepare(req)
    app = create_app(data_dir=tmp_path)
    app.state.job_manager.service = PausedService()
    req = service_request(sources=SourceOptions(include_common_passwords=True), ranking=RankingOptions(True, 10))
    expected = req.to_dict()
    with TestClient(app) as client:
        response = client.post('/api/jobs', json={'request': expected})
        assert response.status_code == 201
        job_id = response.json()['id']
        try:
            assert entered.wait(5)
            req.sources = SourceOptions()
            req.intelligence = IntelligenceOptions(enabled=False)
            snapshot = app.state.repository.get_job(job_id)['request']
            assert snapshot == json.loads(json.dumps(expected))
            assert snapshot['sources']['common_passwords_version'] == 'common-v1'
            release.set()
            assert app.state.job_manager.wait(job_id, 10)['status'] == 'completed'
            assert client.get('/api/jobs/' + job_id + '/download').status_code == 200
        finally:
            release.set()
