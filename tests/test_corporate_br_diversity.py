"""Block 12.6: opt-in source resolution and bounded structural selection."""
from dataclasses import asdict, replace
import gc
import json
import os
from pathlib import Path
import random
import re
import socket
import subprocess
import sys
import threading
import tracemalloc
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from mimic.api import create_app
from mimic.application import (GenerationRequest, GenerationService, IntelligenceOptions,
    MutationOptions, SourceOptions, RankingOptions, GenerationLimits, PolicyOptions)
from mimic.application.errors import InvalidGenerationRequest
from mimic.core.candidate import Candidate, Origin, Transformation
from mimic.domain.models import Organization
from mimic.ranking import CandidateScore, GenerationResult
from mimic.ranking.diverse import select_diverse
from mimic.ranking.families import FAMILIES, FAMILY_VERSION, candidate_family
from mimic.ranking.scoring import score_candidate
from mimic.ranking.topk import select_top_k


def c(value='opaque', origins=(), steps=()):
    return Candidate(value, tuple(Origin(*o) for o in origins),
                     tuple(Transformation(kind, tuple(params.items())) for kind, params in steps))


ORG = ('organization', 'name', 'Private Name')
YEAR = ('knowledge', 'recent_year', '2026')
NUMBER = ('knowledge', 'common_number', '123')
PTBR = ('dataset', 'ptbr.reset_words:2', 'Private Word')
AFFIX = ('affix', {'token': 'opaque'})


@pytest.mark.parametrize('preset', ['corporate-br', 'corporate-br-v1'])
def test_preset_resolves_sources_and_freezes_year(preset):
    r = GenerationRequest.from_dict({'preset': preset, 'intelligence': {'reference_year': 2026}})
    assert r.preset == 'corporate-br-v1'
    assert r.organization_variants and r.sources.include_ptbr and r.sources.include_common_passwords
    assert r.sources.common_passwords_version == 'common-v1'
    assert r.intelligence == IntelligenceOptions(reference_year=2026)
    assert r.intelligence.service_profiles == ()
    assert r.mutations == MutationOptions() and r.limits == GenerationLimits()
    assert r.policy == PolicyOptions() and r.ranking == RankingOptions()
    assert r.organization is None
    assert GenerationRequest.from_dict(json.loads(json.dumps(r.to_dict()))).to_dict() == r.to_dict()
    assert GenerationService().prepare(r).summary().to_dict()['preset'] == r.preset


def test_direct_preset_omitted_options_and_explicit_objects():
    r = GenerationRequest(preset='corporate-br')
    assert r.sources.include_ptbr and r.intelligence.enabled and r.organization_variants
    r = GenerationRequest(preset='corporate-br', sources=SourceOptions(),
                          intelligence=IntelligenceOptions(enabled=False), organization_variants=False)
    restored = GenerationRequest.from_dict(r.to_dict())
    assert not restored.sources.include_ptbr and not restored.sources.include_common_passwords
    assert not restored.organization_variants and not restored.intelligence.enabled
    assert restored.to_dict() == r.to_dict()


@pytest.mark.parametrize('section,key', [('sources','include_ptbr'), ('sources','include_common_passwords'),
    ('intelligence','enabled'), ('intelligence','common_numbers'), ('intelligence','recent_years'),
    ('intelligence','corporate_roles')])
def test_explicit_false_survives_preset_and_job_roundtrip(section, key):
    r = GenerationRequest.from_dict({'preset':'corporate-br', section: {key:False}, 'organization_variants':False})
    assert getattr(getattr(r,section),key) is False
    for _ in range(3):
        r = GenerationRequest.from_dict(json.loads(json.dumps(r.to_dict())))
        assert getattr(getattr(r,section),key) is False and r.organization_variants is False


@pytest.mark.parametrize('value', ['', 'future-v2', True, False, 1, [], {}, 'corporate-br-v2'])
def test_bad_presets_rejected(value):
    with pytest.raises((InvalidGenerationRequest, ValueError)):
        GenerationRequest.from_dict({'preset':value})


def test_old_request_and_result_shapes_stay_historical():
    r = GenerationRequest.from_dict({})
    assert r.preset is None and not r.sources.include_ptbr and not r.intelligence.enabled
    assert not r.organization_variants
    assert 'preset' not in r.to_dict() and 'organization_variants' not in r.to_dict()
    assert r.to_dict()['ranking'] == {'enabled':False,'budget':None}
    assert 'selection' not in GenerationResult(c()).to_dict()
    assert set(GenerationService().prepare(r).summary().to_dict()['ranking']) == {'enabled','budget'}
    assert GenerationRequest.from_dict(r.to_dict()).to_dict() == r.to_dict()


@pytest.mark.parametrize('origins,steps,family', [
    ([('ready_candidate','local:1','secret')], [], 'ready'),
    ([('knowledge','common_password','secret')], [], 'ready'),
    ([('ready_candidate','local:1','secret')], [('reverse',{})], 'other'),
    ([ORG,YEAR], [('knowledge_template',{'template':'organization_role_reverse'}),AFFIX], 'organization-role'),
    ([ORG], [('knowledge_template',{'template':'organization_service'})], 'organization-service'),
    ([], [('knowledge_template',{'template':'service_role_reverse'})], 'service-role'),
    ([ORG,PTBR], [('combine',{}),AFFIX], 'combined'),
    ([ORG,YEAR,NUMBER], [AFFIX], 'organization-year'),
    ([ORG,NUMBER], [AFFIX], 'organization-number'),
    ([ORG,YEAR], [], 'organization-other'),
    ([('profile','empresa','private'),NUMBER], [AFFIX], 'organization-number'),
    ([('context_file','private-path:empresa','private'),YEAR], [AFFIX], 'organization-year'),
    ([PTBR,YEAR], [AFFIX], 'ptbr-year'),
    ([PTBR,NUMBER], [AFFIX], 'ptbr-number'),
    ([PTBR], [], 'ptbr-other'),
    ([], [], 'other'),
    ([('future','private','secret')], [('future',{'secret':'private'})], 'other'),
    ([ORG,PTBR,YEAR], [AFFIX], 'organization-year'),
    ([ORG], [('knowledge_template',{'template':'organization_service'}),
             ('knowledge_template',{'template':'organization_role'})], 'organization-role'),
])
def test_causal_family_precedence(origins, steps, family):
    assert candidate_family(c('Unrelated password 2026', origins, steps)) == family
    assert candidate_family(c('Different literal', list(reversed(origins)), list(reversed(steps)))) == family
    assert family in FAMILIES and 'secret' not in family and 'private' not in family


def test_final_text_cannot_invent_a_family():
    for value in ('Mudar@123','AcmeCorpBrasil123@','Senha2026!','Acmeadmin2026'):
        assert candidate_family(Candidate(value)) == 'other'
    assert len(FAMILIES) == 12 and len(set(FAMILIES)) == 12
    assert FAMILY_VERSION == 'candidate-family-v1'


@pytest.mark.parametrize('budget', [1,2,3,5,12,100,1000])
@pytest.mark.parametrize('size', [0,1,5,300])
def test_diversity_matches_independent_full_sort_oracle(budget,size):
    rng = random.Random(126)
    values = [c(str(i), [rng.choice([ORG,PTBR,('knowledge','common_password','x'),('manual','nome','x')])],
                [AFFIX] if i % 2 else []) for i in range(size)]
    # Ties and unequal family scores, independent of candidate literals.
    scores = {x.value: CandidateScore(rng.randrange(4),()) for x in values}
    scorer = lambda x: scores[x.value]
    ordered = sorted(enumerate(values),key=lambda x:(-scorer(x[1]).total,x[0]))
    winners = {}
    for index, value in ordered:
        winners.setdefault(candidate_family(value),index)
    representative_ids = list(winners.values())[:budget]
    expected = set(representative_ids)
    for index,_ in ordered:
        if len(expected) >= min(budget,size): break
        expected.add(index)
    actual = list(select_diverse(iter(values),budget,scorer))
    assert [r.encounter_index for r in actual] == [i for i,_ in ordered if i in expected]
    assert len(actual) == min(size,budget)
    assert [r.rank for r in actual] == list(range(1,len(actual)+1))
    for r in actual:
        assert r.candidate is values[r.encounter_index]
        assert r.score is scores[r.candidate.value]
        assert r.selection.family == candidate_family(r.candidate)
        assert r.selection.reason == ('family-representative' if r.encounter_index in representative_ids else 'score-fill')
        assert GenerationResult.from_dict(json.loads(json.dumps(r.to_dict()))) == r
    if size:
        assert len({r.selection.family for r in actual}) == min(budget,len(winners))


def test_diversity_displacement_and_score_invariance():
    values = [c(str(i),[ORG]) for i in range(200)] + [c('ptbr',[PTBR]), c('unknown')]
    baseline = list(select_top_k(values,100,score_candidate))
    diverse = list(select_diverse(values,100,score_candidate))
    assert len({candidate_family(r.candidate) for r in baseline}) == 1
    assert len({r.selection.family for r in diverse}) == 3
    assert len({r.candidate.value for r in baseline} - {r.candidate.value for r in diverse}) == 2
    assert all(r.score == score_candidate(r.candidate) for r in diverse)
    assert diverse[0].candidate == values[0] and diverse[-1].candidate.value == 'unknown'


@pytest.mark.parametrize('size', [2000,20000])
def test_selector_live_memory_is_bounded_by_k_and_fixed_families(size):
    gc.collect(); tracemalloc.start()
    list(select_diverse((c(str(i),[ORG if i%2 else PTBR]) for i in range(size)),25,
                        lambda value: CandidateScore(1,())))
    _,peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
    # Independent stream: excludes Core's O(N) dedup. Generous fixed ceiling
    # catches retaining the entire 20k stream, without timing assertions.
    assert peak < 500_000


@pytest.mark.parametrize('config', [dict(selector='diverse-v1'), dict(selector='other'),
    dict(enabled=True,budget=10,selector='other'),dict(enabled=True,budget=10,family_version=FAMILY_VERSION),
    dict(enabled=True,budget=10,selector='diverse-v1',family_version='future'),
    dict(enabled=True,budget=10,selector=True)])
def test_invalid_selection_requests(config):
    with pytest.raises((ValueError,InvalidGenerationRequest)):
        GenerationRequest.from_dict({'ranking':config})


def test_preset_ready_values_not_mutated_and_real_ptbr_causes():
    r=GenerationRequest.from_dict({'preset':'corporate-br','organization':{'name':'Acme Corp Brasil'},
        'intelligence':{'reference_year':2026},'mutations':{'leet_mode':'none','separators':'@!'}})
    targets = {'AcmeCorpBrasil123@','Mudar@123','Senha2026!','ACMECorp2026!','mudar'}
    p=GenerationService().prepare(r)
    found={x.value:x for x in p.iter_candidates() if x.value in targets}
    assert targets - set(found) == {'ACMECorp2026!'}  # No invented ACMECorp alias.
    assert candidate_family(found['Mudar@123']) == 'ptbr-number'
    assert candidate_family(found['Senha2026!']) == 'ptbr-year'
    assert candidate_family(found['AcmeCorpBrasil123@']) == 'organization-number'
    assert found['mudar'].origins == (Origin('knowledge','common_password','mudar'),)
    assert found['mudar'].transformations == ()
    assert not any(o.field=='common_password' for o in found['Mudar@123'].origins)
    alias=replace(r,organization=Organization('Acme Corp Brasil',aliases=['ACMECorp']))
    assert any(x=='ACMECorp2026!' for x in GenerationService().prepare(alias).iter_values())


def test_preview_remains_lazy_and_no_network(monkeypatch):
    import mimic.core.generator as core
    monkeypatch.setattr(core.Generator,'generate_candidates',lambda *_:pytest.fail('preview generated'))
    monkeypatch.setattr(socket,'socket',lambda *_args,**_kw:pytest.fail('network'))
    r=GenerationRequest.from_dict({'preset':'corporate-br','sources':{'dataset_paths':['/missing']},
        'ranking':{'enabled':True,'budget':100,'selector':'diverse-v1'}})
    assert GenerationService().prepare(r).summary().ptbr_enabled


def csrf(client):
    return re.search(r'name="csrf_token" value="([^"]+)"',client.get('/generate').text)[1]


@pytest.mark.parametrize('locale',['pt-BR','en'])
def test_web_preset_resolved_preview_explicit_overrides_and_security(tmp_path,locale):
    with TestClient(create_app(data_dir=tmp_path),cookies={'mimic_locale':locale}) as client:
        form={'csrf_token':csrf(client),'nome':'Synthetic','preset':'corporate-br-v1','reference_year':'2026',
              'selector':'diverse-v1','output_priority':'quick','intent':'preview','leet_mode':'none','separators':''}
        response=client.post('/generate',data=form)
        assert response.status_code==200 and 'corporate-br-v1' in response.text and FAMILY_VERSION in response.text
        assert 'name="include_ptbr" checked' in response.text
        assert client.app.state.repository.list_jobs()==[]
        form.update(preset_options='custom', intelligence_form='1',organization_variants_form='1')
        response=client.post('/generate',data=form)
        assert response.status_code==200
        assert 'name="include_ptbr" checked' not in response.text
        assert 'name="include_common_passwords" checked' not in response.text
        assert client.post('/generate',data={**form,'csrf_token':'bad'}).status_code==403
        assert client.post('/generate',data={**form,'output_priority':'exhaustive'}).status_code==422
        assert client.post('/generate',data={**form,'preset':'<script>x</script>'}).status_code==422
        assert "script-src 'self'" in response.headers['content-security-policy']


def test_api_jobs_store_original_scores_and_separate_selection_without_migration(tmp_path):
    app=create_app(data_dir=tmp_path)
    r=GenerationRequest.from_dict({'preset':'corporate-br','organization':{'name':'Fictional'},
       'intelligence':{'reference_year':2026},'mutations':{'leet_mode':'none','separators':''},
       'ranking':{'enabled':True,'budget':100,'selector':'diverse-v1'}})
    expected=list(GenerationService().prepare(r).iter_results())
    with TestClient(app) as client:
        submitted=client.post('/api/jobs',json={'request':r.to_dict()})
        assert submitted.status_code==201
        job=app.state.job_manager.wait(submitted.json()['id'],20)
        assert job['status']=='completed'
        assert job['request']==json.loads(json.dumps(r.to_dict()))
        rows=client.get(f"/api/jobs/{job['id']}/candidates").json()
        for row,result in zip(rows,expected):
            assert row['selection']==asdict(result.selection)
            assert row['score_components']==[asdict(x) for x in result.score.components]
            assert row['origins']==[asdict(x) for x in result.candidate.origins]
            assert row['transformations']==json.loads(json.dumps([asdict(x) for x in result.candidate.transformations]))
        body=client.get(f"/api/jobs/{job['id']}/download").content
        assert body==''.join(r.candidate.value+'\n' for r in expected).encode()
        with app.state.repository.database.connection() as connection:
            assert connection.execute('PRAGMA user_version').fetchone()[0]==2
    with TestClient(create_app(data_dir=tmp_path)) as restarted:
        assert restarted.get(f"/api/jobs/{job['id']}/download").content==body
        assert restarted.get(f"/api/jobs/{job['id']}/candidates").json()==rows
        assert 'candidate-family-v1' in restarted.get(f"/jobs/{job['id']}").text


@pytest.mark.parametrize('action',['cancel','recover'])
def test_diverse_job_cancellation_and_recovery(tmp_path,action):
    from mimic.jobs import JobManager
    from mimic.persistence import DataPaths,Database,Repository
    paths=DataPaths(tmp_path);db=Database(paths);db.initialize();repo=Repository(db)
    r=GenerationRequest.from_dict({'preset':'corporate-br','ranking':{'enabled':True,'budget':100,'selector':'diverse-v1'}})
    if action=='recover':
        for state in ('pending','running'):
            job=repo.create_job(r.to_dict(),None,None)
            if state=='running':repo.start_job(job['id'])
        manager=JobManager(repo,paths);manager.start();manager.stop()
        assert all(j['status']=='failed' for j in repo.list_jobs())
        return
    entered,release=threading.Event(),threading.Event()
    class Service:
        def prepare(self,request):
            p=GenerationService().prepare(request)
            def stream():
                for i in range(1000):
                    if i==30:entered.set();release.wait(5)
                    yield c(str(i),[ORG])
            p._planned=SimpleNamespace(generator=SimpleNamespace(generate_candidates=stream))
            return p
    manager=JobManager(repo,paths,service=Service(),count_batch=10);manager.start()
    try:
        job=manager.submit(r);assert entered.wait(5)
        manager.cancel(job['id']);release.set()
        assert manager.wait(job['id'],5)['status']=='cancelled'
        assert not paths.output(job['id']).exists()
        assert not paths.output(job['id']).with_name('wordlist.txt.part').exists()
    finally:release.set();manager.stop()


@pytest.mark.parametrize('extra', [[],['--no-ptbr'],['--no-intelligence'],
    ['--no-include-common-passwords','--no-organization-variants'],['--no-common-numbers','--no-recent-years']])
def test_cli_preset_overrides_match_application(extra):
    args=[sys.executable,'-m','mimic.cli','generate','--organization','Fictional','--preset','corporate-br',
          '--reference-year','2026','--leet','none','--separators','','--budget','quick','--selector','diverse-v1',
          '--no-banner','--quiet',*extra]
    result=subprocess.run(args,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    data={'preset':'corporate-br','organization':{'name':'Fictional'},'intelligence':{'reference_year':2026},
          'mutations':{'leet_mode':'none','separators':''},'ranking':{'enabled':True,'budget':100,'selector':'diverse-v1'}}
    for flag in extra:
        if flag=='--no-ptbr':data.setdefault('sources',{})['include_ptbr']=False
        if flag=='--no-intelligence':data['intelligence']['enabled']=False
        if flag=='--no-include-common-passwords':data.setdefault('sources',{})['include_common_passwords']=False
        if flag=='--no-organization-variants':data['organization_variants']=False
        if flag=='--no-common-numbers':data['intelligence']['common_numbers']=False
        if flag=='--no-recent-years':data['intelligence']['recent_years']=False
    assert result.stdout==''.join(x+'\n' for x in GenerationService().prepare(GenerationRequest.from_dict(data)).iter_values())


def test_cli_experimental_exhaustive_rejected():
    p=subprocess.run([sys.executable,'-m','mimic.cli','generate','--preset','corporate-br','--selector','diverse-v1'],capture_output=True)
    assert p.returncode==2 and b'finite' in p.stderr


@pytest.mark.parametrize('seed',['1','42','777'])
def test_hashseed_determinism(seed,tmp_path):
    script='''import hashlib,json
from mimic.application import GenerationRequest,GenerationService
r=GenerationRequest.from_dict({'preset':'corporate-br','organization':{'name':'Synthetic Empresa'},'intelligence':{'reference_year':2026},'mutations':{'leet_mode':'none','separators':'@!'},'ranking':{'enabled':True,'budget':100,'selector':'diverse-v1'}})
p=GenerationService().prepare(r)
print(hashlib.sha256(json.dumps([x.to_dict() for x in p.iter_results()],ensure_ascii=False).encode()).hexdigest())
'''
    a=subprocess.check_output([sys.executable,'-c',script],env={**os.environ,'PYTHONHASHSEED':seed})
    b=subprocess.check_output([sys.executable,'-c',script],env={**os.environ,'PYTHONHASHSEED':'0'})
    assert a==b


def test_selectors_share_candidates_provenance_and_original_scores(monkeypatch):
    monkeypatch.setattr(socket,'socket',lambda *_args,**_kw:pytest.fail('network'))
    monkeypatch.setattr(socket,'getaddrinfo',lambda *_args,**_kw:pytest.fail('DNS'))
    r=GenerationRequest.from_dict({'preset':'corporate-br','organization':{'name':'Imaginary'},
        'intelligence':{'reference_year':2026},'mutations':{'leet_mode':'none','separators':'@!'},
        'limits':{'max_candidates_per_word':50},'ranking':{'enabled':True,'budget':100}})
    d=replace(r,ranking=replace(r.ranking,selector='diverse-v1'))
    # Inspect actual accepted streams before either selection; Candidate equality
    # includes all Origins and Transformations, not just final password bytes.
    a=list(GenerationService().prepare(r)._claim_candidates())
    b=list(GenerationService().prepare(d)._claim_candidates())
    assert a==b
    for result in GenerationService().prepare(d).iter_results():
        assert result.candidate in a
        assert result.score==score_candidate(result.candidate,2026)


@pytest.mark.parametrize('leet,cap,expected', [
    ('none',50,{'AcmeCorpBrasil123@','Mudar@123'}),
    ('partial',256,{'AcmeCorpBrasil123@','Mudar@123','Senha2026!'}),
    ('full',5000,set())])
def test_policy_and_caps_do_not_imply_universal_diagnostic_coverage(leet,cap,expected):
    targets={'AcmeCorpBrasil123@','Mudar@123','Senha2026!'}
    r=GenerationRequest.from_dict({'preset':'corporate-br','organization':{'name':'Acme Corp Brasil'},
        'intelligence':{'reference_year':2026},'mutations':{'leet_mode':leet,'separators':'@!'},
        'limits':{'max_candidates_per_word':cap}})
    assert set(GenerationService().prepare(r).iter_values()) & targets == expected
    constrained=replace(r,policy=PolicyOptions(max_len=12))
    assert set(GenerationService().prepare(constrained).iter_values()) & targets == expected-{'AcmeCorpBrasil123@'}
