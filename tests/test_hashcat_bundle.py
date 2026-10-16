"""Block 13: observed MIMIC output against real Hashcat stdout, never hashes."""
from collections import Counter
from dataclasses import replace
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from mimic.application import (GenerationRequest, GenerationService, MutationOptions,
    PolicyOptions, GenerationLimits, SourceOptions, IntelligenceOptions, RankingOptions)
from mimic.core.candidate import Candidate, Origin, Transformation
from mimic.domain.models import Organization
from mimic.rules import bundle as module
from mimic.rules.bundle import BundleError, BundleLimits, compile_pair, export_bundle


def request(word='Ab cD', leet='none', numbers=('123','2026'), separators='@!'):
    return GenerationRequest(base_candidates=(Candidate(word,(Origin('manual','nome',word),)),),
        number_candidates=tuple(Candidate(v,(Origin('cli','numbers',v),)) for v in numbers),
        mutations=MutationOptions(leet_mode=leet,separators=separators))


@pytest.fixture(scope='session')
def hashcat_runtime(tmp_path_factory):
    executable=shutil.which('hashcat')
    if not executable:pytest.skip('Hashcat not installed: external parity NOT VERIFIED')
    root=tmp_path_factory.mktemp('hashcat-stdout')
    (root/'data/hashcat/sessions').mkdir(parents=True)
    env={**os.environ,'XDG_DATA_HOME':str(root/'data'),'XDG_CACHE_HOME':str(root/'cache'),'POCL_CACHE_DIR':str(root/'pocl'),'POCL_MAX_PTHREAD_COUNT':'2'}
    version=subprocess.run([executable,'--version'],env=env,capture_output=True,timeout=10)
    if version.returncode or version.stdout.strip()!=b'v6.2.6':pytest.skip('External profile requires Hashcat 6.2.6')
    (root/'base').write_text('Probe\n');(root/'rules').write_text(':\n')
    probe=subprocess.run([executable,'--stdout','-r',str(root/'rules'),str(root/'base')],env=env,capture_output=True,timeout=60)
    if probe.returncode:pytest.skip('Hashcat present but stdout backend unavailable: external parity NOT VERIFIED')
    assert probe.stdout==b'Probe\n'
    return executable,env


def apply(bundle,runtime):
    executable,env=runtime;manifest=json.loads((bundle/'manifest.json').read_text());out=[]
    for segment in manifest['segments']:
        p=subprocess.run([executable,'--stdout','-r',str(bundle/segment['rules']['file']),
                          str(bundle/segment['bases']['file'])],capture_output=True,env=env,timeout=60)
        assert p.returncode==0,p.stderr
        out.extend(p.stdout.split(b'\n')[:-1])
    return out


@pytest.mark.parametrize('word',['Foo','Ab cD','aaaa','aA aA',"abc-DEF'xy3ZZ",'João','straße','İstanbul','$HEX[4142]'])
@pytest.mark.parametrize('leet',['none','partial','full'])
def test_real_hashcat_matches_python_case_title_leet_unicode(tmp_path,hashcat_runtime,word,leet):
    r=request(word,leet);reference=[v.encode() for v in GenerationService().prepare(r).iter_values()]
    dest=tmp_path/'bundle';m=export_bundle(r,dest)
    assert Counter(apply(dest,hashcat_runtime))==Counter(reference)
    assert m['counts']['retained']==m['counts']['exported']==len(reference)
    assert m['equivalence']['status']=='not-externally-verified'  # This test does not rewrite the manifest.
    for segment in m['segments']:
        for kind in ('bases','rules'):
            data=(dest/segment[kind]['file']).read_bytes()
            assert hashlib.sha256(data).hexdigest()==segment[kind]['sha256']
            assert len(data)==segment[kind]['bytes']


@pytest.mark.parametrize('separators',['',r'@!#$\^:', ' é\u00a0'])
@pytest.mark.parametrize('numbers',[('12','2026'),('',),('abc','!$\\'),('x'*32,)])
def test_real_affixes_hex_operands_long_fallback_and_empty_tokens(tmp_path,hashcat_runtime,separators,numbers):
    r=request('Qz',numbers=numbers,separators=separators);dest=tmp_path/'out';m=export_bundle(r,dest)
    expected=Counter(v.encode() for v in GenerationService().prepare(r).iter_values())
    assert Counter(apply(dest,hashcat_runtime))==expected
    if numbers==('x'*32,):assert m['materialization'].get('materialized-identity',0)>0


@pytest.mark.parametrize('cap',[1,2,10,50,256])
@pytest.mark.parametrize('policy',[PolicyOptions(),PolicyOptions(min_len=5,max_len=9,require_digit=True)])
def test_caps_and_policy_use_observed_pairs_without_cartesian_extras(tmp_path,hashcat_runtime,cap,policy):
    r=replace(request('Aa sS',leet='partial'),policy=policy,limits=GenerationLimits(max_candidates_per_word=cap))
    m=export_bundle(r,tmp_path/'out')
    expected=Counter(v.encode() for v in GenerationService().prepare(r).iter_values())
    assert Counter(apply(tmp_path/'out',hashcat_runtime))==expected
    assert m['counts']['exported']==sum(expected.values())


def test_reverse_is_independent_branch_and_ready_bypasses_rules(tmp_path,hashcat_runtime):
    ready=tmp_path/'ready';ready.write_text('ReadyOnly\n')
    r=replace(request('Ab',numbers=('123',),separators=''),sources=SourceOptions(ready_candidate_paths=(str(ready),)))
    export_bundle(r,tmp_path/'out');actual=apply(tmp_path/'out',hashcat_runtime)
    assert b'bA' in actual and b'bA123' not in actual
    assert b'ReadyOnly' in actual and b'ReadyOnly123' not in actual and b'READYONLY' not in actual
    assert Counter(actual)==Counter(v.encode() for v in GenerationService().prepare(r).iter_values())


@pytest.mark.parametrize('budget',[None,100])
@pytest.mark.parametrize('selector',[None,'diverse-v1'])
def test_compound_organization_ptbr_presets_and_retained_scope(tmp_path,hashcat_runtime,budget,selector):
    if not budget and selector:
        with pytest.raises(ValueError): RankingOptions(selector=selector)
        return
    r=GenerationRequest.from_dict({'preset':'corporate-br','organization':{'name':'Acme Corp Brasil','aliases':['ACMECorp']},
        'intelligence':{'reference_year':2026},'mutations':{'leet_mode':'none','separators':'@!'},
        'limits':{'max_candidates_per_word':50},'ranking':({'enabled':True,'budget':budget,**({'selector':selector} if selector else {})} if budget else {})})
    dest=tmp_path/'out';m=export_bundle(r,dest)
    assert Counter(apply(dest,hashcat_runtime))==Counter(v.encode() for v in GenerationService().prepare(r).iter_values())
    assert m['planning']['reference_year']==2026 and m['planning']['preset']=='corporate-br-v1'
    assert m['equivalence']['scope']=='retained-request-output'
    text=(dest/'manifest.json').read_text()
    assert 'Acme Corp Brasil' not in text and 'ACMECorp' not in text and str(tmp_path) not in text


def test_real_verified_manifest_is_published_only_after_comparison(tmp_path,hashcat_runtime):
    m=export_bundle(request(),tmp_path/'out',verify=True)
    assert m['equivalence']['status']=='exact-set'
    assert m['equivalence']['differential']=={'status':'passed','version':'v6.2.6','missing':0,'extra':0,'duplicates':0,'emitted':m['counts']['exported']}
    assert not list(tmp_path.glob('.mimic-hashcat-*'))


@pytest.mark.parametrize('bad',['Bad\nLine','Bad\x00Line','Bad\tLine','Bad\u2028Line','Bad\u2029Line','\ud800','x'*129])
def test_unrepresentable_values_strict_or_explicit_partial(tmp_path,bad):
    r=request(bad,numbers=(),separators='')
    with pytest.raises(BundleError):export_bundle(r,tmp_path/'strict')
    assert not (tmp_path/'strict').exists() and not list(tmp_path.glob('.mimic-hashcat-*'))
    m=export_bundle(r,tmp_path/'partial',allow_partial=True)
    assert m['equivalence']['coverage']=='partial' and m['equivalence']['status']=='not-externally-verified'
    assert sum(m['omitted'].values())==m['counts']['retained']-m['counts']['exported']


def test_literal_only_is_not_claimed_as_convergence(tmp_path):
    m=export_bundle(request('Foo',numbers=()),tmp_path/'out')
    assert m['mode']=='literal-identity-only'
    assert m['materialization']['materialized-identity']==m['counts']['exported']
    assert m['counts']['material_bytes']>m['counts']['expanded_exported_bytes']


def test_forged_affix_metadata_cannot_generate_other_values():
    c=Candidate('Actual',transformations=(Transformation('affix',(('input','Private'),('token','secret'),('placement','suffix'),('separator_position','none'))),))
    assert compile_pair(c)==(b'Actual',':','materialized-identity')


@pytest.mark.parametrize('limit',[BundleLimits(max_evaluated=1),BundleLimits(max_segments=1),BundleLimits(max_rules_per_base=1)])
def test_explicit_export_limits_fail_without_partial_publication(tmp_path,limit):
    with pytest.raises(BundleError):export_bundle(request(),tmp_path/'out',limits=limit)
    assert not (tmp_path/'out').exists() and not list(tmp_path.glob('.mimic-hashcat-*'))


@pytest.mark.parametrize('existing',['directory','file','symlink','broken-symlink'])
def test_existing_destination_never_overwritten(tmp_path,existing):
    target=tmp_path/'out'
    if existing=='directory':target.mkdir()
    elif existing=='file':target.write_text('KEEP')
    else:target.symlink_to(tmp_path/('missing' if existing=='broken-symlink' else 'out-parent'))
    with pytest.raises(FileExistsError):export_bundle(request(),target)
    if existing=='file':assert target.read_text()=='KEEP'


def test_symlink_parent_and_missing_parent_rejected(tmp_path):
    real=tmp_path/'real';real.mkdir();(tmp_path/'link').symlink_to(real,target_is_directory=True)
    for dest in (tmp_path/'link'/'out',tmp_path/'missing'/'out'):
        with pytest.raises(OSError):export_bundle(request(),dest)
    assert list(real.iterdir())==[]
    with pytest.raises(BundleError):export_bundle(request(),tmp_path/'..'/'out')


@pytest.mark.parametrize('phase',['write','fsync','publish','race','enospc'])
def test_faults_and_racing_empty_directory_do_not_publish_partial_bundle(tmp_path,monkeypatch,phase):
    dest=tmp_path/'out';original=module._publish
    def failure(*a,**kw):raise OSError(errno.ENOSPC if phase=='enospc' else errno.EACCES,'injected')
    if phase in ('write','enospc'):monkeypatch.setattr(module,'_write',failure)
    elif phase=='fsync':monkeypatch.setattr(os,'fsync',failure)
    elif phase=='publish':monkeypatch.setattr(module,'_publish',failure)
    else:
        def race(fd,src,target):dest.mkdir();original(fd,src,target)
        monkeypatch.setattr(module,'_publish',race)
    with pytest.raises(OSError):export_bundle(request(),dest)
    assert not list(tmp_path.glob('.mimic-hashcat-*'))
    if phase=='race':assert dest.is_dir() and list(dest.iterdir())==[]
    else:assert not dest.exists()


def test_special_directory_names_are_not_shell_commands(tmp_path,hashcat_runtime):
    dest=tmp_path/"'space $(touch OWNED); bundle"
    export_bundle(request(),dest,verify=True)
    assert not (tmp_path/'OWNED').exists()
    assert Counter(apply(dest,hashcat_runtime))==Counter(v.encode() for v in GenerationService().prepare(request()).iter_values())
    for p in dest.iterdir():assert p.stat().st_mode&0o777==0o600


def test_optional_verification_missing_or_wrong_hashcat_cleans_staging(tmp_path,monkeypatch):
    monkeypatch.setattr(shutil,'which',lambda _:None)
    with pytest.raises(BundleError,match='not-installed'):export_bundle(request(),tmp_path/'out',verify=True)
    assert not (tmp_path/'out').exists()
    assert not list(tmp_path.glob('.mimic-hashcat-*'))


@pytest.mark.parametrize('extra,code',[(['--output','x'],2),(['--export-rules','x'],2),(['--hashcat-verify'],0),([],0)])
def test_cli_bundle_contract_and_exit_codes(tmp_path,extra,code,hashcat_runtime):
    dest=tmp_path/'out'
    p=subprocess.run([sys.executable,'-m','mimic.cli','generate','-n','Foo','--no-intelligence','--leet','none',
       '--hashcat-bundle',str(dest),'--quiet','--no-banner',*extra],capture_output=True,text=True)
    assert p.returncode==code,p.stderr
    if code==0:assert p.stdout==p.stderr=='' and (dest/'manifest.json').exists()
    else:assert not dest.exists()


@pytest.mark.parametrize('seed',['1','42','777'])
def test_bundle_bytes_are_deterministic_across_hash_seeds(tmp_path,seed):
    script='''from mimic.application import *
from mimic.domain.models import Organization
from mimic.rules.bundle import export_bundle
import sys
r=GenerationRequest.from_dict({'preset':'corporate-br','organization':{'name':'Synthetic BR'},'intelligence':{'reference_year':2026},'mutations':{'leet_mode':'partial','separators':'@!'},'limits':{'max_candidates_per_word':50},'ranking':{'enabled':True,'budget':100,'selector':'diverse-v1'}})
export_bundle(r,sys.argv[1])
'''
    paths=[]
    for label,hashseed in [('expected','0'),('actual',seed)]:
        dest=tmp_path/label;paths.append(dest)
        p=subprocess.run([sys.executable,'-c',script,str(dest)],env={**os.environ,'PYTHONHASHSEED':hashseed},capture_output=True)
        assert p.returncode==0,p.stderr
    snapshot=lambda d:{p.name:p.read_bytes() for p in d.iterdir()}
    assert snapshot(paths[0])==snapshot(paths[1])


@pytest.mark.parametrize('operations',[1,31,32])
def test_compiler_operation_limit_and_rule_syntax(operations):
    from mimic.mutators.affix import AffixMutator
    candidate=next(c for c in AffixMutator(numbers=['x'*operations],separators='').mutate_candidate(Candidate('Q')) if c.value=='Q'+'x'*operations)
    base,rule,kind=compile_pair(candidate)
    if operations<=31:
        assert base==b'Q' and kind=='compiled-affix'
        assert rule==r'$\x78'*operations
    else:assert rule==':' and kind=='literal-fallback' and base==candidate.value.encode()


@pytest.mark.parametrize('operations',[31,32])
def test_real_hashcat_operation_ceiling(tmp_path,hashcat_runtime,operations):
    exe,env=hashcat_runtime;rule=tmp_path/'r';base=tmp_path/'b'
    rule.write_text(r'$\x23'*operations+'\n');base.write_text('Q\n')
    p=subprocess.run([exe,'--stdout','-r',str(rule),str(base)],env=env,capture_output=True,timeout=60)
    if operations==31:assert p.returncode==0 and p.stdout==b'Q'+b'#'*31+b'\n'
    else:assert p.returncode!=0


def test_seed_ready_packs_and_combine_materialize_before_rules(tmp_path,hashcat_runtime):
    import io
    from mimic.packs import PackRegistry
    registry=PackRegistry(tmp_path/'private-data')
    seed=registry.import_stream(io.BytesIO(b'Nova\n'),id='private-seed',version='1',kind='seed',filename='private.txt',language='pt-BR')
    ready=registry.import_stream(io.BytesIO(b'ReadyOnly\n'),id='private-ready',version='1',kind='ready',filename='private.txt',language='pt-BR')
    r=replace(request('Alice',numbers=('123',),separators='.'),base_candidates=(Candidate('Alice'),Candidate('Bob')),
      sources=SourceOptions(packs=(registry.reference(seed.identity),registry.reference(ready.identity))),
      mutations=MutationOptions(leet_mode='none',combine=True,separators='.'))
    service=GenerationService(registry);dest=tmp_path/'bundle';m=export_bundle(r,dest,service=service)
    actual=Counter(apply(dest,hashcat_runtime));expected=Counter(v.encode() for v in service.prepare(r).iter_values())
    assert actual==expected and b'ReadyOnly123' not in actual and b'alicebob123' in actual
    assert m['planning']['pack_digests']==[seed.sha256,ready.sha256]
    manifest=(dest/'manifest.json').read_text()
    assert 'private-seed' not in manifest and 'private-data' not in manifest and 'private.txt' not in manifest


def test_unknown_verification_version_rejected(tmp_path,monkeypatch):
    monkeypatch.setattr(shutil,'which',lambda _:'/synthetic/hashcat')
    calls=[]
    def run(args,**kw):calls.append(args);return b'v7.0.0\n'
    monkeypatch.setattr(module,'_run_hashcat',run)
    with pytest.raises(BundleError,match='unvalidated-hashcat-version'):export_bundle(request(),tmp_path/'out',verify=True)
    assert calls==[['/synthetic/hashcat','--version']] and not (tmp_path/'out').exists()


@pytest.mark.parametrize('extra,code',[(['--dataset','PRIVATE-MISSING'],2),(['--hashcat-allow-partial'],0),([],3)])
def test_cli_incompatible_inputs_and_private_errors(tmp_path,extra,code):
    # 129 UTF-8 bytes are deliberately outside the conservative contract.
    p=subprocess.run([sys.executable,'-m','mimic.cli','generate','-n','X'*129,'--no-intelligence','--leet','none',
         '--hashcat-bundle',str(tmp_path/'out'),'--quiet','--no-banner',*extra],capture_output=True,text=True)
    # Incompatible candidate can precede a missing streaming dataset; use short
    # input when testing the missing-source I/O branch.
    if extra and extra[0]=='--dataset':
        p=subprocess.run([sys.executable,'-m','mimic.cli','generate','-n','Foo','--no-intelligence',
           '--hashcat-bundle',str(tmp_path/'out'),'--quiet','--no-banner',*extra],capture_output=True,text=True)
    assert p.returncode==code,p.stderr
    assert 'PRIVATE-MISSING' not in p.stderr and 'X'*129 not in p.stderr
    if code:assert not (tmp_path/'out').exists()


def test_no_verification_means_no_subprocess_dependency(tmp_path,monkeypatch):
    def forbidden(*a,**kw):pytest.fail('normal export executed external program')
    monkeypatch.setattr(subprocess,'run',forbidden)
    monkeypatch.setattr(subprocess,'Popen',forbidden)
    export_bundle(request(),tmp_path/'out')


def test_unavailable_platform_is_controlled(tmp_path,monkeypatch):
    monkeypatch.setattr(module.sys,'platform','unsupported')
    with pytest.raises(BundleError,match='linux-atomic'):export_bundle(request(),tmp_path/'out')


@pytest.mark.parametrize('output',[b'',b'Q\nEXTRA\n',b'Q\nQ\n',b'Q'])
def test_differential_missing_extra_duplicate_and_unterminated_output_fail_closed(tmp_path,monkeypatch,output):
    r=replace(request('Q',numbers=()),policy=PolicyOptions(require_upper=True))
    monkeypatch.setattr(shutil,'which',lambda _:'/synthetic/hashcat')
    def run(args,**kw):
        if '--version' in args:return b'v6.2.6\n'
        assert '--stdout' in args and '-r' in args and '-m' not in args
        kw['stdout'].write(output)
    monkeypatch.setattr(module,'_run_hashcat',run)
    with pytest.raises(BundleError):export_bundle(r,tmp_path/'out',verify=True)
    assert not (tmp_path/'out').exists() and not list(tmp_path.glob('.mimic-hashcat-*'))


def test_verified_subset_is_never_labelled_exact_full_request(tmp_path,monkeypatch):
    ready=tmp_path/'ready';ready.write_text('Good\n'+'X'*129+'\n')
    r=GenerationRequest(sources=SourceOptions(ready_candidate_paths=(str(ready),)))
    monkeypatch.setattr(shutil,'which',lambda _:'/synthetic/hashcat')
    def run(args,**kw):
        if '--version' in args:return b'v6.2.6\n'
        kw['stdout'].write(b'Good\n')
    monkeypatch.setattr(module,'_run_hashcat',run)
    m=export_bundle(r,tmp_path/'out',allow_partial=True,verify=True)
    assert m['equivalence']['status']=='partial-request' and m['equivalence']['coverage']=='partial'
    assert m['counts']['retained']==2 and m['counts']['exported']==1
    assert m['equivalence']['differential']['missing']==m['equivalence']['differential']['extra']==0
