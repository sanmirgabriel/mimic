"""Gate 8 gaps: exact explanations, exhaustive cost, late cancellation and adapters."""
from dataclasses import asdict
import html
import json
import sqlite3
import threading
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from mimic.api import create_app
from mimic.application import (ApplicationError, GenerationRequest, GenerationService,
                               MutationOptions, RankingOptions, SourceOptions)
from mimic.core.candidate import Candidate, Origin, Transformation
from mimic.core.generator import Generator
from mimic.core.policy import PasswordPolicy
from mimic.jobs import JobManager
from mimic.mutators.affix import AffixMutator
from mimic.mutators.case import CaseMutator
from mimic.mutators.leet import LeetMutator
from mimic.ranking import CandidateScore, ScoreComponent
from mimic.ranking.scoring import score_candidate
from mimic.ranking.topk import select_top_k
from tests.test_ranking_adapters import csrf, request, store


@pytest.mark.parametrize('origins,steps,total,expected', [
    ((Origin('profile','nome','Ana'),Origin('knowledge','recent_year','2026')), (), 46,
     (ScoreComponent('origin.target.nome',30,'Recorded profile.nome=Ana'),
      ScoreComponent('origin.recent_year.recent_year',16,'Recorded knowledge.recent_year=2026; reference year 2026; recent-year bonus 16'))),
    ((Origin('organization','name','ACME'),Origin('knowledge','service.wordpress.token','wp'),
      Origin('knowledge','common_number','123')), (), 44,
     (ScoreComponent('origin.organization.name',22,'Recorded organization.name=ACME'),
      ScoreComponent('origin.service.service.wordpress.token',14,'Recorded knowledge.service.wordpress.token=wp'),
      ScoreComponent('origin.common_number.common_number',8,'Recorded knowledge.common_number=123'))),
    ((Origin('ready_candidate','ready.txt:1','Exact!'),), (), 50,
     (ScoreComponent('origin.ready_candidate.ready.txt:1',50,'Recorded ready_candidate.ready.txt:1=Exact!'),)),
    ((Origin('dataset','words.txt:1','seed'),), (), 4,
     (ScoreComponent('origin.dataset.words.txt:1',4,'Recorded dataset.words.txt:1=seed'),)),
    ((Origin('dataset','ptbr.reset_words:1','senha'),), (), 5,
     (ScoreComponent('origin.ptbr.ptbr.reset_words:1',5,'Recorded dataset.ptbr.reset_words:1=senha'),)),
    ((Origin('profile','nome','Ana'),), (Transformation('reverse',(('input','Ana'),)),), 18,
     (ScoreComponent('origin.target.nome',30,'Recorded profile.nome=Ana'),
      ScoreComponent('transformation.reverse',-12,'Recorded reverse: input=Ana'))),
    ((Origin('profile','nome','Ana'),), (Transformation('leet',(('from','A'),('position','0'),('to','@'))),), 28,
     (ScoreComponent('origin.target.nome',30,'Recorded profile.nome=Ana'),
      ScoreComponent('transformation.leet',-2,'Recorded leet: from=A, position=0, to=@'))),
    ((Origin('profile','nome','Ana'),), (Transformation('leet',(('from','A'),('position','0'),('to','@'))),
                                      Transformation('leet',(('from','a'),('position','2'),('to','@')))), 26,
     (ScoreComponent('origin.target.nome',30,'Recorded profile.nome=Ana'),
      ScoreComponent('transformation.leet',-2,'Recorded leet: from=A, position=0, to=@'),
      ScoreComponent('transformation.leet',-2,'Recorded leet: from=a, position=2, to=@'))),
])
def test_exact_complete_score_explanations(origins,steps,total,expected):
    candidate=Candidate('final value is irrelevant',origins,steps)
    assert score_candidate(candidate,2026) == CandidateScore(total,expected,'score-v1')


@pytest.mark.parametrize('source,fields,weight,cap', [
    ('profile',('nome','pet','empresa'),30,60),
    ('organization',('name','alias','domain'),22,44),
    ('knowledge',('service.wordpress.token','service.wordpress.role','service.mysql.token'),14,28),
])
def test_effective_caps_survive_sqlite_reload(tmp_path,source,fields,weight,cap):
    paths,repo=store(tmp_path)
    origins=tuple(Origin(source,field,'x') for field in fields)
    candidate=Candidate('x',origins+(origins[0],))
    score=score_candidate(candidate)
    assert score.total==cap and [c.delta for c in score.components]==[weight,weight,0]
    assert f'category cap {cap}' in score.components[-1].description
    assert candidate.origins==origins+(origins[0],)
    job=repo.create_job(request().to_dict(),None,None)
    repo.add_preview(job['id'],[{'sequence':1,'rank':1,'value':'x','origins':[asdict(o) for o in candidate.origins],
        'transformations':[],'score':score.total,'score_version':score.version,
        'score_components':score.to_dict()['components']}])
    row=repo.list_preview(job['id'])[0]
    assert row['score']==sum(c['delta'] for c in row['score_components'])==cap
    assert row['score_components']==score.to_dict()['components']


def test_controlled_conceptual_order_and_real_partial_leet():
    name=Origin('profile','nome','Ana')
    recent=Origin('knowledge','recent_year','2026')
    old_number=Origin('knowledge','common_number','123')
    target_year=Candidate('Ana2026',(name,recent))
    target_number=Candidate('Ana123',(name,old_number))
    service=Origin('knowledge','service.wordpress.token','wp')
    contextual=Candidate('ACMEwp2026',(Origin('organization','name','ACME'),service,recent))
    generic=Candidate('wp123',(service,old_number))
    assert score_candidate(target_year,2026).total>score_candidate(target_number,2026).total
    assert score_candidate(contextual,2026).total>score_candidate(generic,2026).total
    reversed_candidate=target_year.derive('6202anA',Transformation('reverse',(('input',target_year.value),)))
    assert score_candidate(target_year,2026).total>score_candidate(reversed_candidate,2026).total
    raw=Candidate('ace',(Origin('profile','nome','ace'),))
    mutated=list(LeetMutator('partial').mutate_candidate(raw))
    assert [c.value for c in mutated]==['ace','@ce','ac3','@c3']
    assert mutated[0] is raw
    assert [len(c.transformations) for c in mutated]==[0,1,1,2]
    assert score_candidate(mutated[0]).total>score_candidate(mutated[1]).total>score_candidate(mutated[3]).total
    # Zero substitutions now survives the composed frontier before Affix.
    generated=list(Generator(base_words=[raw],stages=(CaseMutator(),LeetMutator('partial'),
                   AffixMutator(numbers=['2026'],separators='')),policy=PasswordPolicy()).generate_candidates())
    unleeted=next(c for c in generated if c.value=='ace2026')
    assert not any(t.kind=='leet' for t in unleeted.transformations)


@pytest.mark.parametrize('method', ['iter_candidates','iter_values'])
def test_exhaustive_hot_path_needs_no_result_envelope(monkeypatch,method):
    import mimic.application.generation as module
    def forbidden(*args,**kwargs):
        pytest.fail('exhaustive projection constructed ranking metadata')
    for name in ('GenerationResult','score_candidate','select_top_k'):
        monkeypatch.setattr(module,name,forbidden)
    options=GenerationRequest(base_candidates=(Candidate('Ana'),),mutations=MutationOptions(leet_mode='none'))
    prepared=GenerationService().prepare(options)
    stream=getattr(prepared,method)()
    assert prepared.evaluated_count==0
    for other in ('iter_candidates','iter_values','iter_results'):
        with pytest.raises(ApplicationError):
            getattr(prepared,other)()
    output=list(stream)
    assert output and prepared.evaluated_count==len(output)


@pytest.mark.parametrize('budget', [1,99,250,2500,100000])
def test_numeric_custom_budgets(budget):
    options=RankingOptions.from_budget(str(budget))
    assert options==RankingOptions(True,budget)
    assert RankingOptions.from_dict(json.loads(json.dumps(options.to_dict())))==options


@pytest.mark.parametrize('budget', [0,-1,1.5,'banana',True,None])
def test_custom_budget_invalid_types(budget):
    with pytest.raises(ValueError,match='finite positive integer budget'):
        RankingOptions(True,budget)


@pytest.mark.parametrize('budget', [1,99,250,1000,1500])
def test_many_ties_match_reference_all_result_fields(budget):
    candidates=[Candidate(str(1000-i),(Origin('profile','nome','Ana'),)) for i in range(1000)]
    reference=[(i,c,score_candidate(c)) for i,c in enumerate(candidates)]
    reference=sorted(reference,key=lambda item:(-item[2].total,item[0]))[:budget]
    output=list(select_top_k(iter(candidates),budget,score_candidate))
    assert [(r.encounter_index,r.candidate,r.score,r.rank) for r in output]==[
        (i,c,score,rank) for rank,(i,c,score) in enumerate(reference,1)]


@pytest.mark.parametrize('point', ['final_sort','completion'])
def test_cancel_accepted_after_last_evaluation_wins(tmp_path,monkeypatch,point):
    paths,repo=store(tmp_path)
    entered,release=threading.Event(),threading.Event()
    prepared_plans=[]
    class Service:
        def prepare(self,options):
            prepared=GenerationService().prepare(options)
            prepared_plans.append(prepared)
            return prepared
    manager=JobManager(repo,paths,service=Service())
    if point=='final_sort':
        import mimic.ranking.topk as module
        def sorting(heap,**kwargs):
            entered.set()
            assert release.wait(5)
            return sorted(heap,**kwargs)
        monkeypatch.setattr(module,'sorted',sorting,raising=False)
    else:
        complete=repo.complete_job
        def completing(*args):
            entered.set()
            assert release.wait(5)
            return complete(*args)
        monkeypatch.setattr(repo,'complete_job',completing)
    manager.start()
    try:
        job=manager.submit(request())
        assert entered.wait(5)
        total=prepared_plans[0].evaluated_count
        assert total>0
        assert manager.cancel(job['id'])['cancel_requested']
        release.set()
        terminal=manager.wait(job['id'],5)
        assert terminal['status']=='cancelled' and terminal['evaluated_count']==total
        assert not paths.output(job['id']).exists()
        assert not paths.output(job['id']).with_name('wordlist.txt.part').exists()
        with pytest.raises(ValueError):
            manager.completed_output(job['id'])
        next_job=manager.submit(request())
        assert manager.wait(next_job['id'],5)['status']=='completed'
    finally:
        release.set()
        manager.stop()


@pytest.mark.parametrize('failure', ['scorer','checkpoint'])
def test_scan_errors_are_sanitized_and_worker_recovers(tmp_path,monkeypatch,failure):
    paths,repo=store(tmp_path)
    class Service:
        calls=0
        def prepare(self,options):
            self.calls+=1
            prepared=GenerationService().prepare(options)
            if self.calls==1:
                prepared._planned=SimpleNamespace(generator=SimpleNamespace(
                    generate_candidates=lambda:(Candidate(f'controlled-{i}') for i in range(20))))
            return prepared
    if failure=='scorer':
        import mimic.application.generation as module
        score=module.score_candidate
        def failing_score(candidate,year):
            if candidate.value=='controlled-3':
                raise RuntimeError('SECRET scorer detail')
            return score(candidate,year)
        monkeypatch.setattr(module,'score_candidate',failing_score)
    else:
        update=repo.set_evaluated_count
        failed=False
        def failing_checkpoint(*args):
            nonlocal failed
            if not failed:
                failed=True
                raise RuntimeError('SECRET checkpoint detail')
            return update(*args)
        monkeypatch.setattr(repo,'set_evaluated_count',failing_checkpoint)
    manager=JobManager(repo,paths,service=Service(),count_batch=2)
    manager.start()
    try:
        job=manager.submit(request())
        terminal=manager.wait(job['id'],5)
        assert terminal['status']=='failed' and terminal['candidate_count']==0
        assert 'SECRET' not in terminal['error']
        assert not paths.output(job['id']).exists()
        assert not paths.output(job['id']).with_name('wordlist.txt.part').exists()
        following=manager.submit(request())
        assert manager.wait(following['id'],5)['status']=='completed'
    finally:
        manager.stop()


def test_future_database_version_is_rejected_without_downgrade(tmp_path):
    paths,repo=store(tmp_path)
    with repo.database.connection() as connection:
        connection.execute('PRAGMA user_version = 999')
    with pytest.raises(RuntimeError,match='unsupported database schema version: 999'):
        repo.database.initialize()
    with sqlite3.connect(paths.database) as connection:
        assert connection.execute('PRAGMA user_version').fetchone()[0]==999


@pytest.mark.parametrize('budget', ['banana','1.5','True','None','quick','exhaustive'])
def test_web_custom_rejects_nonnumeric_presets(tmp_path,budget):
    with TestClient(create_app(data_dir=tmp_path), cookies={"mimic_locale": "en"}) as client:
        response=client.post('/generate',data={'csrf_token':csrf(client),'nome':'Ana','mode':'quick',
            'intent':'preview','output_priority':'custom','custom_budget':budget})
        assert response.status_code==422
        assert 'Custom output budget must be a positive whole number.' in response.text


def test_web_custom_submit_and_preview_laziness(tmp_path,monkeypatch):
    app=create_app(data_dir=tmp_path)
    with TestClient(app, cookies={"mimic_locale": "en"}) as client:
        form={'csrf_token':csrf(client),'mode':'quick','nome':'Ana','output_priority':'custom',
              'custom_budget':'250','reference_year':'2026','intent':'preview'}
        with monkeypatch.context() as guard:
            import mimic.application.generation as module
            def forbidden(*args,**kwargs):
                pytest.fail('preview consumed candidates or dataset')
            guard.setattr(Generator,'generate_candidates',forbidden)
            guard.setattr(module,'score_candidate',forbidden)
            def unread_dataset(*args,**kwargs):
                forbidden()
                yield  # Calling the source factory is allowed; reading it is not.
            guard.setattr(module,'stream_dataset',unread_dataset)
            preview=client.post('/generate',data=form,files={'dataset_file':('seed.txt',b'Dataset\n')})
            assert preview.status_code==200 and 'score-v1' in preview.text and '250' in preview.text
            assert app.state.repository.list_jobs()==[]
        form['intent']='generate'
        generated=client.post('/generate',data=form,follow_redirects=False)
        assert generated.status_code==303
        job_id=generated.headers['location'].split('/')[-1]
        job=app.state.job_manager.wait(job_id,10)
        assert job['status']=='completed' and job['candidate_count']==250
        assert job['request']['ranking']=={'enabled':True,'budget':250}
        assert len(client.get(f'/api/jobs/{job_id}/download').text.splitlines())==250


def test_stored_explanations_escape_html_and_do_not_rescore(tmp_path,monkeypatch):
    app=create_app(data_dir=tmp_path)
    with TestClient(app, cookies={"mimic_locale": "en"}) as client:
        hostile='<script>alert("x")</script>'
        options=request(); job=app.state.repository.create_job(options.to_dict(),None,None)
        repo=app.state.repository
        repo.start_job(job['id'])
        path=app.state.job_manager.paths.output(job['id']); path.parent.mkdir(parents=True)
        path.write_text(hostile+'\n',encoding='utf-8')
        repo.add_preview(job['id'],[{'sequence':1,'rank':1,'value':hostile,
            'origins':[asdict(Origin('profile','nome',hostile))],
            'transformations':[asdict(Transformation('case',(('mode',hostile),)))],
            'score':17,'score_version':'score-v1',
            'score_components':[asdict(ScoreComponent('stored',17,hostile))]}])
        assert repo.complete_job(job['id'],1,str(path))
        import mimic.application.generation as module
        monkeypatch.setattr(module,'score_candidate',lambda *args:pytest.fail('history rescored'))
        detail=client.get('/jobs/'+job['id']).text
        assert hostile not in detail and html.unescape(detail).count(hostile)>=4
        assert 'Why this priority?' in detail and 'Origins' in detail and 'Transformations' in detail
        assert 'Score 17' in detail and 'score-v1' in detail
        preview=client.get(f'/api/jobs/{job["id"]}/candidates').json()[0]
        assert preview['score']==17 and preview['score_components'][0]['description']==hostile


def test_ranked_api_and_submit_snapshot_isolation(tmp_path):
    app=create_app(data_dir=tmp_path)
    with TestClient(app, cookies={"mimic_locale": "en"}) as client:
        payload=request(100).to_dict()
        response=client.post('/api/jobs',json={'request':payload})
        assert response.status_code==201
        payload['ranking']['budget']=1
        job=app.state.job_manager.wait(response.json()['id'])
        assert job['request']['ranking']=={'enabled':True,'budget':100}
        assert job['status']=='completed'
        # Test submit's separate snapshot of the caller's mutable request.
        options=request(99)
        submitted=app.state.job_manager.submit(options)
        options.ranking=RankingOptions(True,1)
        frozen=app.state.job_manager.wait(submitted['id'])
        assert frozen['request']['ranking']=={'enabled':True,'budget':99}


def test_first_core_derivation_is_scored_without_rewriting(tmp_path,monkeypatch):
    ready=tmp_path/'ready.txt'
    ready.write_text('Ana\n',encoding='utf-8')
    options=GenerationRequest(base_candidates=(Candidate('Ana',(Origin('dataset','first:1','Ana'),)),),
        sources=SourceOptions(ready_candidate_paths=(str(ready),)),
        mutations=MutationOptions(leet_mode='none'),ranking=RankingOptions(True,100))
    exhaustive=GenerationRequest.from_dict({**options.to_dict(),'ranking':{'enabled':False,'budget':None}})
    reference=list(GenerationService().prepare(exhaustive).iter_candidates())
    core_output=[]
    original=Generator.generate_candidates
    def observed_core(generator):
        for candidate in original(generator):
            core_output.append(candidate)
            yield candidate
    monkeypatch.setattr(Generator,'generate_candidates',observed_core)
    import mimic.application.generation as module
    score=module.score_candidate
    def observed_score(candidate,year):
        assert candidate is core_output[-1]
        before=asdict(candidate)
        result=score(candidate,year)
        assert asdict(candidate)==before
        return result
    monkeypatch.setattr(module,'score_candidate',observed_score)
    results=list(GenerationService().prepare(options).iter_results())
    assert core_output==reference
    result=next(r for r in results if r.candidate.value=='Ana')
    assert result.candidate is core_output[0]
    assert result.candidate.origins==(Origin('dataset','first:1','Ana'),)
    assert result.score.total==4  # A later ready origin (+50) never replaces this cause.


def test_exhaustive_rich_api_claims_immediately():
    prepared=GenerationService().prepare(GenerationRequest(base_candidates=(Candidate('Ana'),)))
    prepared.iter_results()
    assert prepared.evaluated_count==0
    for method in ('iter_results','iter_candidates','iter_values'):
        with pytest.raises(ApplicationError):
            getattr(prepared,method)()
