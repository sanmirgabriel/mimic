"""Small synthetic differential/size evaluation; run from a development checkout.

python -m tests.block13_evaluation --output /tmp/block13-evaluation
Only Hashcat --stdout is used. No hashes, authentication or downloaded data.
"""
from collections import Counter
from dataclasses import replace
import argparse
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import time
from unittest.mock import patch

from mimic.application import GenerationRequest,GenerationService,MutationOptions,GenerationLimits,SourceOptions
from mimic.core.candidate import Candidate,Origin
from mimic.rules.bundle import export_bundle
from mimic.rules import bundle as module


def fixtures():
    cases=[]
    for mode in ('none','partial','full'):
        cases.append((f'ascii-{mode}',GenerationRequest(base_candidates=(Candidate('Ab aa CD',(Origin('manual','nome','Ab aa CD'),)),),
            number_candidates=(Candidate('123'),Candidate('2026')),mutations=MutationOptions(mode,separators='@!'))))
    cases.append(('corporate-br',GenerationRequest.from_dict({'preset':'corporate-br','organization':{'name':'Acme Corp Brasil','aliases':['ACMECorp']},
        'intelligence':{'reference_year':2026},'mutations':{'leet_mode':'none','separators':'@!'},'limits':{'max_candidates_per_word':256}})))
    cases.append(('unicode-policy',GenerationRequest.from_dict({'base_candidates':[{'value':'João ß','origins':[],'transformations':[]}],
        'number_candidates':[{'value':'2026','origins':[],'transformations':[]}], 'mutations':{'leet_mode':'partial','separators':'!'},'policy':{'max_len':12}})))
    return cases


def evaluate(root):
    logging.disable(logging.CRITICAL);root.mkdir()
    runtime=root/'runtime';(runtime/'data/hashcat/sessions').mkdir(parents=True)
    env={**os.environ,'XDG_DATA_HOME':str(runtime/'data'),'XDG_CACHE_HOME':str(runtime/'cache'),'POCL_CACHE_DIR':str(runtime/'pocl'),'POCL_MAX_PTHREAD_COUNT':'2'}
    executable=shutil.which('hashcat');rows=[]
    for name,request in fixtures():
        case=root/name;case.mkdir();t=time.perf_counter();prepared=GenerationService().prepare(request);plan=time.perf_counter()-t
        reference=Counter();t=time.perf_counter()
        with (case/'expanded.txt').open('wb') as f:
            for value in prepared.iter_values():
                raw=value.encode();reference[raw]+=1;f.write(raw+b'\n')
        generation=time.perf_counter()-t
        writing=planning=0;real_write=module._write
        def timed_write(*args):
            nonlocal writing
            t=time.perf_counter();result=real_write(*args);writing+=time.perf_counter()-t;return result
        class Timed(GenerationService):
            def prepare(self,request):
                nonlocal planning
                t=time.perf_counter();result=super().prepare(request);planning+=time.perf_counter()-t;return result
        t=time.perf_counter()
        with patch.object(module,'_write',timed_write):manifest=export_bundle(request,case/'bundle',service=Timed())
        export=time.perf_counter()-t;actual=Counter();apply_seconds=None
        if executable:
            t=time.perf_counter()
            for i,segment in enumerate(manifest['segments']):
                output=case/f'hashcat-{i}.txt'
                with output.open('wb') as stream:
                    process=subprocess.run([executable,'--stdout','-r',str(case/'bundle'/segment['rules']['file']),str(case/'bundle'/segment['bases']['file'])],env=env,stdout=stream,stderr=subprocess.PIPE,timeout=60)
                if process.returncode:raise RuntimeError('Hashcat stdout unavailable/failed; no external equivalence claim')
                with output.open('rb') as stream:
                    for line in stream:actual[line[:-1]]+=1
            apply_seconds=time.perf_counter()-t
            assert actual==reference
        expanded_bytes=(case/'expanded.txt').stat().st_size
        total=sum(p.stat().st_size for p in (case/'bundle').iterdir())
        rows.append({'fixture':name,'evaluated':prepared.evaluated_count,'candidates':sum(reference.values()),
            'expanded_bytes':expanded_bytes,'material_bytes':manifest['counts']['material_bytes'],'bundle_total_bytes':total,
            'segments':len(manifest['segments']),'base_lines':sum(s['bases']['lines'] for s in manifest['segments']),
            'rule_lines':sum(s['rules']['lines'] for s in manifest['segments']),
            'mimic_plan_seconds':plan,'mimic_generation_write_seconds':generation,'export_seconds':export,
            'export_plan_seconds':planning,'export_write_fsync_seconds':writing,'external_stdout_seconds':apply_seconds,
            'missing':sum((reference-actual).values()) if executable else None,'extra':sum((actual-reference).values()) if executable else None,
            'duplicates':sum(n-1 for n in actual.values()) if executable else None,'external_status':'passed' if executable else 'NOT VERIFIED'})
    (root/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
    return rows


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(evaluate(args.output),indent=2))
