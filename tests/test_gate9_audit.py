"""Gate 9: deterministic failure boundaries and adapter isolation."""
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading

import pytest
from fastapi.testclient import TestClient

from mimic.api import create_app
from mimic.application import (GenerationRequest, GenerationService, SourceOptions,
    RankingOptions, MutationOptions, IntelligenceOptions, GenerationLimits)
from mimic.core.candidate import Candidate, Origin
from mimic.cli import main
from mimic.jobs import JobManager
from mimic.packs import PackRegistry, PackError
from mimic.packs import registry as storage
from mimic.persistence import Database, Repository
from tests.test_packs import install, request, corpus, registry
from tests.test_web_packs import upload
from tests.test_web_i18n import token


@pytest.mark.parametrize('field', ['name', 'language', 'license', 'source_url', 'attribution', 'description'])
def test_reimport_rejects_immutable_metadata_conflicts(registry, field):
    first = install(registry)
    value = 'https://example.test/other' if field == 'source_url' else 'Changed'
    with pytest.raises(PackError) as error:
        registry.import_stream(io.BytesIO(corpus(registry).read_bytes()), id='work', version='1',
            kind='seed', filename='fixture.txt', **{'language': 'pt-BR', field: value})
    assert error.value.code == 'conflict'
    assert registry.verify('work@1') == first
    assert not list(registry.root.glob('.import-*'))


@pytest.mark.parametrize('change', [
    ('name', 12), ('name', '\ud800'), ('source_url', 'https://example.test/\x00'),
    ('source_url', 'https://example.test/\udfff'), ('source_url', 'https://example.test/\x7f'),
    ('size_bytes', True), ('size_bytes', -1), ('physical_line_count', 1.5),
    ('sha256', 'a'*63), ('sha256', 'g'*64), ('schema_version', 2),
    ('schema_version', True), ('id', '../work'), ('version', '../1'),
    ('name', 'x'*2049), ('unexpected', 'value')])
def test_invalid_manifest_never_lists_installed(registry, change):
    install(registry)
    path=corpus(registry).with_name('manifest.json')
    data=json.loads(path.read_text()); data[change[0]]=change[1]
    path.write_text(json.dumps(data))
    with pytest.raises(PackError): registry.list()


@pytest.mark.parametrize('missing', ['schema_version','id','version','name','kind','language',
    'license','source_url','sha256','size_bytes','physical_line_count','filename','attribution'])
def test_missing_manifest_fields_are_rejected(registry, missing):
    install(registry)
    path=corpus(registry).with_name('manifest.json')
    data=json.loads(path.read_text()); del data[missing]
    path.write_text(json.dumps(data))
    with pytest.raises(PackError): registry.list()


@pytest.mark.parametrize('stage', ['copy','hash','manifest-write','before-publish','publish','stage-open'])
def test_import_stage_failure_keeps_existing_and_cleans(registry, monkeypatch, stage):
    existing=install(registry)
    original_open=storage.os.open
    class BrokenRead(io.BytesIO):
        def read(self, size): raise OSError('copy failed')
    stream=BrokenRead(b'new\n') if stage=='copy' else io.BytesIO(b'new\n')
    def fail(*args, **kwargs): raise OSError('injected failure')
    if stage=='hash': monkeypatch.setattr(storage.hashlib,'sha256',fail)
    elif stage=='manifest-write': monkeypatch.setattr(storage.json,'dump',fail)
    elif stage=='before-publish':
        directory=storage._directory
        def fail_parent(name,parent=None):
            if name=='other': raise OSError('parent unavailable')
            return directory(name,parent)
        monkeypatch.setattr(storage,'_directory',fail_parent)
    elif stage=='publish': monkeypatch.setattr(storage.os,'rename',fail)
    elif stage=='stage-open':
        def fail_stage(name,flags,*args,**kwargs):
            if str(name).startswith('.import-'): raise OSError('stage open failed')
            return original_open(name,flags,*args,**kwargs)
        monkeypatch.setattr(storage.os,'open',fail_stage)
    with pytest.raises((OSError,PackError)):
        registry.import_stream(stream,id='other',version='1',kind='ready',filename='fixture.txt')
    # Restore fault injection before inspecting independent managed content.
    monkeypatch.undo()
    assert registry.list()==[existing]
    assert registry.verify('work@1')==existing
    assert not list(registry.root.glob('.import-*'))


@pytest.mark.parametrize('scenario', ['identical','metadata','content','versions'])
def test_concurrent_publication_conflicts_are_explicit(registry, scenario):
    barrier=threading.Barrier(2)
    class Synchronized(io.BytesIO):
        def read(self,size):
            if self.tell()==0: barrier.wait(5)
            return super().read(size)
    def run(index):
        fields=dict(id='work',version='2' if scenario=='versions' and index else '1',
            kind='ready',filename='fixture.txt',name='Changed' if scenario=='metadata' and index else 'Original')
        try: return registry.import_stream(Synchronized(b'other\n' if scenario=='content' and index else b'one\n'),**fields)
        except PackError as exc: return exc
    with ThreadPoolExecutor(2) as pool: results=list(pool.map(run,range(2)))
    if scenario in ('metadata','content'):
        assert sum(isinstance(r,PackError) and r.code=='conflict' for r in results)==1
        assert len(registry.list())==1
    elif scenario=='versions': assert len(registry.list())==2
    else: assert results[0]==results[1] and len(registry.list())==1
    for metadata in registry.list(): assert registry.verify(metadata.identity)==metadata
    assert not list(registry.root.glob('.import-*'))


@pytest.mark.parametrize('mutation', ['in-place','truncate','same-size','replace','delete','symlink'])
def test_verified_descriptor_stream_contract(registry,tmp_path,mutation):
    contents=b''.join(f'Original{i:05d}\n'.encode() for i in range(2000))
    metadata=install(registry,contents,kind='ready')
    with registry.open_verified((registry.reference('work@1'),)) as streams:
        seeds=registry.seeds(*streams['work@1'])
        assert next(seeds).candidate.value=='Original00000'
        path=corpus(registry)
        if mutation in ('in-place','same-size'):
            with path.open('r+b') as output:
                output.seek(len(contents)-14); output.write(b'Changed!01999\n')
        elif mutation=='truncate':
            with path.open('r+b') as output: output.truncate(10000)
        elif mutation=='replace':
            replacement=tmp_path/'replacement'; replacement.write_bytes(b'Changed\n'); os.replace(replacement,path)
        elif mutation=='delete': path.unlink()
        else:
            outside=tmp_path/'outside'; outside.write_bytes(b'Changed\n'); path.unlink();path.symlink_to(outside)
        if mutation in ('in-place','same-size','truncate'):
            with pytest.raises(PackError): list(seeds)
        else:
            # Unlinked/replaced path cannot redirect the held regular-file descriptor.
            remaining=list(seeds)
            assert len(remaining)==1999 and remaining[-1].candidate.value=='Original01999'
    with pytest.raises(PackError): registry.verify(metadata.identity)


def test_already_buffered_bytes_limit_is_explicit(registry):
    install(registry,b'First\nSecond\n',kind='ready')
    with registry.open_verified((registry.reference('work@1'),)) as streams:
        seeds=registry.seeds(*streams['work@1']); assert next(seeds).candidate.value=='First'
        corpus(registry).write_bytes(b'Other\nSecond\n')
        # The text reader has already buffered the old bytes; final hash covers consumed bytes.
        assert [s.candidate.value for s in seeds]==['Second']
    with pytest.raises(PackError): registry.verify('work@1')


@pytest.mark.parametrize('file_output',[False,True])
def test_cli_detected_final_digest_blocks_file_but_stdout_can_be_partial(registry,tmp_path,monkeypatch,capsys,file_output):
    contents=b''.join(f'Original{i:05d}\n'.encode() for i in range(2000))
    install(registry,contents,kind='ready')
    from mimic.core.sink import Sink
    drain=Sink.drain
    def drain_with_edit(self,values):
        def edited():
            for index,value in enumerate(values):
                yield value
                if index==0:
                    with corpus(registry).open('r+b') as out:
                        out.seek(len(contents)-14);out.write(b'Changed!01999\n')
        return drain(self,edited())
    monkeypatch.setattr(Sink,'drain',drain_with_edit)
    destination=tmp_path/'result.txt';destination.write_bytes(b'Existing\n')
    args=['generate','--pack','work@1','--data-dir',str(registry.paths.root),'--no-intelligence','--quiet']
    if file_output: args+=['-o',str(destination)]
    assert main(args)==1
    captured=capsys.readouterr()
    if file_output: assert destination.read_bytes()==b'Existing\n'
    else: assert captured.out.startswith('Original00000\n')
    assert not list(tmp_path.glob('.mimic-*.part'))


def test_job_cancel_during_verifier_and_worker_recovers(registry,monkeypatch):
    install(registry,b'large\n'*20000,kind='ready')
    entered=threading.Event();release=threading.Event()
    inspect=storage.inspect_stream
    def paused(stream,**kwargs):
        if kwargs.get('checkpoint'):
            calls=0;checkpoint=kwargs['checkpoint']
            def stop_point():
                nonlocal calls
                calls+=1
                if calls==2: entered.set();assert release.wait(10)
                checkpoint()
            kwargs['checkpoint']=stop_point
        return inspect(stream,**kwargs)
    monkeypatch.setattr(storage,'inspect_stream',paused)
    db=Database(registry.paths);db.initialize();manager=JobManager(Repository(db),registry.paths);manager.start()
    try:
        job=manager.submit(request(registry,ranking=RankingOptions(True,100)))
        assert entered.wait(5)
        assert manager.repository.get_job(job['id'])['evaluated_count']==0
        manager.cancel(job['id']);release.set()
        assert manager.wait(job['id'],10)['status']=='cancelled'
        assert not registry.paths.output(job['id']).exists()
        assert not registry.paths.output(job['id']).with_suffix('.txt.part').exists()
        next_job=manager.submit(GenerationRequest(base_candidates=(Candidate('Healthy'),)))
        assert manager.wait(next_job['id'],10)['status']=='completed'
    finally: release.set();manager.stop()


@pytest.mark.parametrize('failure',['removed','manifest','digest','read','stream-digest','ranking','write','finalize','cancel-generator'])
def test_job_failure_matrix_keeps_worker_healthy(registry,monkeypatch,failure):
    contents=(b''.join(f'Original{i:05d}\n'.encode() for i in range(2000))
              if failure=='stream-digest' else b'First\nSecond\n')
    install(registry,contents,kind='ready')
    entered=threading.Event();release=threading.Event()
    class PausedService(GenerationService):
        def prepare(self,req):
            if req.sources.packs: entered.set();assert release.wait(10)
            return super().prepare(req)
    db=Database(registry.paths);db.initialize();manager=JobManager(Repository(db),registry.paths,service=PausedService(registry));manager.start()
    try:
        job=manager.submit(request(registry,ranking=RankingOptions(True,100) if failure=='ranking' else RankingOptions()))
        assert entered.wait(5)
        with monkeypatch.context() as guard:
            if failure=='removed': shutil.rmtree(corpus(registry).parent)
            elif failure=='manifest': corpus(registry).with_name('manifest.json').write_text('{}')
            elif failure=='digest': corpus(registry).write_bytes(b'Changed\n')
            elif failure=='read':
                regular=storage._regular
                @contextmanager
                def broken(name,parent=None):
                    with regular(name,parent) as stream:
                        if name=='corpus.txt': raise OSError('injected read error')
                        yield stream
                guard.setattr(storage,'_regular',broken)
            elif failure=='stream-digest':
                seeds=storage.PackRegistry.seeds
                def changed(*args):
                    for index,seed in enumerate(seeds(*args)):
                        yield seed
                        if index==0:
                            with corpus(registry).open('r+b') as output:
                                output.seek(len(contents)-14)
                                output.write(b'Changed!01999\n')
                guard.setattr(storage.PackRegistry,'seeds',staticmethod(changed))
            elif failure=='ranking':
                def broken(*a):raise OSError('ranking failure')
                guard.setattr('mimic.application.generation.score_candidate',broken)
            elif failure=='write':
                opening=Path.open
                def broken(path,*a,**kw):
                    if path.name=='wordlist.txt.part':raise OSError('write failed')
                    return opening(path,*a,**kw)
                guard.setattr(Path,'open',broken)
            elif failure=='finalize':
                replacing=os.replace
                def broken(src,dst,*a,**kw):
                    if str(src).endswith('wordlist.txt.part'): raise OSError('publish failed')
                    return replacing(src,dst,*a,**kw)
                guard.setattr('mimic.jobs.manager.os.replace',broken)
            elif failure=='cancel-generator':
                seeds=storage.PackRegistry.seeds
                def cancelling(*args):
                    for seed in seeds(*args):
                        manager.cancel(job['id']);yield seed
                guard.setattr(storage.PackRegistry,'seeds',staticmethod(cancelling))
            release.set()
            record=manager.wait(job['id'],10)
            assert record['status']==('cancelled' if failure=='cancel-generator' else 'failed')
            if failure=='stream-digest':assert record['error']=='pack.error.digest'
            with pytest.raises(ValueError): manager.completed_output(job['id'])
            assert not registry.paths.output(job['id']).exists()
            assert not registry.paths.output(job['id']).with_suffix('.txt.part').exists()
        healthy=manager.submit(GenerationRequest(base_candidates=(Candidate('Healthy'),)))
        assert manager.wait(healthy['id'],10)['status']=='completed'
    finally: release.set();manager.stop()


def test_two_data_dirs_cli_web_api_and_bidirectional_import(tmp_path,capsys):
    a,b=tmp_path/'a',tmp_path/'b';ra,rb=PackRegistry(a),PackRegistry(b)
    install(ra,b'OnlyA\n',id='pack-a',kind='ready')
    for directory,expected in [(a,'pack-a@1'),(b,'No packs')]:
        assert main(['packs','list','--data-dir',str(directory)])==0
        assert expected in capsys.readouterr().out
    assert main(['generate','--pack','pack-a@1','--data-dir',str(a),'--no-intelligence','--quiet'])==0
    assert capsys.readouterr().out=='OnlyA\n'
    assert main(['generate','--pack','pack-a@1','--data-dir',str(b),'--quiet'])==1
    with TestClient(create_app(data_dir=a)) as ca,TestClient(create_app(data_dir=b)) as cb:
        assert 'pack-a@1' in ca.get('/generate').text and 'pack-a@1' not in cb.get('/generate').text
        payload=request(ra,('pack-a@1',)).to_dict()
        assert cb.post('/api/jobs',json={'request':payload}).status_code==422
        result=ca.post('/api/jobs',json={'request':payload});assert result.status_code==201
        assert ca.app.state.job_manager.wait(result.json()['id'],10)['status']=='completed'
        assert upload(cb,id='pack-b',contents=b'OnlyB\n').status_code==303
        assert main(['generate','--pack','pack-b@1','--data-dir',str(b),'--no-intelligence','--quiet'])==0
        assert capsys.readouterr().out=='OnlyB\n'
        assert ca.post('/api/jobs',json={'request':request(rb,('pack-b@1',)).to_dict()}).status_code==422
        # CLI import into B is immediately usable by that running Web instance.
        source=tmp_path/'local.txt';source.write_bytes(b'CLItoWeb\n')
        assert main(['packs','import',str(source),'--id','cli','--version','1','--kind','ready','--data-dir',str(b)])==0
        response=cb.post('/generate',data={'csrf_token':token(cb),'mode':'quick','intent':'generate','packs':'cli@1'},follow_redirects=False)
        assert response.status_code==303
        job_id=response.headers['location'].split('/')[-1]
        assert cb.app.state.job_manager.wait(job_id,10)['status']=='completed'
        assert cb.get('/api/jobs/'+job_id+'/download').text=='CLItoWeb\n'


def test_preview_never_opens_corpus_generates_scores_or_mutates(tmp_path,monkeypatch):
    registry=PackRegistry(tmp_path);install(registry,kind='ready')
    before={str(p):p.read_bytes() for p in registry.root.rglob('*') if p.is_file()}
    with TestClient(create_app(data_dir=tmp_path)) as client:
        regular=storage._regular
        @contextmanager
        def guard(name,parent=None):
            assert name!='corpus.txt'
            with regular(name,parent) as stream:yield stream
        monkeypatch.setattr(storage,'_regular',guard)
        def forbidden(*a,**kw):pytest.fail('preview executed pack/generator/scoring')
        monkeypatch.setattr(storage,'inspect_stream',forbidden)
        monkeypatch.setattr('mimic.core.generator.Generator.generate_candidates',forbidden)
        monkeypatch.setattr('mimic.application.generation.score_candidate',forbidden)
        assert client.get('/generate').status_code==200
        assert client.post('/generate',data={'csrf_token':token(client),'mode':'quick','intent':'preview','packs':'work@1'}).status_code==200
    assert before=={str(p):p.read_bytes() for p in registry.root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('case',['wrong-sha','missing-id','missing-version','duplicate','unknown','kind','old'])
def test_api_pack_payload_validation(tmp_path,case):
    registry=PackRegistry(tmp_path);install(registry,kind='ready')
    payload=request(registry).to_dict();reference=payload['sources']['packs'][0]
    if case=='wrong-sha':reference['sha256']='0'*64
    elif case=='missing-id':reference['id']='absent'
    elif case=='missing-version':reference['version']='99'
    elif case=='duplicate':payload['sources']['packs']=[reference,reference.copy()]
    elif case=='unknown':reference['path']='/etc/passwd'
    elif case=='kind':reference['metadata']['kind']='seed'
    else:payload={'base_candidates':[{'value':'Old','origins':[],'transformations':[]}]}
    with TestClient(create_app(data_dir=tmp_path)) as client:
        response=client.post('/api/jobs',json={'request':payload})
        assert response.status_code==(201 if case=='old' else 422)
        if case=='old': assert client.app.state.job_manager.wait(response.json()['id'],10)['status']=='completed'


@pytest.mark.parametrize('headers,status',[({'origin':'null'},403),
    ({'origin':'null','sec-fetch-site':'cross-site'},403),
    ({'sec-fetch-site':'cross-site'},403),({'origin':'https://attacker.example'},403),
    ({'origin':'http://testserver','sec-fetch-site':'cross-site'},403),
    ({'origin':'null','sec-fetch-site':'same-origin'},303),({},303),
    ({'origin':'http://testserver','sec-fetch-site':'same-origin'},303)])
def test_web_origin_matrix_still_requires_csrf(tmp_path,headers,status):
    with TestClient(create_app(data_dir=tmp_path)) as client:
        data={'id':'work','version':'1','kind':'ready','csrf_token':token(client)}
        assert client.post('/packs/import',data=data,headers=headers,files={'pack_file':('local.txt',b'Word\n')},follow_redirects=False).status_code==status
        data.pop('csrf_token')
        assert client.post('/packs/import',data=data,headers=headers,files={'pack_file':('local.txt',b'Word\n')},follow_redirects=False).status_code==403


def test_rich_hashseed_determinism_with_quick_org_service(registry):
    install(registry,b'financeiro\nadmin\n',id='seed-one')
    install(registry,b'financeiro\nsuporte\n',id='seed-two')
    install(registry,b'admin\nReady2026!\n',id='ready',kind='ready')
    script='''
import sys,json
from dataclasses import asdict
from mimic.application import *
from mimic.domain.models import Organization
from mimic.packs import PackRegistry
r=PackRegistry(sys.argv[1])
q=GenerationRequest(organization=Organization('ACME'),sources=SourceOptions(packs=tuple(r.reference(x) for x in ('seed-two@1','ready@1','seed-one@1'))),mutations=MutationOptions('partial',False,''),limits=GenerationLimits(20,10000),intelligence=IntelligenceOptions(enabled=True,service_profiles=('wordpress',),reference_year=2026),ranking=RankingOptions.from_budget('quick'))
p=GenerationService(r).prepare(q)
print(json.dumps([asdict(x) for x in p.iter_results()],sort_keys=True,ensure_ascii=False))
'''
    outputs=[subprocess.check_output([sys.executable,'-B','-c',script,str(registry.paths.root)],env={**os.environ,'PYTHONHASHSEED':seed,'PYTHONDONTWRITEBYTECODE':'1'}) for seed in ('1','42','777')]
    assert outputs[0]==outputs[1]==outputs[2]
    assert len(json.loads(outputs[0]))==100


@pytest.mark.parametrize('change',['remove','replace','metadata'])
def test_pending_job_pins_order_metadata_and_exact_version(registry,change):
    first=install(registry,b'First\n',kind='ready')
    install(registry,b'Second\n',id='second',kind='ready')
    frozen=request(registry,('second@1','work@1'))
    snapshot=json.loads(json.dumps(frozen.to_dict()))
    assert GenerationRequest.from_dict(snapshot).to_dict()==frozen.to_dict()
    entered=threading.Event();release=threading.Event()
    class BlockFirst(GenerationService):
        def prepare(self,req):
            if not req.sources.packs: entered.set();assert release.wait(10)
            return super().prepare(req)
    db=Database(registry.paths);db.initialize();manager=JobManager(Repository(db),registry.paths,service=BlockFirst(registry));manager.start()
    try:
        blocker=manager.submit(GenerationRequest(base_candidates=(Candidate('Blocker'),)))
        assert entered.wait(5)
        job=manager.submit(frozen)
        assert manager.repository.get_job(job['id'])['status']=='pending'
        assert [p['id'] for p in manager.repository.get_job(job['id'])['request']['sources']['packs']]==['second','work']
        if change=='remove': shutil.rmtree(corpus(registry).parent)
        elif change=='replace':
            shutil.rmtree(corpus(registry).parent);install(registry,b'Replaced\n',kind='ready')
        else:
            manifest=corpus(registry).with_name('manifest.json');data=json.loads(manifest.read_text());data['kind']='seed';manifest.write_text(json.dumps(data))
        # A newer version must never be silently substituted for the missing/pinned one.
        install(registry,b'Newer\n',kind='ready',version='2')
        release.set()
        assert manager.wait(blocker['id'],10)['status']=='completed'
        assert manager.wait(job['id'],10)['status']=='failed'
        assert not registry.paths.output(job['id']).exists()
        assert not registry.paths.output(job['id']).with_suffix('.txt.part').exists()
        healthy=manager.submit(GenerationRequest(base_candidates=(Candidate('Healthy'),)))
        assert manager.wait(healthy['id'],10)['status']=='completed'
    finally:release.set();manager.stop()


@pytest.mark.parametrize('contents,physical,values',[
    (b'',0,[]),(b'\n'*10000,10000,[]),(b'# comment\n'*10000,10000,[]),
    ('# skip\r\n\r\n recepção \r\nfinanceiro'.encode(),4,['recepção','financeiro']),
    (b'x'*1024*1024,1,['x'*1024*1024]),(b'First\rSecond\r\nThird\n',3,['First','Second','Third'])],
    ids=['empty', 'blank-lines-10000', 'comments-10000', 'utf8-crlf',
         'single-line-1mib', 'mixed-newlines'])
def test_physical_lines_and_large_single_line(registry,contents,physical,values):
    metadata=install(registry,contents,kind='ready')
    assert metadata.line_count==physical and metadata.size_bytes==len(contents)
    prepared=GenerationService(registry).prepare(request(registry,limits=GenerationLimits(2,10000)))
    candidates=list(prepared.iter_candidates())
    assert [c.value for c in candidates]==values
    if values and len(values[0])<100:
        assert all(c.origins[0].value==c.value and c.transformations==() for c in candidates)
        assert candidates[0].origins[0].field.endswith(':3' if physical==4 else ':1')


def test_first_causal_derivation_retained_even_when_later_scores_higher(registry):
    from mimic.ranking.scoring import score_candidate
    install(registry,b'Duplicate\n',kind='ready')
    manual=Candidate('Duplicate',(Origin('manual','nome','Duplicate'),))
    ready=Candidate('Duplicate',(Origin('ready_candidate','pack:work@1:1','Duplicate'),))
    assert score_candidate(ready,2026).total>score_candidate(manual,2026).total
    prepared=GenerationService(registry).prepare(request(registry,base_candidates=(manual,),
        mutations=MutationOptions('none',False,''),ranking=RankingOptions(True,100)))
    duplicate=next(r for r in prepared.iter_results() if r.candidate.value=='Duplicate')
    assert duplicate.candidate.origins==manual.origins
    assert duplicate.score.total==score_candidate(manual,2026).total


@pytest.mark.parametrize('kind',['seed','ready'])
def test_pack_policy_is_global_and_seed_does_not_combine(registry,kind):
    from mimic.application import PolicyOptions
    install(registry,b'financeiro\nsuporte\ncontabilidade\n',kind=kind)
    prepared=GenerationService(registry).prepare(request(registry,base_candidates=(Candidate('Pedro'),),
        mutations=MutationOptions('partial',True,''),policy=PolicyOptions(min_len=9),ranking=RankingOptions(True,100)))
    results=list(prepared.iter_results())
    assert results and all(len(r.candidate.value)>=9 for r in results)
    packed=[r for r in results if r.candidate.origins[0].field.startswith('pack:')]
    assert packed and all(not any(t.kind=='combine' for t in r.candidate.transformations) for r in packed)
    if kind=='ready':assert {r.candidate.value for r in packed}=={'financeiro','contabilidade'}
    else:assert any(t.kind=='leet' for r in packed for t in r.candidate.transformations)


def test_web_io_failure_is_sanitized_and_cleans(tmp_path,monkeypatch):
    with TestClient(create_app(data_dir=tmp_path)) as client:
        def failed(*a,**kw):raise OSError('/secret/operator/path: disk full')
        monkeypatch.setattr(storage.os,'fsync',failed)
        response=upload(client)
        assert response.status_code==422 and '/secret/operator/path' not in response.text
        assert PackRegistry(tmp_path).list()==[]
        assert not list(PackRegistry(tmp_path).root.glob('.import-*'))


def test_import_fsync_failure_after_publication_leaves_complete_pack(registry,monkeypatch):
    fsync=os.fsync;calls=0
    def fail_last(fd):
        nonlocal calls
        calls+=1
        if calls==4:raise OSError('published directory fsync failed')
        fsync(fd)
    monkeypatch.setattr(storage.os,'fsync',fail_last)
    with pytest.raises(OSError):install(registry)
    monkeypatch.undo()
    assert len(registry.list())==1
    assert registry.verify('work@1')==registry.get('work@1')
    assert not list(registry.root.glob('.import-*'))


def test_manifest_physical_line_count_contract(registry):
    metadata=install(registry,b'# comment\n\nTerm\r\nLast',kind='ready')
    manifest=json.loads(corpus(registry).with_name('manifest.json').read_text())
    assert manifest['physical_line_count']==4
    assert 'line_count' not in manifest
    assert metadata.to_dict()['physical_line_count']==4
