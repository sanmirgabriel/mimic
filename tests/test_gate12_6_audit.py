"""Independent adversarial Gate 12.6 checks; no selection-policy tuning."""
from collections import Counter
from dataclasses import asdict, replace
import gc
from itertools import permutations
import json
import random
import re
import subprocess
import sys
import tracemalloc
import weakref

import pytest
from fastapi.testclient import TestClient

from mimic.api import create_app
from mimic.application import GenerationRequest, GenerationService, SourceOptions, IntelligenceOptions, RankingOptions
from mimic.application.errors import InvalidGenerationRequest
from mimic.core.candidate import Candidate, Origin, Transformation
from mimic.core.generator import Generator
from mimic.core.seed import Seed
from mimic.persistence import DataPaths, Database, Repository
from mimic.ranking.models import CandidateScore, GenerationResult, Selection
from mimic.ranking.diverse import select_diverse
from mimic.ranking.families import FAMILIES, candidate_family
from mimic.ranking.scoring import score_candidate


def term(source,field,value='opaque'):
    return Origin(source,field,value)


def step(kind,**params):
    return Transformation(kind,tuple(params.items()))


ORG=term('organization','name');YEAR=term('knowledge','recent_year','2026')
NUM=term('knowledge','common_number','123');PT=term('dataset','ptbr.reset_words:1')
AFF=step('affix',token='opaque')
# Oracle labels come from explicit constructions, never from the classifier.
FIXTURES=(
 ('ready',(term('knowledge','common_password'),),()),
 ('organization-role',(ORG,), (step('knowledge_template',template='organization_role'),)),
 ('organization-service',(ORG,), (step('knowledge_template',template='organization_service_reverse'),)),
 ('service-role',(),(step('knowledge_template',template='service_role_reverse'),)),
 ('combined',(ORG,PT),(step('combine'),)),
 ('organization-year',(ORG,YEAR),(AFF,)),
 ('organization-number',(ORG,NUM),(AFF,)),
 ('organization-other',(ORG,),()),
 ('ptbr-year',(PT,YEAR),(AFF,)),
 ('ptbr-number',(PT,NUM),(AFF,)),
 ('ptbr-other',(PT,),()),
 ('other',(),()),
)


@pytest.mark.parametrize('family,origins,steps',FIXTURES)
def test_independent_all_families_and_private_literal_invariance(family,origins,steps):
    for value in ('Mudar@123','AcmeCorpBrasil123@','PRIVATE /home/private/domain.test 2026'):
        assert candidate_family(Candidate(value,origins,steps))==family
    assert family in FAMILIES


@pytest.mark.parametrize('seed',range(5))
@pytest.mark.parametrize('size',[0,1,12,144,1001])
def test_selector_independent_labelled_oracle_all_bounds(seed,size):
    rng=random.Random(seed);entries=[]
    for i in range(size):
        family,origins,steps=(FIXTURES[i] if size==12 else
                              FIXTURES[7] if size==144 and seed==0 else rng.choice(FIXTURES))
        candidate=Candidate(f'private-{i}',origins,steps)
        entries.append((candidate,family,rng.randrange(-8,4)))
    # Sort whole small test stream; use labelled partitions and selection by
    # set membership. No heap, selector or classifier in reference algorithm.
    order=sorted(range(size),key=lambda i:(-entries[i][2],i))
    best={}
    for i in order:best.setdefault(entries[i][1],i)
    for k in sorted({1,2,11,12,13,50,1001,max(1,size)}):
        reserve=set(list(best.values())[:k]);expected=set(reserve)
        for i in order:
            if len(expected)>=min(k,size):break
            expected.add(i)
        calls=Counter();scores={c.value:CandidateScore(score,()) for c,_,score in entries}
        def scorer(c):calls[c.value]+=1;return scores[c.value]
        output=list(select_diverse((e[0] for e in entries),k,scorer))
        ids=[r.encounter_index for r in output]
        assert ids==[i for i in order if i in expected]
        assert len(ids)==len(set(ids))==min(k,size)
        assert len({r.candidate.value for r in output})==len(output)
        assert all(n==1 for n in calls.values()) and sum(calls.values())==size
        for rank,r in enumerate(output,1):
            assert r.rank==rank and r.candidate is entries[r.encounter_index][0]
            assert r.score is scores[r.candidate.value]
            assert r.selection.family==entries[r.encounter_index][1]
            assert r.selection.reason==('family-representative' if r.encounter_index in reserve else 'score-fill')
        if k>=len(best) and size:
            assert len(set(order[:k])-set(ids))<=len(best)-1


def test_rare_late_family_negative_scores_and_loss_of_cutoff_target():
    values=[Candidate(str(i),(ORG,)) for i in range(100)] + [Candidate('rare')]
    scores={c.value:CandidateScore(-i,()) for i,c in enumerate(values)}
    output=list(select_diverse(iter(values),100,lambda c:scores[c.value]))
    retained={r.candidate.value for r in output}
    assert '99' not in retained and 'rare' in retained
    assert len({r.selection.family for r in output})==2
    # Explicit adversarial holdouts: recall worsens or stays unchanged even
    # as families improve. Denominators include a never-generated target.
    for holdout,before,after in [({'99'},1,0),({'0'},1,1),({'absent'},0,0),({'99','absent'},1,0)]:
        assert len(holdout & {c.value for c in values[:100]})==before
        assert len(holdout & retained)==after


def test_duplicate_values_are_deduped_by_engine_first_cause():
    first=Candidate('same',(ORG,));second=Candidate('same',(PT,))
    engine=Generator([],[],seeds=[Seed(first),Seed(second),Seed(Candidate('other'))])
    accepted=list(engine.generate_candidates())
    assert accepted==[first,Candidate('other')]
    output=list(select_diverse(accepted,100,score_candidate))
    assert len(output)==2 and output[0].candidate is first


def test_equivalent_metadata_orders_multiple_affixes_and_template_precedence():
    origins=(ORG,PT,YEAR,NUM)
    steps=(AFF,step('affix',placement='prefix'),step('leet',position='1'),step('reverse'))
    for os in permutations(origins):
        for ss in (steps,steps[::-1]):
            assert candidate_family(Candidate('irrelevant',os,ss))=='organization-year'
    mixed=[step('knowledge_template',template=v) for v in ('service_role','organization_service','organization_role_reverse')]
    for ss in permutations(mixed):
        assert candidate_family(Candidate('irrelevant',origins,ss))=='organization-role'
    for source in ('profile','target','context_file'):
        field='file:empresa' if source=='context_file' else 'empresa'
        assert candidate_family(Candidate('x',(term(source,field),YEAR),(AFF,)))=='organization-year'
    assert candidate_family(Candidate('x',(ORG,YEAR),()))=='organization-other'
    assert candidate_family(Candidate('x',(),(step('unknown',private='secret'),)))=='other'
    with pytest.raises(TypeError):Candidate('x',('bad',))
    with pytest.raises(TypeError):step('affix',token=123)


@pytest.mark.parametrize('k',[1,25,250])
def test_auxiliary_memory_grows_with_k_not_n_and_closes_on_scan_error(k):
    def peak(n):
        gc.collect();tracemalloc.start()
        list(select_diverse((Candidate(str(i),(ORG,)) for i in range(n)),k,lambda _:CandidateScore(1,())))
        _,value=tracemalloc.get_traced_memory();tracemalloc.stop();return value
    small=peak(2000);large=peak(20000)
    assert large<small+200_000
    closed=[];refs=[]
    def stream():
        try:
            for i in range(100):
                c=Candidate(str(i),(ORG,));refs.append(weakref.ref(c));yield c
        finally:closed.append(True)
    def fail(c):
        if c.value=='50':raise RuntimeError('cancelled')
        return CandidateScore(1,())
    result=select_diverse(stream(),k,fail)
    with pytest.raises(RuntimeError):next(result)
    gc.collect()
    assert closed==[True] and all(r() is None for r in refs)


@pytest.mark.parametrize('section,key', [('sources','include_ptbr'),('sources','include_common_passwords'),
 ('intelligence','enabled'),('intelligence','common_numbers'),('intelligence','recent_years'),
 ('intelligence','corporate_roles'),(None,'organization_variants')])
@pytest.mark.parametrize('value',[False,True])
def test_all_preset_overrides_roundtrip_without_mutating_input(section,key,value):
    raw={'preset':'corporate-br','intelligence':{'reference_year':2026}}
    if section:raw.setdefault(section,{})[key]=value
    else:raw[key]=value
    saved=json.dumps(raw,sort_keys=True)
    request=GenerationRequest.from_dict(raw)
    for _ in range(5):
        assert (getattr(getattr(request,section),key) if section else request.organization_variants) is value
        request=GenerationRequest.from_dict(json.loads(json.dumps(request.to_dict())))
    assert json.dumps(raw,sort_keys=True)==saved


@pytest.mark.parametrize('raw',[None,[],False,3,'bad'])
@pytest.mark.parametrize('section',['mutations','policy','limits'])
def test_malformed_preset_option_sections_rejected_as_request_errors(section,raw):
    with pytest.raises(InvalidGenerationRequest):
        GenerationRequest.from_dict({'preset':'corporate-br',section:raw})


@pytest.mark.parametrize('changes',[
 {'family':'/home/private/password'}, {'family':'x'*10000}, {'family':[]},
 {'family_version':'candidate-family-v9'}, {'family_version':None},
 {'selector':'diverse-v9'}, {'selector':False}, {'reason':'future'}, {'reason':{}},
])
def test_selection_metadata_rejects_unknown_private_or_malformed_fields(changes):
    data={'family':'other','family_version':'candidate-family-v1','selector':'diverse-v1','reason':'score-fill',**changes}
    with pytest.raises(ValueError):Selection(**data)


@pytest.mark.parametrize('bad',[{},[],False,0,'private',{'family':'other'}])
def test_result_selection_cannot_silently_disappear_or_accept_malformed_metadata(bad):
    data=GenerationResult(Candidate('x')).to_dict();data['selection']=bad
    with pytest.raises(ValueError):GenerationResult.from_dict(data)


def test_result_selection_unknown_keys_rejected_without_echoing_private_data():
    data=GenerationResult(Candidate('x')).to_dict()
    data['selection']={'family':'other','family_version':'candidate-family-v1',
                       'selector':'diverse-v1','reason':'score-fill','PRIVATE-SENSITIVE':'secret'}
    with pytest.raises(ValueError,match='selection metadata') as error:GenerationResult.from_dict(data)
    assert 'PRIVATE-SENSITIVE' not in str(error.value)


def store(tmp_path):
    paths=DataPaths(tmp_path);db=Database(paths);db.initialize();return Repository(db)


def preview_row(components):
    return {'sequence':1,'value':'x','origins':[],'transformations':[],
            'rank':1,'score':0,'score_version':'score-v1','score_components':components}


@pytest.mark.parametrize('payload',[
 {}, {'components':[]}, {'selection':{}}, {'components':None,'selection':{}},
 {'components':[],'selection':{'family':'other','reason':'future','selector':'diverse-v1','family_version':'candidate-family-v1'}},
 {'components':[],'selection':{'family':'other','reason':'score-fill','selector':'future','family_version':'candidate-family-v1'}},
 {'components':[{'code':'x','delta':True,'description':'x'}],'selection':{'family':'other','reason':'score-fill','selector':'diverse-v1','family_version':'candidate-family-v1'}},
])
def test_malformed_persisted_envelope_is_rejected_with_fixed_error(tmp_path,payload):
    repo=store(tmp_path);job=repo.create_job(GenerationRequest().to_dict(),None,None)
    repo.add_preview(job['id'],[preview_row([])])
    with repo.database.connection() as con:
        con.execute('UPDATE candidate_preview SET score_components=?',(json.dumps(payload),))
    with pytest.raises(ValueError,match='selection explanation'):repo.list_preview(job['id'])


def test_legacy_and_new_explanations_roundtrip_without_component_changes(tmp_path):
    repo=store(tmp_path);job=repo.create_job(GenerationRequest().to_dict(),None,None)
    component={'code':'recorded','delta':-2,'description':'private cause'}
    rows=[preview_row([component]),{**preview_row([component]),'sequence':2,
          'selection':asdict(Selection('other','score-fill','candidate-family-v1'))}]
    repo.add_preview(job['id'],rows);actual=repo.list_preview(job['id'])
    assert actual[0]['score_components']==actual[1]['score_components']==[component]
    assert 'selection' not in actual[0] and actual[1]['selection']==rows[1]['selection']
    assert Repository(repo.database).list_preview(job['id'])==actual


def test_help_explains_non_nested_diverse_budget_prefixes():
    output=subprocess.check_output([sys.executable,'-m','mimic.cli','generate','--help'],text=True)
    assert 'prefix' in output and 'diverse-v1' in output


def test_web_copy_explains_non_nested_diverse_budget_prefixes():
    from mimic.web.i18n import translate
    assert 'prefix' in translate('en','diversity.help')
    assert 'primeir' in translate('pt-BR','diversity.help')


@pytest.mark.parametrize('raw',['{','false','42','"private/path"', '{"components":[]}'])
def test_corrupt_preview_api_and_web_reject_without_exposing_data(tmp_path,raw):
    with TestClient(create_app(data_dir=tmp_path),raise_server_exceptions=False) as client:
        repo=client.app.state.repository
        job=repo.create_job(GenerationRequest().to_dict(),None,None)
        repo.add_preview(job['id'],[preview_row([])])
        with repo.database.connection() as con:
            con.execute('UPDATE candidate_preview SET score_components=?',(raw,))
        api=client.get(f"/api/jobs/{job['id']}/candidates")
        assert api.status_code==409 and api.json()=={'detail':'invalid selection explanation'}
        web=client.get(f"/jobs/{job['id']}")
        assert web.status_code==409 and 'private/path' not in web.text


def test_metadata_large_component_preserved_but_private_family_rejected(tmp_path):
    repo=store(tmp_path);job=repo.create_job(GenerationRequest().to_dict(),None,None)
    row=preview_row([{'code':'recorded','delta':0,'description':'A'*100000}])
    row['selection']=asdict(Selection('other','score-fill','candidate-family-v1'))
    repo.add_preview(job['id'],[row])
    assert repo.list_preview(job['id'])[0]['score_components']==row['score_components']
    row['sequence']=2;row['selection']['family']='A'*100000
    with pytest.raises(ValueError,match='selection explanation'):repo.add_preview(job['id'],[row])


def test_non_nested_prefixes_are_an_actual_selection_outcome():
    candidates=[Candidate(str(i),(ORG,)) for i in range(2000)]+[Candidate('rare')]
    short=list(select_diverse(candidates,100,lambda _:CandidateScore(0,())))
    long=list(select_diverse(candidates,1000,lambda _:CandidateScore(0,())))
    assert 'rare' in [r.candidate.value for r in short]
    assert 'rare' not in [r.candidate.value for r in long[:100]]
    assert short!=long[:100]


@pytest.mark.parametrize('locale',['pt-BR','en'])
def test_web_without_js_explicit_false_and_error_restoration_and_lazy_preview(tmp_path,locale,monkeypatch):
    import mimic.application.generation as generation
    def forbidden(*_a,**_kw):pytest.fail('preview executed candidates or opened corpus')
    monkeypatch.setattr(Generator,'generate_candidates',forbidden)
    monkeypatch.setattr(generation,'stream_dataset',forbidden)
    with TestClient(create_app(data_dir=tmp_path),cookies={'mimic_locale':locale}) as client:
        html=client.get('/generate').text
        token=re.search(r'name="csrf_token" value="([^"]+)"',html)[1]
        base={'csrf_token':token,'nome':'Synthetic','preset':'corporate-br-v1','preset_options':'custom',
              'intelligence_form':'1','organization_variants_form':'1','selector':'diverse-v1',
              'output_priority':'quick','reference_year':'2026','intent':'preview'}
        response=client.post('/generate',data=base)
        assert response.status_code==200 and 'candidate-family-v1' in response.text
        for key in ('include_ptbr','include_common_passwords','intelligence_enabled','organization_variants'):
            assert f'name="{key}" checked' not in response.text
        bad=client.post('/generate',data={**base,'reference_year':'bad'})
        assert bad.status_code==422 and 'value="custom" selected' in bad.text
        assert 'value="diverse-v1" selected' in bad.text
        assert 'name="include_ptbr" checked' not in bad.text
        assert client.post('/generate',data={**base,'preset_options':'defaults'}).status_code==200


def test_default_and_preset_ready_dedup_causes_stay_distinct(tmp_path):
    ready=tmp_path/'ready.txt';ready.write_text('Mudar@123\nmudar\n')
    seed=tmp_path/'seed.txt';seed.write_text('Mudar\nMudar\n')
    r=GenerationRequest.from_dict({'preset':'corporate-br','sources':{'dataset_paths':[str(seed)],'ready_candidate_paths':[str(ready)]},
      'intelligence':{'reference_year':2026},'mutations':{'leet_mode':'none','separators':'@!'},'limits':{'max_candidates_per_word':256}})
    targets={c.value:c for c in GenerationService().prepare(r).iter_candidates() if c.value in {'Mudar@123','mudar','Mudar123'}}
    assert targets['Mudar@123'].origins[0].source=='ready_candidate'
    assert targets['mudar'].origins[0].source=='ready_candidate'
    assert not targets['Mudar@123'].transformations
    assert targets['Mudar123'].origins[0].field.startswith(str(seed))
    without=replace(r,sources=replace(r.sources,ready_candidate_paths=(),dataset_paths=()))
    targets={c.value:c for c in GenerationService().prepare(without).iter_candidates() if c.value in {'Mudar@123','mudar'}}
    assert candidate_family(targets['Mudar@123'])=='ptbr-number'
    assert targets['mudar'].origins==(term('knowledge','common_password','mudar'),)


@pytest.mark.parametrize('section,key',[('sources','include_ptbr'),('sources','include_common_passwords'),
 ('intelligence','enabled'),('intelligence','common_numbers'),('intelligence','recent_years'),
 ('intelligence','corporate_roles'),(None,'organization_variants')])
def test_job_freezes_every_false_override_and_year_even_after_caller_edits(tmp_path,section,key,monkeypatch):
    from mimic.jobs import JobManager
    import mimic.application.requests as module
    class FutureDate:
        @staticmethod
        def today():return type('Future',(),{'year':2099})()
    raw={'preset':'corporate-br','organization':{'name':'Synthetic'},'intelligence':{'reference_year':2026},
         'ranking':{'enabled':True,'budget':30,'selector':'diverse-v1'},
         'mutations':{'leet_mode':'none','separators':''},'limits':{'max_candidates_per_word':50}}
    if section:raw.setdefault(section,{})[key]=False
    else:raw[key]=False
    r=GenerationRequest.from_dict(raw);snapshot=json.loads(json.dumps(r.to_dict()))
    repo=store(tmp_path);manager=JobManager(repo,repo.database.paths);manager.start()
    try:
        job=manager.submit(r);r.preset='invalid-after-submit';r.sources=SourceOptions();r.organization.name='Changed'
        monkeypatch.setattr(module,'date',FutureDate)
        completed=manager.wait(job['id'],10)
        assert completed['status']=='completed' and completed['request']==snapshot
        assert completed['request']['intelligence']['reference_year']==2026
        saved=GenerationRequest.from_dict(completed['request'])
        assert (getattr(getattr(saved,section),key) if section else saved.organization_variants) is False
        body=manager.completed_output(job['id']).read_bytes();rows=repo.list_preview(job['id'])
    finally:manager.stop()
    restarted=JobManager(repo,repo.database.paths);restarted.start()
    try:
        assert restarted.completed_output(job['id']).read_bytes()==body
        assert repo.list_preview(job['id'])==rows
    finally:restarted.stop()


@pytest.mark.parametrize('data',[{'preset':'corporate-br-v9'},
 {'preset':'corporate-br','mutations':[]},
 {'ranking':{'enabled':True,'budget':10,'selector':'diverse-v9'}},
 {'ranking':{'enabled':True,'budget':10,'selector':'diverse-v1','family_version':'candidate-family-v9'}},
 {'ranking':{'selector':'diverse-v1'}},
 {'preset':True}])
def test_unknown_versions_and_malformed_api_inputs_are_controlled(tmp_path,data):
    with TestClient(create_app(data_dir=tmp_path)) as client:
        assert client.post('/api/jobs',json={'request':data}).status_code==422
        assert client.app.state.repository.list_jobs()==[]


def test_hostile_organization_preview_is_escaped_and_new_family_ids_are_fixed(tmp_path):
    hostile='<img src=x onerror="window.OWNED=1">'
    with TestClient(create_app(data_dir=tmp_path)) as client:
        organization=client.post('/api/organizations',json={'name':hostile,'aliases':['重复','重复','İ'*2000]}).json()
        page=client.get('/generate').text;token=re.search(r'name="csrf_token" value="([^"]+)"',page)[1]
        preview=client.post('/generate',data={'csrf_token':token,'preset':'corporate-br-v1','mode':'organization',
           'organization_id':organization['id'],'selector':'diverse-v1','output_priority':'quick','intent':'preview'})
        assert preview.status_code==200 and hostile not in preview.text and '&lt;img' in preview.text
        r=GenerationRequest.from_dict({'preset':'corporate-br','organization':{'name':hostile,'aliases':['重复','重复']},
           'intelligence':{'reference_year':2026},'mutations':{'leet_mode':'none'},'limits':{'max_candidates_per_word':50},
           'ranking':{'enabled':True,'budget':100,'selector':'diverse-v1'}})
        assert all(result.selection.family in FAMILIES for result in GenerationService().prepare(r).iter_results())
