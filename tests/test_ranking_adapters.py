"""Persisted ranking, real v1 migration and cooperative worker lifecycle."""
from dataclasses import asdict
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from mimic.api import create_app
from mimic.application import (GenerationRequest, GenerationService, MutationOptions, RankingOptions,
                               IntelligenceOptions, SourceOptions)
from mimic.core.candidate import Candidate, Origin
from mimic.domain.models import Organization
from mimic.jobs import JobManager
from mimic.persistence import DataPaths, Database, Repository
from mimic.ranking import CandidateScore


def request(budget=10):
    return GenerationRequest(base_candidates=(Candidate('Ana',(Origin('manual','nome','Ana'),)),),
                             mutations=MutationOptions(leet_mode='none',separators=''),
                             ranking=RankingOptions(True,budget))


def store(path):
    paths = DataPaths(path)
    database = Database(paths)
    database.initialize()
    return paths, Repository(database)


def test_ranked_job_preview_and_output_are_the_final_ranking(tmp_path):
    paths, repo = store(tmp_path)
    options = GenerationRequest(organization=Organization('ACME'),
        intelligence=IntelligenceOptions(reference_year=2026,service_profiles=('wordpress',)),
        mutations=MutationOptions(leet_mode='none',separators=''),ranking=RankingOptions(True,250))
    expected = list(GenerationService().prepare(options).iter_results())
    manager = JobManager(repo,paths)
    manager.start()
    try:
        job = manager.submit(options)
        complete = manager.wait(job['id'])
        assert complete['status'] == 'completed'
        assert complete['candidate_count'] == 250 < complete['evaluated_count']
        values = manager.completed_output(job['id']).read_text().splitlines()
        assert values == [r.candidate.value for r in expected]
        preview = repo.list_preview(job['id'])
        assert len(preview) == 200
        assert [p['value'] for p in preview] == values[:200]
        for row, result in zip(preview,expected):
            assert row['rank'] == result.rank
            assert row['score'] == result.score.total
            assert row['score_version'] == 'score-v1'
            assert row['score_components'] == result.score.to_dict()['components']
            assert row['origins'] == [asdict(o) for o in result.candidate.origins]
            rebuilt = CandidateScore.from_dict({'total':row['score'],'version':row['score_version'],
                                                'components':row['score_components']})
            assert rebuilt == result.score
    finally:
        manager.stop()
    restarted = JobManager(repo, paths)
    restarted.start()
    try:
        assert repo.list_preview(job['id']) == preview
        assert restarted.completed_output(job['id']).read_text().splitlines() == values
    finally:
        restarted.stop()


@pytest.mark.parametrize('mode', ['cancel','failure'])
def test_interrupt_ranked_scan_and_next_job_succeeds(tmp_path,mode):
    paths, repo = store(tmp_path)
    entered, release = threading.Event(), threading.Event()
    class Service:
        calls = 0
        def prepare(self, options):
            self.calls += 1
            prepared = GenerationService().prepare(options)
            if self.calls == 1:
                def stream():
                    for index in range(1000000):
                        if index == 32:
                            entered.set()
                            release.wait(5)
                            if mode == 'failure':
                                raise RuntimeError('SECRET internal source path')
                        yield Candidate(str(index))
                prepared._planned = SimpleNamespace(generator=SimpleNamespace(generate_candidates=stream))
            return prepared
    manager = JobManager(repo,paths,service=Service(),count_batch=10)
    manager.start()
    try:
        job = manager.submit(request())
        assert entered.wait(5)
        running = repo.get_job(job['id'])
        assert running['evaluated_count'] >= 30 and running['candidate_count'] == 0
        assert paths.output(job['id']).with_name('wordlist.txt.part').exists()
        if mode == 'cancel':
            manager.cancel(job['id'])
        release.set()
        terminal = manager.wait(job['id'],5)
        assert terminal['status'] == ('cancelled' if mode == 'cancel' else 'failed')
        assert terminal['candidate_count'] == 0 and terminal['evaluated_count'] == 32
        assert 'SECRET' not in (terminal['error'] or '')
        assert not paths.output(job['id']).exists()
        assert not paths.output(job['id']).with_name('wordlist.txt.part').exists()
        with pytest.raises(ValueError):
            manager.completed_output(job['id'])
        following = manager.submit(request())
        assert manager.wait(following['id'],5)['status'] == 'completed'
        assert manager.completed_output(following['id']).is_file()
    finally:
        release.set()
        manager.stop()


def test_real_v1_database_migration_preserves_records(tmp_path):
    paths = DataPaths(tmp_path)
    historical_id = str(uuid4())
    output = paths.output(historical_id)
    output.parent.mkdir(parents=True)
    output.write_text('Ana\n', encoding='utf-8')
    # Actual v1 column definitions: no ranking fields or evaluated_count.
    with sqlite3.connect(paths.database) as connection:
        connection.executescript('''
        CREATE TABLE engagements(id TEXT PRIMARY KEY,name TEXT NOT NULL,description TEXT);
        CREATE TABLE organizations(id TEXT PRIMARY KEY,engagement_id TEXT REFERENCES engagements(id) ON DELETE RESTRICT,
          name TEXT NOT NULL,aliases_json TEXT NOT NULL,locations_json TEXT NOT NULL,
          keywords_json TEXT NOT NULL,relevant_dates_json TEXT NOT NULL,domains_json TEXT NOT NULL);
        CREATE TABLE targets(id TEXT PRIMARY KEY,engagement_id TEXT REFERENCES engagements(id) ON DELETE RESTRICT,
          organization_id TEXT REFERENCES organizations(id) ON DELETE RESTRICT,name TEXT NOT NULL,profile_json TEXT NOT NULL);
        CREATE TABLE jobs(id TEXT PRIMARY KEY,status TEXT NOT NULL,request_json TEXT NOT NULL,
          target_id TEXT REFERENCES targets(id) ON DELETE RESTRICT,engagement_id TEXT REFERENCES engagements(id) ON DELETE RESTRICT,
          created_at TEXT NOT NULL,started_at TEXT,finished_at TEXT,candidate_count INTEGER NOT NULL DEFAULT 0,
          error TEXT,cancel_requested INTEGER NOT NULL DEFAULT 0,output_path TEXT);
        CREATE TABLE candidate_preview(job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,sequence INTEGER NOT NULL,
          value TEXT NOT NULL,origins_json TEXT NOT NULL,transformations_json TEXT NOT NULL,
          PRIMARY KEY(job_id,sequence));
        CREATE INDEX jobs_created_idx ON jobs(created_at DESC);
        PRAGMA user_version = 1;
        ''')
        connection.execute("INSERT INTO engagements VALUES('e','Audit',NULL)")
        connection.execute("INSERT INTO organizations VALUES('o','e','ACME','[]','[]','[]','[]','[]')")
        connection.execute("INSERT INTO targets VALUES('t','e','o','Ana',?)",(json.dumps({'nome':'Ana'}),))
        old = request().to_dict(); old.pop('ranking')
        connection.execute("INSERT INTO jobs(id,status,request_json,target_id,engagement_id,created_at,candidate_count,output_path) VALUES(?,'completed',?,'t','e','2026-01-01',1,?)",(historical_id,json.dumps(old),str(output)))
        connection.execute("INSERT INTO candidate_preview VALUES(?,1,'Ana',?,?)",(historical_id,json.dumps([asdict(Origin('profile','nome','Ana'))]),'[]'))
    database = Database(paths); database.initialize(); database.initialize()
    repo = Repository(database)
    assert repo.get_engagement('e')['name'] == 'Audit'
    assert repo.get_organization('o')['name'] == 'ACME'
    assert repo.target_domain('t').organization.name == 'ACME'
    historical = repo.get_job(historical_id)
    assert historical['status'] == 'completed' and historical['candidate_count'] == 1
    assert historical['evaluated_count'] is None
    assert not GenerationRequest.from_dict(historical['request']).ranking.enabled
    preview = repo.list_preview(historical_id)[0]
    assert preview['value'] == 'Ana' and preview['origins'][0]['source'] == 'profile'
    assert all(preview[field] is None for field in ('rank','score','score_version','score_components'))
    with database.connection() as connection:
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 2
        assert len(connection.execute('SELECT * FROM candidate_preview').fetchall()) == 1
    # Existing completed files survive migration and repeated application startup.
    for _ in range(2):
        with TestClient(create_app(repository=repo), cookies={"mimic_locale": "en"}) as client:
            assert client.get(f'/api/jobs/{historical_id}/download').text == 'Ana\n'
            assert client.get(f'/api/jobs/{historical_id}/candidates').json()[0] == preview
            page = client.get(f'/jobs/{historical_id}').text
            assert 'Unknown (historical)' in page and 'Ana' in page


def csrf(client):
    return re.search(r'name="csrf_token" value="([^"]+)"',client.get('/generate').text)[1]


def test_web_preview_ranked_job_download_and_historical_explanation(tmp_path,monkeypatch):
    app = create_app(data_dir=tmp_path)
    with TestClient(app, cookies={"mimic_locale": "en"}) as client:
        page = client.get('/generate').text
        assert 'value="exhaustive" selected' in page and 'Output priority' in page
        organization = client.post('/api/organizations',json={'name':'ACME'}).json()
        form = {'csrf_token':csrf(client),'mode':'organization','organization_id':organization['id'],
                'service_profiles':'wordpress','reference_year':'2026','output_priority':'focused',
                'leet_mode':'none','separators':'','intent':'preview'}
        # Preparation is a config preview: scoring would fail if accidentally invoked.
        import mimic.application.generation as module
        real = module.score_candidate
        monkeypatch.setattr(module,'score_candidate',lambda *args: pytest.fail('preview scored candidates'))
        response = client.post('/generate',data=form)
        assert response.status_code == 200
        assert 'Focused' in response.text and 'score-v1' in response.text
        assert app.state.repository.list_jobs() == []
        monkeypatch.setattr(module,'score_candidate',real)
        form['intent']='generate'
        response = client.post('/generate',data=form,follow_redirects=False)
        assert response.status_code == 303
        job_id=response.headers['location'].split('/')[-1]
        job=app.state.job_manager.wait(job_id,10)
        assert job['status'] == 'completed' and job['candidate_count'] == 1000
        monkeypatch.setattr(module,'score_candidate',lambda *args: pytest.fail('history was rescored'))
        # Stored explanation remains authoritative even if a future model changes.
        with app.state.repository.database.connection() as connection:
            connection.execute("UPDATE candidate_preview SET score_version='score-historical' WHERE job_id=?",(job_id,))
        detail = client.get('/jobs/'+job_id)
        assert 'Why this priority?' in detail.text and 'score-historical' in detail.text
        assert 'Candidates evaluated' in detail.text and 'Candidates retained' in detail.text
        assert 'Ranked output order' in detail.text and 'Origins' in detail.text and 'Transformations' in detail.text
        preview=client.get(f'/api/jobs/{job_id}/candidates').json()
        assert [p['rank'] for p in preview] == list(range(1,201))
        download = client.get(f'/api/jobs/{job_id}/download')
        assert download.status_code == 200 and len(download.text.splitlines()) == 1000
        assert download.text.splitlines()[:200] == [p['value'] for p in preview]
        custom={**form,'output_priority':'custom','custom_budget':'0','intent':'preview'}
        assert client.post('/generate',data=custom).status_code == 422
        custom['custom_budget']='2500'
        assert client.post('/generate',data=custom).status_code == 200


def test_old_api_request_exhaustive_and_invalid_ranked_request(tmp_path):
    app=create_app(data_dir=tmp_path)
    with TestClient(app, cookies={"mimic_locale": "en"}) as client:
        old=request().to_dict(); old.pop('ranking')
        submitted=client.post('/api/jobs',json={'request':old})
        assert submitted.status_code == 201
        job=app.state.job_manager.wait(submitted.json()['id'])
        assert job['status'] == 'completed'
        assert job['evaluated_count'] == job['candidate_count']
        assert not job['request']['ranking']['enabled']
        assert all(p['score'] is None and p['rank'] is None
                   for p in app.state.repository.list_preview(job['id']))
        for config in [dict(enabled=True),dict(enabled=True,budget=0),dict(enabled=True,budget=True)]:
            assert client.post('/api/jobs',json={'request':{**old,'ranking':config}}).status_code == 422


@pytest.mark.parametrize('budget', ['quick','focused','balanced','large','2500','exhaustive'])
def test_cli_budget_and_debug_keep_plain_output(tmp_path,budget):
    args=[sys.executable,'-B','-m','mimic.cli','generate','-n','Ana','--no-intelligence',
          '--leet','none','--separators','','--budget',budget,'--debug','--quiet','--no-banner']
    result=subprocess.run(args,capture_output=True,text=True,
                          env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
    assert result.returncode == 0
    assert result.stdout.splitlines() and all('rank=' not in line for line in result.stdout.splitlines())
    assert 'manual.nome=Ana' in result.stderr
    if budget == 'exhaustive':
        assert 'rank=' not in result.stderr
    else:
        assert 'rank=1 score=32 model=score-v1' in result.stderr
        assert 'origin.explicit.nome' in result.stderr


@pytest.mark.parametrize('budget', ['0','-1','nonsense','2.5'])
def test_cli_invalid_budget(budget):
    result=subprocess.run([sys.executable,'-B','-m','mimic.cli','-n','Ana','--budget',budget],capture_output=True)
    assert result.returncode == 2


def test_ranked_pending_and_running_restart_recovery(tmp_path):
    paths, repo=store(tmp_path)
    pending=repo.create_job(request().to_dict(),None,None)
    running=repo.create_job(request().to_dict(),None,None); repo.start_job(running['id'])
    for job in [pending,running]:
        output=paths.output(job['id']); output.parent.mkdir(parents=True)
        output.write_text('stale')
        output.with_name('wordlist.txt.part').write_text('partial')
    manager=JobManager(repo,paths); manager.start()
    try:
        for job in [pending,running]:
            assert repo.get_job(job['id'])['status'] == 'failed'
            assert not paths.output(job['id']).exists()
            assert not paths.output(job['id']).with_name('wordlist.txt.part').exists()
    finally:
        manager.stop()
