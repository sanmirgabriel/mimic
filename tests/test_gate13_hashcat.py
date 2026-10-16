"""Independent Gate 13 adversarial checks; all data is fictitious/local."""
from collections import Counter
from dataclasses import asdict, replace
import errno
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

import pytest

from mimic.application import GenerationRequest, GenerationService, MutationOptions, PolicyOptions, SourceOptions
from mimic.core.candidate import Candidate, Origin, Transformation
from mimic.rules import bundle as module
from mimic.rules.bundle import BundleError, BundleLimits, compile_pair, export_bundle
from tests.test_hashcat_bundle import hashcat_runtime, request


def fake_executable(tmp_path, monkeypatch, body):
    path = tmp_path / 'synthetic-stdout-tool'
    path.write_text('#!' + sys.executable + '\nimport os,sys,time\n' + body)
    path.chmod(0o700)
    monkeypatch.setattr(module.shutil, 'which', lambda _: str(path))
    return path


def assert_integrity(root, manifest):
    """Audit consumer, not a production manifest-import API or rule interpreter."""
    assert manifest['format'] == 'mimic-hashcat-bundle-v1'
    names = {'manifest.json'}
    for segment in manifest['segments']:
        assert segment['outputs'] == segment['bases']['lines'] * segment['rules']['lines']
        for kind in ('bases', 'rules'):
            item = segment[kind]
            assert item['file'] == Path(item['file']).name and item['file'] not in names
            names.add(item['file'])
            data = (root / item['file']).read_bytes()
            assert data.endswith(b'\n')
            assert data.count(b'\n') == item['lines']
            assert len(data) == item['bytes']
            assert hashlib.sha256(data).hexdigest() == item['sha256']
    assert names == {p.name for p in root.iterdir()}
    count = manifest['counts']
    assert sum(s['outputs'] for s in manifest['segments']) == count['exported']
    assert count['retained'] == count['exported'] + sum(manifest['omitted'].values())
    assert sum(manifest['materialization'].values()) == count['exported']
    assert sum(s[k]['bytes'] for s in manifest['segments'] for k in ('bases', 'rules')) == count['material_bytes']
    assert root.stat().st_mode & 0o777 == 0o700
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in root.iterdir())


def independent_outputs(root, manifest, reference, runtime):
    exe, env = runtime
    accepted = Counter(c.value.encode() for c in reference)
    actual = Counter()
    for segment in manifest['segments']:
        process = subprocess.run([exe, '--stdout', '-r', str(root / segment['rules']['file']),
                                  str(root / segment['bases']['file'])], capture_output=True, env=env, timeout=60)
        assert process.returncode == 0, process.stderr
        assert process.stdout.endswith(b'\n')
        part = Counter(process.stdout[:-1].split(b'\n'))
        # Each segment separately must only emit values in the independent engine reference.
        assert not (part - accepted)
        assert sum(part.values()) == segment['outputs']
        actual.update(part)
    assert actual == accepted
    assert all(n == 1 for n in actual.values())
    return actual


@pytest.mark.parametrize('empty_kind', ['policy-empty', 'all-omitted'])
def test_empty_export_cannot_claim_external_verification(tmp_path, monkeypatch, empty_kind):
    r = replace(request('Q', numbers=()), policy=PolicyOptions(min_len=20))
    if empty_kind == 'all-omitted':
        r = request('X' * 129, numbers=())
    calls = []
    def version_only(args, **kwargs):
        from types import SimpleNamespace
        calls.append(args)
        return SimpleNamespace(stdout=b'v6.2.6\n', returncode=0)
    monkeypatch.setattr(module.shutil, 'which', lambda _: '/synthetic/hashcat')
    monkeypatch.setattr(module.subprocess, 'run', version_only)
    with pytest.raises(BundleError, match='no-exported-candidates-to-verify'):
        export_bundle(r, tmp_path / 'out', allow_partial=True, verify=True)
    assert calls == []
    assert not (tmp_path / 'out').exists()
    assert not list(tmp_path.glob('.mimic-hashcat-*'))


@pytest.mark.parametrize('channel', ['stdout', 'stderr', 'version'])
def test_external_output_budget_kills_and_reaps_process(tmp_path, monkeypatch, channel):
    pidfile = tmp_path / 'pid'
    body = "open(" + repr(str(pidfile)) + ", 'w').write(str(os.getpid()))\n"
    if channel != 'version':
        body += "if '--version' in sys.argv:\n print('v6.2.6');sys.exit()\n"
    fd = 2 if channel == 'stderr' else 1
    body += f"for i in range(128):os.write({fd}, b'X'*65536)\n"
    fake_executable(tmp_path, monkeypatch, body)
    ready = tmp_path / 'ready'; ready.write_text('Good\n')
    r = GenerationRequest(sources=SourceOptions(ready_candidate_paths=(str(ready),)))
    with pytest.raises(BundleError, match='hashcat-output-limit-exceeded'):
        export_bundle(r, tmp_path / 'out', verify=True)
    pid = int(pidfile.read_text())
    with pytest.raises(ProcessLookupError): os.kill(pid, 0)
    assert not (tmp_path / 'out').exists()
    assert not list(tmp_path.glob('.mimic-hashcat-*'))


@pytest.mark.parametrize('mode', ['none', 'partial', 'full'])
@pytest.mark.parametrize('word', ['assista', 'aA aA: foo-BAR', 'João', 'Joa\u0303o', 'Straße İ', '😀Aaé', 'aba'])
def test_adversarial_unicode_leet_palindrome_real(tmp_path, hashcat_runtime, mode, word):
    r = request(word, leet=mode, numbers=('xy', '2026'), separators='$#\\^ é😀')
    frozen = GenerationRequest.from_dict(r.to_dict())
    reference = list(GenerationService().prepare(frozen).iter_candidates())
    m = export_bundle(frozen, tmp_path / 'out')
    assert_integrity(tmp_path / 'out', m)
    independent_outputs(tmp_path / 'out', m, reference, hashcat_runtime)
    assert m['equivalence']['status'] == 'not-externally-verified'
    provenance = hashlib.sha256()
    for c in reference: provenance.update(json.dumps(asdict(c), ensure_ascii=True, sort_keys=True).encode() + b'\n')
    assert provenance.hexdigest() == m['candidate_provenance_sha256']
    if word == 'assista' and mode == 'partial':
        values = {c.value for c in reference}
        assert '@ssista' in values and '@$sista' in values and '@$$1$7@' not in values


@pytest.mark.parametrize('value', ['Q', 'Q'*127, 'Q'*128, 'é'*64, '😀'*32, '$HEX[244845585b343134325d]'])
def test_real_identity_autohex_byte_boundaries(tmp_path, hashcat_runtime, value):
    ready = tmp_path / 'ready'; ready.write_text(value + '\n')
    r = GenerationRequest(sources=SourceOptions(ready_candidate_paths=(str(ready),)))
    ref = list(GenerationService().prepare(r).iter_candidates())
    m = export_bundle(r, tmp_path / 'out')
    independent_outputs(tmp_path / 'out', m, ref, hashcat_runtime)
    assert m['mode'] == 'literal-identity-only'


@pytest.mark.parametrize('value', ['', 'Q'*129, 'é'*65, '😀'*33, '\x00', 'x\rY', 'x\x7fY', 'x\x85Y', 'x\u2028Y', 'x\u2029Y', '\udfff'])
def test_rejected_values_never_silently_change(value):
    with pytest.raises(BundleError): compile_pair(Candidate(value))


@pytest.mark.parametrize('operations', [30, 31, 32])
def test_real_operation_count_and_literal_fallback(tmp_path, hashcat_runtime, operations):
    r = request('Q', numbers=('é'*15 + ('x' if operations == 31 else 'xx' if operations == 32 else ''),), separators='')
    ref = list(GenerationService().prepare(r).iter_candidates())
    m = export_bundle(r, tmp_path / 'out')
    independent_outputs(tmp_path / 'out', m, ref, hashcat_runtime)
    if operations == 32: assert m['materialization']['literal-fallback'] > 0
    else: assert m['materialization']['compiled-affix'] > 0
    exe, env = hashcat_runtime
    (tmp_path / 'base').write_bytes(b'Q\n')
    (tmp_path / 'rule').write_text(r'$\x78' * operations + '\n')
    result = subprocess.run([exe, '--stdout', '-r', str(tmp_path/'rule'), str(tmp_path/'base')], env=env, capture_output=True, timeout=60)
    if operations <= 31: assert result.returncode == 0 and result.stdout == b'Q' + b'x'*operations + b'\n'
    else: assert result.returncode != 0


@pytest.mark.parametrize('budget', [100, 1000])
@pytest.mark.parametrize('selector', [None, 'diverse-v1'])
def test_quick_focused_true_retained_reference(tmp_path, hashcat_runtime, budget, selector):
    r = GenerationRequest.from_dict({'preset':'corporate-br', 'organization':{'name':'Luz Norte Sintética','aliases':['LNS']},
        'intelligence':{'reference_year':2026}, 'mutations':{'leet_mode':'partial','separators':'@!'},
        'limits':{'max_candidates_per_word':50}, 'ranking':{'enabled':True,'budget':budget, **({'selector':selector} if selector else {})}})
    p = GenerationService().prepare(r); ref = list(p.iter_candidates())
    m = export_bundle(r, tmp_path / 'out')
    assert m['counts']['evaluated'] == p.evaluated_count > budget
    assert m['counts']['retained'] == budget
    assert_integrity(tmp_path / 'out', m)
    independent_outputs(tmp_path / 'out', m, ref, hashcat_runtime)


def test_one_service_prepare_one_stream_and_first_cause(tmp_path):
    r = replace(request('aba'), base_candidates=(Candidate('aba',(Origin('manual','first','aba'),)), Candidate('aba',(Origin('manual','second','aba'),))))
    calls = Counter()
    class Service(GenerationService):
        def prepare(self, r):
            calls['prepare'] += 1
            prepared = super().prepare(r); original = prepared.iter_results
            def once(**kwargs):
                calls['iter_results'] += 1
                return original(**kwargs)
            prepared.iter_results = once
            return prepared
    m = export_bundle(r, tmp_path/'out', service=Service())
    assert calls == {'prepare':1,'iter_results':1}
    ref = list(GenerationService().prepare(r).iter_candidates())
    assert all(not any(o.field == 'second' for o in c.origins) for c in ref)
    assert m['counts']['retained'] == len(ref)


@pytest.mark.parametrize('corruption', ['base', 'rule', 'missing', 'extra', 'duplicate-segment', 'bad-count', 'bad-format'])
def test_independent_integrity_check_detects_corruption(tmp_path, corruption):
    root = tmp_path/'out'; m = export_bundle(request(), root)
    assert_integrity(root, m)
    s = m['segments'][0]
    if corruption in ('base', 'rule'):
        key = 'bases' if corruption == 'base' else 'rules'
        path = root/s[key]['file']; path.write_bytes(path.read_bytes() + b':\n')
    elif corruption == 'missing': (root/s['bases']['file']).unlink()
    elif corruption == 'extra': (root/'UNDECLARED').write_text('extra')
    elif corruption == 'duplicate-segment': m['segments'].append(s)
    elif corruption == 'bad-count': m['counts']['exported'] += 1
    else: m['format'] = 'unknown'
    with pytest.raises((AssertionError, FileNotFoundError)): assert_integrity(root, m)



@pytest.mark.parametrize('count', [64, 65])
def test_exact_segment_boundary_including_late_group(tmp_path, count):
    tokens = tuple(str(i) for i in range(1, 7))
    bases = [f'Q{i:03}Z' for i in range(1, count - 1)]
    ready = tmp_path / 'ready'; dataset = tmp_path / 'dataset'
    ready.write_text(''.join(base + token + '\n' for mask, base in enumerate(bases, 1)
                             for bit, token in enumerate(tokens) if mask & (1 << bit)))
    dataset.write_text('\n'.join(bases) + '\n')
    r = GenerationRequest(sources=SourceOptions(ready_candidate_paths=(str(ready),), dataset_paths=(str(dataset),)),
        number_candidates=tuple(Candidate(v) for v in tokens), mutations=MutationOptions(leet_mode='none', separators=''))
    if count == 65:
        with pytest.raises(BundleError, match='segment-limit'):
            export_bundle(r, tmp_path/'out', allow_partial=True)
        assert not (tmp_path/'out').exists()
    else:
        m = export_bundle(r, tmp_path/'out')
        assert len(m['segments']) == 64
        assert_integrity(tmp_path/'out', m)


@pytest.mark.parametrize('rule_count', [1024, 1025])
def test_exact_rules_per_base_boundary(tmp_path, rule_count):
    ready = tmp_path/'ready'; dataset = tmp_path/'dataset'
    tokens = tuple(f'Q{i:04}' for i in range(512))
    dataset.write_text('1\n'); ready.write_text('1' + tokens[0] + '\n' if rule_count == 1024 else '')
    r = GenerationRequest(sources=SourceOptions(ready_candidate_paths=(str(ready),), dataset_paths=(str(dataset),)),
        number_candidates=tuple(Candidate(v) for v in tokens), mutations=MutationOptions(leet_mode='none', separators=''))
    if rule_count == 1025:
        with pytest.raises(BundleError, match='rules-per-base-limit'):
            export_bundle(r, tmp_path/'out', allow_partial=True)
        assert not (tmp_path/'out').exists()
    else:
        m = export_bundle(r, tmp_path/'out')
        assert max(s['rules']['lines'] for s in m['segments']) == 1024
        assert_integrity(tmp_path/'out', m)


@pytest.mark.parametrize('phase', ['connect', 'statement', 'close'])
def test_sqlite_faults_leave_no_publication_and_no_fd_leak(tmp_path, monkeypatch, phase):
    original = module.sqlite3.connect
    before = len(list(Path('/proc/self/fd').iterdir()))
    class Broken(sqlite3.Connection):
        def execute(self, *args, **kwargs):
            if phase == 'statement': raise sqlite3.OperationalError('injected spool failure')
            return super().execute(*args, **kwargs)
        def close(self):
            super().close()
            if phase == 'close': raise sqlite3.OperationalError('injected close failure')
    def connect(*args, **kwargs):
        if phase == 'connect': raise sqlite3.OperationalError('injected open failure')
        return original(*args, **kwargs, factory=Broken)
    monkeypatch.setattr(module.sqlite3, 'connect', connect)
    for i in range(3):
        with pytest.raises(sqlite3.Error): export_bundle(request(), tmp_path/f'out-{i}')
    assert len(list(Path('/proc/self/fd').iterdir())) == before
    assert not list(tmp_path.glob('out-*')) and not list(tmp_path.glob('.mimic-hashcat-*'))


def test_bound_parent_survives_rename_and_symlink_substitution(tmp_path, monkeypatch):
    parent = tmp_path/'chosen'; parent.mkdir()
    moved = tmp_path/'moved'; outside = tmp_path/'other'; outside.mkdir()
    original = module._write; swapped = False
    def write(path, lines):
        nonlocal swapped
        if not swapped:
            swapped = True; parent.rename(moved); parent.symlink_to(outside, target_is_directory=True)
        return original(path, lines)
    monkeypatch.setattr(module, '_write', write)
    try:
        m = export_bundle(request(), parent/'out')
    except sqlite3.Error:
        # SQLite may reject a rename of its canonical journal path. Failure
        # must remain safe; an FD-bound publication must never follow the link.
        assert not (moved/'out').exists()
    else:
        assert_integrity(moved/'out', m)
    assert list(outside.iterdir()) == []
    assert not list(moved.glob('.mimic-hashcat-*'))


def test_hardlink_target_is_not_modified(tmp_path):
    original = tmp_path/'original'; original.write_bytes(b'KEEP')
    os.link(original, tmp_path/'out')
    with pytest.raises(FileExistsError): export_bundle(request(), tmp_path/'out')
    assert original.read_bytes() == b'KEEP' and (tmp_path/'out').read_bytes() == b'KEEP'


def test_competing_publishers_publish_one_complete_directory(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    def export(_):
        try: return export_bundle(request(), tmp_path/'out')
        except FileExistsError: return None
    with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(export, range(2)))
    assert sum(r is not None for r in results) == 1
    manifest = json.loads((tmp_path/'out/manifest.json').read_text())
    assert_integrity(tmp_path/'out', manifest)
    assert not list(tmp_path.glob('.mimic-hashcat-*'))


@pytest.mark.parametrize('kind', ['timeout', 'nonzero', 'permission', 'interrupted', 'mid-segment'])
def test_verification_errors_cleanup_and_preserve_environment(tmp_path, monkeypatch, kind):
    env_before = dict(os.environ)
    if kind == 'permission':
        path = fake_executable(tmp_path, monkeypatch, "pass\n"); path.chmod(0o600)
        with pytest.raises(OSError): export_bundle(request(), tmp_path/'out', verify=True)
    elif kind == 'mid-segment':
        calls = []
        def run(args, **kwargs):
            calls.append(args)
            if '--version' in args: return b'v6.2.6\n'
            if len(calls) == 3: raise BundleError('hashcat-stdout-failed')
        monkeypatch.setattr(module.shutil, 'which', lambda _: '/synthetic/hashcat')
        monkeypatch.setattr(module, '_run_hashcat', run)
        with pytest.raises(BundleError): export_bundle(request(), tmp_path/'out', verify=True)
        assert len(calls) == 3
    else:
        pidfile = tmp_path/'pid'
        body = f"open({str(pidfile)!r},'w').write(str(os.getpid()))\n"
        if kind == 'nonzero': body += "sys.exit(7)\n"
        else: body += "time.sleep(30)\n"
        path = fake_executable(tmp_path, monkeypatch, body)
        if kind == 'interrupted':
            original = module.selectors.DefaultSelector
            class Interrupt(original):
                def select(self, timeout=None):
                    time.sleep(0.05)
                    raise KeyboardInterrupt
            monkeypatch.setattr(module.selectors, 'DefaultSelector', Interrupt)
        children = []; popen = module.subprocess.Popen
        def tracked(*args, **kwargs):
            child = popen(*args, **kwargs); children.append(child); return child
        monkeypatch.setattr(module.subprocess, 'Popen', tracked)
        error = KeyboardInterrupt if kind == 'interrupted' else BundleError
        with pytest.raises(error):
            module._run_hashcat([str(path),'--stdout'], env=os.environ.copy(), timeout=0.2, max_bytes=129)
        assert len(children) == 1 and children[0].poll() is not None
        with pytest.raises(ProcessLookupError): os.kill(children[0].pid, 0)
    assert os.environ == env_before
    assert not (tmp_path/'out').exists() and not list(tmp_path.glob('.mimic-hashcat-*'))


def test_verified_partial_real_and_empty_unverified_are_honest(tmp_path, hashcat_runtime):
    ready = tmp_path/'ready'; ready.write_text('Good\n'+'X'*129+'\n')
    r = GenerationRequest(sources=SourceOptions(ready_candidate_paths=(str(ready),)))
    m = export_bundle(r, tmp_path/'partial', allow_partial=True, verify=True)
    assert m['equivalence']['status'] == 'partial-request'
    assert m['counts']['retained'] == 2 and m['counts']['exported'] == 1
    assert m['omitted'] == {'value-exceeds-128-utf8-bytes':1}
    assert_integrity(tmp_path/'partial', m)
    ready.write_text('X'*129+'\n')
    m = export_bundle(r, tmp_path/'empty', allow_partial=True)
    assert m['counts']['exported'] == 0 and m['counts']['retained'] == 1
    assert m['equivalence']['coverage'] == 'partial' and m['equivalence']['status'] == 'not-externally-verified'
    assert m['segments'] == []


@pytest.mark.parametrize('allow_partial', [False, True])
def test_accepted_scan_bound_is_exact_and_not_bypassed(tmp_path, allow_partial):
    r = request('Q', numbers=())
    count = len(list(GenerationService().prepare(r).iter_values()))
    m = export_bundle(r, tmp_path/'at-limit', limits=BundleLimits(max_evaluated=count), allow_partial=allow_partial)
    assert m['counts']['evaluated'] == count
    with pytest.raises(BundleError, match='accepted-scan-limit'):
        export_bundle(r, tmp_path/'over-limit', limits=BundleLimits(max_evaluated=count-1), allow_partial=allow_partial)
    assert not (tmp_path/'over-limit').exists()


@pytest.mark.parametrize('length', [127, 128])
def test_final_affix_byte_limit_and_partial_denominator_real(tmp_path, hashcat_runtime, length):
    r = request('Q'*length, numbers=('x',), separators='')
    reference = list(GenerationService().prepare(r).iter_candidates())
    allowed = [c for c in reference if len(c.value.encode()) <= 128]
    m = export_bundle(r, tmp_path/'out', allow_partial=True)
    independent_outputs(tmp_path/'out', m, allowed, hashcat_runtime)
    assert m['counts']['retained'] == len(reference)
    assert m['counts']['exported'] == len(allowed)
    assert sum(m['omitted'].values()) == len(reference) - len(allowed)
    if length == 128:
        with pytest.raises(BundleError): export_bundle(r, tmp_path/'strict')


@pytest.mark.parametrize('text', ['', '\n', '?\n'])
def test_real_hashcat_empty_and_invalid_rule_files_fail(tmp_path, hashcat_runtime, text):
    exe, env = hashcat_runtime
    (tmp_path/'base').write_text('Q\n'); (tmp_path/'rule').write_text(text)
    p = subprocess.run([exe,'--stdout','-r',str(tmp_path/'rule'),str(tmp_path/'base')], env=env, capture_output=True, timeout=60)
    assert p.returncode != 0 and p.stdout != b'Q\n'
    if text == '?\n': assert b'Skipping invalid or unsupported rule' in p.stdout


def test_cli_invalid_utf8_source_has_fixed_input_error(tmp_path):
    ready = tmp_path/'PRIVATE-SOURCE'; ready.write_bytes(b'\xff\n')
    p = subprocess.run([sys.executable,'-m','mimic.cli','generate','-n','Q','--no-intelligence','--no-banner','--quiet',
                        '--candidates',str(ready),'--hashcat-bundle',str(tmp_path/'out')],capture_output=True,text=True)
    assert p.returncode == 1
    assert 'PRIVATE-SOURCE' not in p.stderr and 'Traceback' not in p.stderr
    assert not (tmp_path/'out').exists()


@pytest.mark.parametrize('flag', [['--hashcat-bundle', ''], ['--hashcat-bundle=']])
def test_empty_cli_destination_never_falls_back_to_wordlist(tmp_path, flag):
    p = subprocess.run([sys.executable,'-m','mimic.cli','generate','-n','Q','--no-intelligence','--leet','none',
                        '--quiet','--no-banner',*flag],capture_output=True,text=True)
    assert p.returncode == 2 and p.stdout == ''
    assert '--hashcat-bundle' in p.stderr and 'Traceback' not in p.stderr
