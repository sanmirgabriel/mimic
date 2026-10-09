"""Real local packs: confinement, streaming, source causality and snapshots."""
from dataclasses import asdict, replace
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import tracemalloc

import pytest

from mimic.application import (GenerationService, GenerationRequest, SourceOptions,
    GenerationLimits, MutationOptions, RankingOptions, IntelligenceOptions)
from mimic.core.candidate import Candidate, Origin
from mimic.domain.models import Organization, Target
from mimic.profile.schema import TargetProfile
from mimic.packs import PackRegistry, PackReference, PackError
from mimic.packs import registry as storage
from mimic.persistence import DataPaths, Database, Repository
from mimic.jobs import JobManager
from mimic.cli import main


@pytest.fixture
def registry(tmp_path):
    return PackRegistry(tmp_path / 'data')


def install(registry, contents=b'financeiro\nrecep\xc3\xa7\xc3\xa3o\n', **kwargs):
    return registry.import_stream(io.BytesIO(contents), id=kwargs.pop('id', 'work'),
        version=kwargs.pop('version', '1'), kind=kwargs.pop('kind', 'seed'),
        filename='fixture.txt', language='pt-BR', **kwargs)


def request(registry, identities=('work@1',), **kwargs):
    return GenerationRequest(sources=SourceOptions(packs=tuple(registry.reference(i) for i in identities)), **kwargs)


def corpus(registry, identity='work@1'):
    pack_id, version = identity.split('@')
    return registry.root / pack_id / version / 'corpus.txt'


def edit_manifest(registry, **fields):
    path = corpus(registry).with_name('manifest.json')
    metadata = json.loads(path.read_text())
    metadata.update(fields)
    path.write_text(json.dumps(metadata))


def test_import_copies_original_and_preserves_version_metadata(registry, tmp_path):
    original = tmp_path / 'external.txt'
    original.write_bytes(Path('tests/fixtures/br-workplace.txt').read_bytes())
    pack = registry.import_file(original, id='BR-Workplace', version='2026-10', kind='seed',
        name='Vocabulário profissional', language='pt-BR', license='NOASSERTION',
        source_url='https://example.test/terms', attribution='Original test vocabulary')
    original.unlink()
    assert registry.verify(pack.identity) == pack
    assert pack.id == 'br-workplace' and pack.line_count == 7
    assert pack.sha256 == hashlib.sha256(Path('tests/fixtures/br-workplace.txt').read_bytes()).hexdigest()
    assert corpus(registry, pack.identity).read_bytes() == Path('tests/fixtures/br-workplace.txt').read_bytes()
    assert registry.paths.packs == registry.root
    assert list(GenerationService(registry).prepare(request(registry, (pack.identity,))).iter_values())


def test_idempotency_conflict_and_versions(registry):
    first = install(registry, name='Original')
    assert install(registry, name='Original') == first
    with pytest.raises(PackError, match='metadata'):
        install(registry, name='Changed display')
    with pytest.raises(PackError, match='different bytes'):
        install(registry, b'other\n')
    with pytest.raises(PackError, match='kind'):
        install(registry, kind='ready')
    second = install(registry, b'other\n', version='2')
    assert registry.list() == [first, second]
    assert registry.get(first.identity) == first


@pytest.mark.parametrize('contents,lines', [(b'', 0), (b'a', 1), (b'a\n', 1),
    (b'\n\n', 2), (b'a\r\nb\rc\n\n# comment', 5),
    (b'a' * 65535 + b'\r\nb', 2), (b'a' * 65535 + 'ç\n'.encode(), 1)])
def test_physical_lines_and_chunk_boundary_utf8(registry, contents, lines):
    pack = install(registry, contents, kind='ready')
    assert pack.line_count == lines
    assert registry.verify(pack.identity) == pack
    # Universal newline normalization matches the existing dataset adapter.
    results = list(GenerationService(registry).prepare(request(registry)).iter_candidates())
    assert all(c.origins[0].field.startswith('pack:work@1:') for c in results)


@pytest.mark.parametrize('fields', [{'id':'../escape'}, {'version':'../escape'}, {'id':'/absolute'},
    {'id':'a@b'}, {'version':'x/y'}, {'version':'x\\y'}, {'kind':'auto'},
    {'source_url':'javascript:alert(1)'}, {'source_url':'https://user:pass@example.test/'},
    {'attribution':'bad\nheader'}])
def test_metadata_and_identity_rejection_has_no_side_effects(registry, fields):
    with pytest.raises(PackError):
        install(registry, **fields)
    assert not registry.root.exists()


@pytest.mark.parametrize('failure', ['utf8', 'nul', 'oversize', 'interrupt', 'write', 'permission'])
def test_failed_import_cleans_staging(registry, monkeypatch, failure):
    stream = io.BytesIO(b'valid\n')
    kwargs = {}
    if failure == 'utf8': stream = io.BytesIO(b'bad\xff')
    if failure == 'nul': stream = io.BytesIO(b'a\x00b')
    if failure == 'oversize': kwargs['max_bytes'] = 2
    if failure == 'interrupt':
        class Interrupted:
            calls = 0
            def read(self, size):
                self.calls += 1
                if self.calls == 1: return b'a' * size
                raise KeyboardInterrupt()
        stream = Interrupted()
    if failure == 'write':
        monkeypatch.setattr(storage.os, 'fsync', lambda fd: (_ for _ in ()).throw(OSError('disk full')))
    if failure == 'permission':
        original = storage.os.open
        def denied(name, flags, *args, **kwargs):
            if name == 'manifest.json': raise PermissionError('denied')
            return original(name, flags, *args, **kwargs)
        monkeypatch.setattr(storage.os, 'open', denied)
    with pytest.raises((PackError, OSError, KeyboardInterrupt)):
        registry.import_stream(stream, id='work', version='1', kind='seed', filename='fixture.txt', **kwargs)
    assert registry.list() == []
    assert not list(registry.root.glob('.import-*'))
    assert not corpus(registry).exists()


@pytest.mark.parametrize('position', ['packs', 'id', 'version', 'corpus', 'manifest'])
def test_symlinks_never_followed(registry, tmp_path, position):
    install(registry)
    selected = {'packs':registry.root, 'id':registry.root/'work', 'version':corpus(registry).parent,
                'corpus':corpus(registry), 'manifest':corpus(registry).with_name('manifest.json')}[position]
    moved = tmp_path / 'moved'
    selected.rename(moved)
    selected.symlink_to(moved, target_is_directory=moved.is_dir())
    with pytest.raises((PackError, OSError)):
        registry.verify('work@1')
    assert moved.exists()


def test_nonregular_cli_source_is_rejected(registry, tmp_path):
    fifo = tmp_path / 'pipe.txt'
    os.mkfifo(fifo)
    with pytest.raises(PackError, match='regular'):
        registry.import_file(fifo, id='work', version='1', kind='seed')


@pytest.mark.parametrize('failure,code', [('digest','digest'), ('missing','unavailable'),
    ('manifest','manifest'), ('utf8','utf8'), ('size','size'), ('lines','size'), ('schema','manifest'),
    ('identity','manifest'), ('traversal','manifest'), ('duplicate','manifest')])
def test_verification_checks_actual_content_and_manifest(registry, failure, code):
    install(registry)
    reference = registry.reference('work@1')
    if failure == 'digest': corpus(registry).write_bytes(b'changed\n')
    elif failure == 'missing': corpus(registry).unlink()
    elif failure == 'utf8': corpus(registry).write_bytes(b'\xff')
    elif failure == 'manifest': corpus(registry).with_name('manifest.json').write_text('{broken')
    elif failure == 'duplicate':
        path=corpus(registry).with_name('manifest.json');path.write_text(path.read_text()[:-1] + ',"id":"work"}')
    elif failure == 'size': edit_manifest(registry,size_bytes=999)
    elif failure == 'lines': edit_manifest(registry,physical_line_count=999)
    elif failure == 'schema': edit_manifest(registry,schema_version=99)
    elif failure == 'identity': edit_manifest(registry,id='different')
    elif failure == 'traversal': edit_manifest(registry,corpus_path='../../outside')
    # A fresh lookup checks the manifest against disk; pinned references also reject metadata drift.
    with pytest.raises(PackError) as error:
        registry.verify('work@1')
    assert error.value.code == code
    with pytest.raises(PackError):
        with registry.open_verified((reference,)): pass


@pytest.mark.parametrize('kind', ['seed', 'ready'])
def test_existing_pipeline_scores_and_noncombinable_semantics(registry, kind):
    install(registry, b'financeiro\nfinanceiro\n', kind=kind)
    prepared = GenerationService(registry).prepare(request(registry,
        base_candidates=(Candidate('Pedro',(Origin('manual','nome','Pedro'),)),),
        mutations=MutationOptions('partial',True,''), ranking=RankingOptions(True,100)))
    results=list(prepared.iter_results())
    from_pack=[r for r in results if r.candidate.origins[0].field.startswith('pack:')]
    assert from_pack and not any('Pedro' in r.candidate.value for r in from_pack)
    if kind=='ready':
        assert len(from_pack)==1 and from_pack[0].candidate.value=='financeiro'
        assert from_pack[0].candidate.transformations==() and from_pack[0].score.total==50
    else:
        assert len(from_pack)>1
        original=next(r for r in from_pack if r.candidate.value=='financeiro')
        assert original.score.total==4
        assert any(t.kind=='leet' for r in from_pack for t in r.candidate.transformations)
    assert all(r.score.version=='score-v1' for r in from_pack)


def test_physical_limit_is_per_pack_and_fails_before_any_output(registry):
    install(registry,b'one\n\n# comment\ntwo\n',kind='ready')
    prepared=GenerationService(registry).prepare(request(registry,limits=GenerationLimits(10,3),
        base_candidates=(Candidate('Pedro'),)))
    with pytest.raises(PackError,match='physical lines'):
        next(prepared.iter_values())
    assert prepared.evaluated_count==0
    install(registry,b'a\nb\nc\n',id='second',kind='ready')
    assert len(list(GenerationService(registry).prepare(request(registry,('second@1',),
        limits=GenerationLimits(10,3))).iter_values()))==3


def test_preview_is_metadata_only_and_roundtrip_is_pinned(registry, monkeypatch):
    install(registry)
    req=request(registry)
    minimal=PackReference('work','1',req.sources.packs[0].sha256)
    req.sources=SourceOptions(packs=(minimal,))
    monkeypatch.setattr(storage,'inspect_stream',lambda *a,**kw:pytest.fail('preview read corpus'))
    prepared=GenerationService(registry).prepare(req)
    assert prepared.summary().packs[0].identity=='work@1'
    snapshot=json.loads(json.dumps(prepared.request.to_dict()))
    assert json.loads(json.dumps(GenerationRequest.from_dict(snapshot).to_dict()))==snapshot
    assert GenerationRequest.from_dict(snapshot).sources.packs[0].metadata.license=='NOASSERTION'
    assert SourceOptions.from_dict(json.loads(json.dumps(prepared.request.sources.to_dict())))==prepared.request.sources
    old=GenerationRequest.from_dict({'sources':{'include_ptbr':False}})
    assert old.sources.packs==() and 'packs' not in old.to_dict()['sources']


def test_all_extra_source_precedence_and_first_causal_wins(registry,tmp_path,monkeypatch):
    values=b'ReadyExplicit\nReadyPack\nadmin\nDirectData\nSeedPack\nBuiltin\n'
    explicit_ready=tmp_path/'ready.txt';explicit_ready.write_bytes(b'ReadyExplicit\n')
    explicit_dataset=tmp_path/'dataset.txt';explicit_dataset.write_bytes(b'DirectData\nSeedPack\n')
    install(registry,b'ReadyExplicit\nReadyPack\n',kind='ready',id='ready')
    install(registry,values,id='seed')
    install(registry,b'SeedPack\nBuiltin\n',id='second')
    from mimic.core.seed import Seed
    monkeypatch.setattr('mimic.application.generation.stream_ptbr',lambda: iter([
        Seed(Candidate('Builtin',(Origin('dataset','ptbr.fixture:1','Builtin'),)))]))
    req=request(registry,('seed@1','ready@1','second@1'),mutations=MutationOptions('none',False,''),
        intelligence=IntelligenceOptions(enabled=True,common_numbers=False,recent_years=False,
            corporate_roles=False,service_profiles=('wordpress',),reference_year=2026))
    req.sources=replace(req.sources,ready_candidate_paths=(str(explicit_ready),),
        dataset_paths=(str(explicit_dataset),),include_ptbr=True)
    candidates=list(GenerationService(registry).prepare(req).iter_candidates())
    by_value={c.value:c for c in candidates}
    assert by_value['ReadyExplicit'].origins[0].source=='ready_candidate'
    assert by_value['ReadyExplicit'].origins[0].field==str(explicit_ready)+':1'
    assert by_value['ReadyPack'].origins[0].field=='pack:ready@1:2'
    assert by_value['admin'].origins[0].source=='knowledge'
    assert by_value['DirectData'].origins[0].field==str(explicit_dataset)+':1'
    assert by_value['SeedPack'].origins[0].field==str(explicit_dataset)+':2'
    assert by_value['Builtin'].origins[0].field=='pack:seed@1:6'
    assert [c.value for c in candidates].index('ReadyPack') < [c.value for c in candidates].index('admin')
    # Excluding the explicit duplicate attributes the value to the first selected seed pack.
    req.sources=replace(req.sources,dataset_paths=())
    assert next(c for c in GenerationService(registry).prepare(req).iter_candidates()
                if c.value=='SeedPack').origins[0].field=='pack:seed@1:5'


def test_stream_detects_in_place_change_after_verification(registry):
    install(registry,b'First\nSecond\n',kind='ready')
    with registry.open_verified((registry.reference('work@1'),)) as streams:
        corpus(registry).write_bytes(b'Other\nSecond\n')
        with pytest.raises(PackError,match='changed during execution'):
            list(registry.seeds(*streams['work@1']))


def test_growth_after_verification_and_comment_only_cancellation(registry):
    install(registry,b'# comment\n\n' * 20,kind='ready')
    state={'streaming':False,'calls':0}
    def checkpoint():
        if state['streaming']:
            state['calls']+=1
            if state['calls']==3:raise RuntimeError('cancelled while reading comments')
    with registry.open_verified((registry.reference('work@1'),),checkpoint=checkpoint) as streams:
        state['streaming']=True
        with pytest.raises(RuntimeError,match='reading comments'):
            list(registry.seeds(*streams['work@1']))
    assert state['calls']==3
    with registry.open_verified((registry.reference('work@1'),)) as streams:
        with corpus(registry).open('ab') as target:target.write(b'# appended after validation\n')
        with pytest.raises(PackError,match='grew during execution'):
            list(registry.seeds(*streams['work@1']))


def test_ready_10000_lines_incremental_budget_scans_all(registry):
    class Chunked(io.BytesIO):
        def read(self,size=-1):
            assert 0 < size <= 65536
            return super().read(size)
    contents=''.join(f'Candidate{i:05d}!\n' for i in range(10000)).encode()
    registry.import_stream(Chunked(contents),id='work',version='1',kind='ready',filename='large.txt')
    prepared=GenerationService(registry).prepare(request(registry,ranking=RankingOptions(True,100)))
    retained=list(prepared.iter_results())
    assert prepared.evaluated_count==10000 and len(retained)==100
    assert [r.candidate.value for r in retained]==[f'Candidate{i:05d}!' for i in range(100)]
    assert all(r.candidate.transformations==() for r in retained)
    exhaustive=GenerationService(registry).prepare(request(registry))
    assert sum(1 for _ in exhaustive.iter_values())==10000
    tracemalloc.start()
    registry.verify('work@1')
    _,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
    assert peak<1024*1024


def test_jobs_freeze_metadata_and_worker_survives_integrity_failure(registry,monkeypatch):
    install(registry,kind='ready')
    database=Database(registry.paths);database.initialize();repo=Repository(database)
    entered=threading.Event();release=threading.Event()
    class WaitingService(GenerationService):
        def prepare(self, req):
            entered.set();assert release.wait(10)
            return super().prepare(req)
    manager=JobManager(repo,registry.paths,service=WaitingService(registry));manager.start()
    try:
        req=request(registry)
        job=manager.submit(req);assert entered.wait(5)
        req.sources=SourceOptions()
        assert repo.get_job(job['id'])['request']['sources']['packs'][0]['metadata']['license']=='NOASSERTION'
        corpus(registry).write_bytes(b'changed\n');release.set()
        failed=manager.wait(job['id'],10)
        assert failed['status']=='failed' and failed['error']=='pack.error.digest'
        assert not registry.paths.output(job['id']).exists()
        assert not registry.paths.output(job['id']).with_name('wordlist.txt.part').exists()
        good=manager.submit(GenerationRequest(base_candidates=(Candidate('Healthy'),)))
        assert manager.wait(good['id'],10)['status']=='completed'
    finally:
        release.set();manager.stop()


def test_cancellation_during_pack_ranking_and_verification(registry,monkeypatch):
    install(registry,b''.join(f'Candidate{i:05d}\n'.encode() for i in range(10000)),kind='ready')
    database=Database(registry.paths);database.initialize();repo=Repository(database)
    entered=threading.Event();release=threading.Event()
    from mimic.application import generation
    score=generation.score_candidate
    def blocked(candidate,year):
        entered.set();assert release.wait(10)
        return score(candidate,year)
    monkeypatch.setattr(generation,'score_candidate',blocked)
    manager=JobManager(repo,registry.paths);manager.start()
    try:
        job=manager.submit(request(registry,ranking=RankingOptions(True,100)))
        assert entered.wait(5);manager.cancel(job['id']);release.set()
        assert manager.wait(job['id'],10)['status']=='cancelled'
        assert not registry.paths.output(job['id']).exists()
        assert not registry.paths.output(job['id']).with_name('wordlist.txt.part').exists()
    finally:
        release.set();manager.stop()
    calls=[]
    def cancelled():
        calls.append(1);raise RuntimeError('cancelled verification')
    with pytest.raises(RuntimeError,match='cancelled verification'):
        with registry.open_verified((registry.reference('work@1'),),checkpoint=cancelled): pass
    assert calls==[1]


def test_cli_management_generation_and_atomic_failure(registry,tmp_path,capsys):
    source=tmp_path/'seclists-local.txt';source.write_text('Example2026!\nOther2026!\n')
    data=['--data-dir',str(registry.paths.root)]
    assert main(['packs','list',*data])==0
    assert 'No packs' in capsys.readouterr().out
    assert main(['packs','import',str(source),'--id','ready','--version','1','--kind','ready',
        '--license','MIT','--attribution','Local synthetic SecLists workflow fixture',*data])==0
    assert main(['packs','show','ready@1',*data])==0
    assert '"sha256"' in capsys.readouterr().out
    assert main(['packs','verify','ready@1',*data])==0
    assert 'Verified' in capsys.readouterr().out
    output=tmp_path/'output.txt'
    args=['generate','--pack','ready@1',*data,'--no-intelligence','--quiet','-o',str(output)]
    assert main(args)==0 and output.read_bytes()==source.read_bytes()
    corpus(registry,'ready@1').write_text('tampered\n')
    assert main(args)==1 and output.read_bytes()==source.read_bytes()
    assert not list(tmp_path.glob('.mimic-*.part'))
    assert main(['generate','--pack','missing@1',*data,'--quiet'])==1


def test_hash_seed_determinism_with_multiple_duplicate_packs(registry):
    install(registry,b'financeiro\nrecep\xc3\xa7\xc3\xa3o\nfinanceiro\n')
    install(registry,b'Ready2026!\nfinanceiro\n',id='ready',kind='ready')
    install(registry,b'financeiro\nsuporte\n',id='second')
    script='''
import json,sys
from dataclasses import asdict
from mimic.packs import PackRegistry
from mimic.application import GenerationService,GenerationRequest,SourceOptions,RankingOptions,MutationOptions
r=PackRegistry(sys.argv[1])
q=GenerationRequest(sources=SourceOptions(packs=tuple(r.reference(x) for x in ('ready@1','work@1','second@1'))),ranking=RankingOptions(True,1000),mutations=MutationOptions('partial',False,''))
print(json.dumps([asdict(x) for x in GenerationService(r).prepare(q).iter_results()],sort_keys=True,ensure_ascii=False))
'''
    outputs=[subprocess.check_output([sys.executable,'-B','-c',script,str(registry.paths.root)],
        env={**os.environ,'PYTHONHASHSEED':seed,'PYTHONDONTWRITEBYTECODE':'1'}) for seed in ('1','42','777')]
    assert outputs[0]==outputs[1]==outputs[2]


def test_concurrent_identical_imports_publish_one_complete_version(registry):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _:install(registry,kind='ready'),range(4)))
    assert len(registry.list())==1 and results.count(results[0])==4
    assert registry.verify('work@1')==results[0]
    assert not list(registry.root.glob('.import-*'))


def test_seed_10000_lines_mutation_caps_dedup_and_ranking(registry,caplog):
    install(registry,b''.join(f'term{i:05d}\n'.encode() for i in range(10000)))
    prepared=GenerationService(registry).prepare(request(registry,
        limits=GenerationLimits(2,10000),mutations=MutationOptions('partial',True,''),
        ranking=RankingOptions(True,100)))
    results=list(prepared.iter_results())
    assert len(results)==100 and prepared.evaluated_count==30000
    assert all(r.candidate.origins[0].source=='dataset' for r in results)
    assert all(not any(t.kind=='combine' for t in r.candidate.transformations) for r in results)
    assert 'cap=2' in caplog.text


def test_pack_removal_and_permission_errors_are_explicit(registry,monkeypatch):
    install(registry,kind='ready')
    prepared=GenerationService(registry).prepare(request(registry))
    original=storage.os.open
    def denied(name,*args,**kwargs):
        if name=='corpus.txt':raise PermissionError('source denied')
        return original(name,*args,**kwargs)
    with monkeypatch.context() as guard:
        guard.setattr(storage.os,'open',denied)
        with pytest.raises(PackError,match='unavailable'):
            registry.verify('work@1')
    corpus(registry).unlink()
    with pytest.raises(PackError,match='unavailable'):
        next(prepared.iter_values())
    assert prepared.evaluated_count==0
