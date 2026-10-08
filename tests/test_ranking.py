"""Score contracts, bounded selection, and the opt-in application boundary."""
from dataclasses import FrozenInstanceError
import json
import os
from pathlib import Path
import random
import subprocess
import sys
from types import SimpleNamespace

import pytest

from mimic.application import (ApplicationError, GenerationRequest, GenerationService,
                               MutationOptions, PolicyOptions, RankingOptions, SourceOptions)
from mimic.application.generation import PreparedGeneration
from mimic.core.candidate import Candidate, Origin, Transformation
from mimic.domain.models import Organization, Target
from mimic.intelligence import IntelligenceOptions
from mimic.profile.schema import TargetProfile
from mimic.ranking import CandidateScore, GenerationResult, ScoreComponent
from mimic.ranking.scoring import score_candidate
from mimic.ranking.topk import select_top_k


def candidate(*origins, steps=()):
    return Candidate('unchanged', tuple(Origin(*origin) for origin in origins), tuple(steps))


def step(kind, **params):
    return Transformation(kind, tuple(params.items()))


@pytest.mark.parametrize('source,field,value,total', [
    ('ready_candidate', '/data:1', 'x', 50), ('manual', 'nome', 'x', 32),
    ('cli', 'numbers', '123', 32), ('profile', 'nome', 'x', 30),
    ('context_file', '/data:pet', 'x', 30), ('target', 'name', 'x', 30),
    ('organization', 'name', 'x', 22), ('knowledge', 'service.wordpress.token', 'wp', 14),
    ('knowledge', 'service.wordpress.role', 'admin', 14), ('knowledge', 'role', 'admin', 10),
    ('knowledge', 'common_number', '123', 8), ('dataset', '/path:1', 'x', 4),
    ('dataset', 'ptbr.reset_words:1', 'senha', 5), ('unknown', 'name', 'x', 0),
    ('knowledge', 'recent_year', '2026', 16), ('knowledge', 'recent_year', '2025', 13),
    ('knowledge', 'recent_year', '2024', 10), ('knowledge', 'recent_year', '2023', 7),
    ('knowledge', 'recent_year', '2022', 0), ('knowledge', 'recent_year', '2027', 0),
])
def test_origin_weights(source, field, value, total):
    score = score_candidate(candidate((source, field, value)), 2026)
    assert score.total == total
    assert score.version == 'score-v1'
    assert score.total == sum(c.delta for c in score.components)
    if source != 'unknown':
        assert value in score.components[0].description


def test_exact_components_and_serialization():
    original = candidate(('organization', 'name', 'ACME'),
                         ('knowledge', 'service.wordpress.role', 'admin'),
                         ('knowledge', 'recent_year', '2026'),
                         steps=(step('knowledge_template', template='organization_role'),
                                step('case', mode='original'), step('affix', token='2026')))
    score = score_candidate(original, 2026)
    assert score.total == 56
    assert [c.code for c in score.components] == [
        'origin.organization.name', 'origin.service.service.wordpress.role',
        'origin.recent_year.recent_year', 'transformation.knowledge_template',
        'transformation.case.original', 'transformation.affix']
    assert [c.delta for c in score.components] == [22, 14, 16, 4, 0, 0]
    assert score.components[0] == ScoreComponent('origin.organization.name', 22,
                                               'Recorded organization.name=ACME')
    result = GenerationResult(original, score, 1, 2)
    restored = GenerationResult.from_dict(json.loads(json.dumps(result.to_dict())))
    assert restored == result
    with pytest.raises(FrozenInstanceError):
        score.total = 100
    assert result.candidate is original


def test_caps_and_semantic_fields():
    origins = [('profile', 'nome', 'Ana'), ('profile', 'nome', 'Bia'),
               ('context_file', '/a:nome', 'Ana'), ('target', 'name', 'Ana'),
               ('profile', 'pet', 'Luna'), ('profile', 'empresa', 'ACME')]
    score = score_candidate(candidate(*origins, origins[0]))
    assert score.total == 60
    assert [c.delta for c in score.components] == [30, 30, 0]
    assert 'cap 60' in score.components[-1].description
    for source, fields, cap in [
        ('organization', ['name', 'alias', 'domain', 'keyword'], 44),
        ('knowledge', ['service.wordpress.token', 'service.wordpress.role', 'service.mysql.token'], 28),
        ('manual', ['nome', 'pet', 'number'], 32),
        ('ready_candidate', ['/a:1', '/b:2'], 50),
        ('dataset', ['/a:1', '/b:2'], 4),
    ]:
        assert score_candidate(candidate(*[(source, f, 'x') for f in fields])).total == cap


@pytest.mark.parametrize('kind,params,weight', [
    ('case', {'mode':'original'}, 0), ('case', {'mode':'title'}, -1),
    ('case', {'mode':'lower'}, -1), ('case', {'mode':'upper'}, -2),
    ('leet', {'position':'0'}, -2), ('reverse', {}, -12), ('combine', {}, -4),
    ('affix', {}, 0), ('organization_domain_label', {}, -1), ('date', {}, 0),
    ('knowledge_template', {}, 4),
])
def test_transformations(kind, params, weight):
    base = candidate(('manual', 'nome', 'Ana'))
    changed = Candidate(base.value, base.origins, (step(kind, **params),))
    assert score_candidate(changed).total == score_candidate(base).total + weight
    if kind == 'leet':
        twice = Candidate(base.value, base.origins, changed.transformations * 2)
        assert score_candidate(twice).total == 28


def test_score_ignores_final_value_and_live_clock():
    base = candidate(('knowledge', 'recent_year', '2026'))
    assert score_candidate(base, 2026) == score_candidate(Candidate('anything', base.origins), 2026)
    assert score_candidate(base, 2027).total == 13
    assert score_candidate(base).total == 0


@pytest.mark.parametrize('budget', [1, 3, 10, 50, 200])
def test_heap_matches_sorted_reference_and_is_bounded(monkeypatch, budget):
    import mimic.ranking.topk as module
    rng = random.Random(100)
    candidates = [Candidate(str(i)) for i in range(100)]
    scores = [rng.randrange(-10, 20) for _ in candidates]
    maximum = 0
    original_push = module.heapq.heappush
    def push(heap, entry):
        nonlocal maximum
        original_push(heap, entry)
        maximum = max(maximum, len(heap))
    monkeypatch.setattr(module.heapq, 'heappush', push)
    def scorer(c):
        return CandidateScore(scores[int(c.value)], ())
    actual = list(select_top_k(iter(candidates), budget, scorer))
    expected = sorted(enumerate(candidates), key=lambda pair: (-scores[pair[0]], pair[0]))[:budget]
    assert [r.candidate for r in actual] == [c for _, c in expected]
    assert [r.rank for r in actual] == list(range(1, len(actual)+1))
    assert maximum <= budget
    assert all(r.candidate is candidates[r.encounter_index] for r in actual)


def test_equal_scores_use_encounter_order_and_empty_stream():
    items = [Candidate(value) for value in ['z', 'a', 'm']]
    assert [r.candidate.value for r in select_top_k(items, 2, score_candidate)] == ['z', 'a']
    assert list(select_top_k([], 100, score_candidate)) == []


@pytest.mark.parametrize('options', ['exhaustive', 'quick', 'focused', 'balanced', 'large', '2500'])
def test_request_roundtrip(options):
    request = GenerationRequest(target=Target('Ána', TargetProfile(nome='Ána')),
        intelligence=IntelligenceOptions(enabled=True, reference_year=2026, service_profiles=('wordpress',)),
        sources=SourceOptions(dataset_paths=('/dados/á.txt',)), ranking=RankingOptions.from_budget(options))
    payload = json.loads(json.dumps(request.to_dict(), ensure_ascii=False))
    assert GenerationRequest.from_dict(payload).to_dict() == request.to_dict()
    payload.pop('ranking')
    assert not GenerationRequest.from_dict(payload).ranking.enabled


@pytest.mark.parametrize('options', [dict(enabled=True), dict(enabled=True,budget=0),
    dict(enabled=True,budget=-2), dict(enabled=True,budget=True), dict(enabled=True,budget=2.0),
    dict(enabled='yes'), dict(budget=1)])
def test_invalid_options(options):
    with pytest.raises(ValueError):
        RankingOptions(**options)


def request(**kwargs):
    return GenerationRequest(base_candidates=(candidate(('manual','nome','Ana')),),
                             mutations=MutationOptions(leet_mode='none', separators=''), **kwargs)


@pytest.mark.parametrize('first', ['iter_candidates','iter_values','iter_results'])
@pytest.mark.parametrize('second', ['iter_candidates','iter_values','iter_results'])
def test_one_shot_guard_claims_immediately(first, second):
    prepared = GenerationService().prepare(request(ranking=RankingOptions(True, 2)))
    getattr(prepared, first)()
    assert prepared.evaluated_count == 0
    with pytest.raises(ApplicationError):
        getattr(prepared, second)()


def test_exhaustive_bypasses_score_and_heap(monkeypatch):
    import mimic.application.generation as module
    def forbidden(*args):
        pytest.fail('exhaustive invoked ranking')
    monkeypatch.setattr(module, 'score_candidate', forbidden)
    monkeypatch.setattr(module, 'select_top_k', forbidden)
    prepared = GenerationService().prepare(request())
    results = list(prepared.iter_results())
    assert results and all(r.score is None and r.rank is None for r in results)
    assert prepared.evaluated_count == len(results)


def test_policy_precedes_scoring_and_budget_scans_all(monkeypatch):
    import mimic.application.generation as module
    scored = []
    real = module.score_candidate
    prepared = GenerationService().prepare(request(ranking=RankingOptions(True, 1),
                                                   policy=PolicyOptions(require_upper=True, require_lower=False)))
    def score(c, year):
        scored.append(c)
        assert any(ch.isupper() for ch in c.value)
        return real(c, year)
    monkeypatch.setattr(module, 'score_candidate', score)
    output = list(prepared.iter_results())
    assert len(output) == 1 < prepared.evaluated_count == len(scored)


def test_checkpoint_can_interrupt_scan_before_results():
    prepared = GenerationService().prepare(request(ranking=RankingOptions(True, 1)))
    calls = []
    def checkpoint():
        calls.append(prepared.evaluated_count)
        if len(calls) == 3:
            raise InterruptedError('cancel')
    results = prepared.iter_results(checkpoint)
    with pytest.raises(InterruptedError):
        next(results)
    assert calls == [0, 1, 2]
    assert prepared.evaluated_count == 2


def test_original_candidates_and_first_causal_derivation_survive():
    first = Candidate('equal', (Origin('dataset','first:1','equal'),))
    second = Candidate('equal', (Origin('ready_candidate','second:1','equal'),))
    fake = SimpleNamespace(generator=SimpleNamespace(generate_candidates=lambda: iter((first,))))
    prepared = PreparedGeneration(request(ranking=RankingOptions(True, 10)), fake, (), None)
    result = next(prepared.iter_results())
    assert result.candidate is first
    real_request = GenerationRequest(base_candidates=(first, second), mutations=MutationOptions(leet_mode='none'))
    exhaustive = list(GenerationService().prepare(real_request).iter_candidates())
    ranked = list(GenerationService().prepare(GenerationRequest.from_dict({**real_request.to_dict(),
        'ranking': {'enabled':True,'budget':100}})).iter_candidates())
    assert set(exhaustive) == set(ranked)
    assert next(c for c in ranked if c.value == 'equal').origins == first.origins


def test_hash_seed_determinism():
    script = '''import json
from mimic.application import *
from mimic.domain.models import Organization
r=GenerationRequest(organization=Organization('ACME'),
 intelligence=IntelligenceOptions(reference_year=2026,service_profiles=('wordpress',)),
 mutations=MutationOptions(leet_mode='none',separators='!'),ranking=RankingOptions(True,100))
print(json.dumps([x.to_dict() for x in GenerationService().prepare(r).iter_results()],ensure_ascii=False))'''
    outputs = [subprocess.run([sys.executable,'-B','-c',script],check=True,capture_output=True,
        env={**os.environ,'PYTHONHASHSEED':seed,'PYTHONDONTWRITEBYTECODE':'1'}).stdout
        for seed in ['1','42','777']]
    assert outputs[0] == outputs[1] == outputs[2]


def test_import_boundaries():
    script = '''import sys
import mimic.core
assert not any(n.startswith('mimic.ranking') for n in sys.modules)
import mimic.ranking, mimic.application
assert not any(n.startswith(('fastapi','mimic.jobs','mimic.persistence','mimic.web','mimic.cli')) for n in sys.modules)
'''
    subprocess.run([sys.executable,'-B','-c',script],check=True)
    for path in Path('mimic/core').glob('*.py'):
        assert 'mimic.ranking' not in path.read_text()
    manager = Path('mimic/jobs/manager.py').read_text()
    assert 'scoring import' not in manager and 'WEIGHTS' not in manager


def test_relative_context_priority():
    target_year = candidate(('profile','nome','Ana'),('knowledge','recent_year','2026'))
    dataset = candidate(('dataset','/a:1','generic'))
    contextual = candidate(('organization','name','ACME'),('knowledge','service.wordpress.token','wp'),
                           ('knowledge','common_number','123'))
    service = candidate(('knowledge','service.wordpress.token','wp'))
    assert score_candidate(target_year,2026).total > score_candidate(dataset,2026).total
    assert score_candidate(contextual,2026).total > score_candidate(service,2026).total


@pytest.mark.parametrize('total,budget', [(152,100),(80,100)])
def test_evaluated_and_retained_exactness(total,budget):
    options = request(ranking=RankingOptions(True,budget))
    fake = SimpleNamespace(generator=SimpleNamespace(generate_candidates=lambda: (Candidate(str(i)) for i in range(total))))
    prepared = PreparedGeneration(options,fake,(),None)
    assert len(list(prepared.iter_results())) == min(total,budget)
    assert prepared.evaluated_count == total


def test_ready_input_keeps_empty_transformations(tmp_path):
    source=tmp_path/'ready.txt'; source.write_text('Exact!\n',encoding='utf-8')
    options=GenerationRequest(sources=SourceOptions(ready_candidate_paths=(str(source),)),
                              ranking=RankingOptions(True,100))
    result=next(GenerationService().prepare(options).iter_results())
    assert result.candidate.value == 'Exact!' and result.candidate.transformations == ()
    assert result.candidate.origins == (Origin('ready_candidate',str(source)+':1','Exact!'),)
    assert result.score.total == 50
