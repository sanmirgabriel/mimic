"""Small synthetic offline Block 12.6 evaluation; not part of production package.

Reproduce: python -m tests.block12_6_benchmark --output /tmp/block126.json
Policy is fixed independently of the holdout literals below. No tuning loop.
Native time/RSS are measured in fresh worker processes; no tracemalloc overhead.
"""
from collections import Counter, defaultdict
from dataclasses import asdict
import argparse
import hashlib
import json
import logging
from pathlib import Path
import resource
import subprocess
import sys
import time

from mimic.application import GenerationRequest, GenerationService
from mimic.ranking.families import candidate_family
from mimic.ranking.scoring import score_candidate

# Frozen synthetic holdouts. Diagnostic examples are evaluated separately.
HOLDOUTS = (
    {'name':'Lumen Sistemas Norte','aliases':['LSN'], 'targets':[
        'LumenSistemasNorte123@','LSN2026!','Lumen2025','LSNadmin2026',
        'adminLSN2026','LSNsuporte2026!','Lumen Sistemas Norteadmin2026',
        'Mudar@123','Senha2026!','Acesso123','Trocar2025!', 'Bemvindo123@',
        'Flamengo2026','Flamengo123','mudar','password',
        'LSN-2026-XYZ','LumenNorte789?','NoSuchToken2026!', 'LSN2031!']},
    {'name':'Vela Rede Sul','aliases':['VRS'], 'targets':[
        'VelaRedeSul123@','VRS2026!','Vela2025','VRSadmin2026',
        'adminVRS2026','VRShelpdesk2026!','Vela Rede Suladmin2026',
        'Mudar@123','Senha2026!','Usuario123','Brasil2025!', 'Trabalho123@',
        'Flamengo2026','Flamengo123','mudar','changeme',
        'VRS-2026-XYZ','VelaSul789?','NoSuchToken2026!', 'VRS2031!']},
)
DIAGNOSTIC = {'name':'Acme Corp Brasil','aliases':[],
              'targets':['AcmeCorpBrasil123@','ACMECorp2026!','Mudar@123','Senha2026!']}
POLICY = 'best per candidate-family-v1, fill by original score/encounter; no literal rules'


def request_data(context, source='combined', leet='partial', separators='@!#_.', numbers=True, cap=5000):
    return {'organization':{'name':context['name'],'aliases':context['aliases']},
            'organization_variants':True,
            'sources':{'include_ptbr':source in ('ptbr','combined'),
                       'include_common_passwords':source=='combined'},
            'intelligence':{'enabled':True,'common_numbers':numbers,'recent_years':True,
                            'corporate_roles':source!='ptbr','reference_year':2026},
            'mutations':{'leet_mode':leet,'separators':separators},
            'limits':{'max_candidates_per_word':cap},
            **({'preset':'corporate-br-v1'} if source=='combined' else {})}


def shape(candidate):
    """Literal-free sibling shape: direction, case, leet count, affix geometry.

    Different literal stems/numbers/separator characters may share a shape.
    Descriptive concentration only; this is not another selection taxonomy.
    """
    templates=[];cases=[];leet=0;affix=[]
    for step in candidate.transformations:
        params=dict(step.params)
        if step.kind=='knowledge_template': templates.append(params.get('template','unknown'))
        if step.kind=='case':cases.append(params.get('mode','unknown'))
        if step.kind=='leet':leet+=1
        if step.kind=='affix':affix.append((params.get('placement','unknown'),params.get('separator_position','unknown')))
    return json.dumps([templates,cases,min(leet,3),affix],sort_keys=True)


def worker(payload):
    logging.disable(logging.CRITICAL)
    data=payload['request']; targets=payload['targets']; budget=payload.get('budget')
    if budget:
        data={**data,'ranking':{'enabled':True,'budget':budget,
                              **({'selector':'diverse-v1'} if payload.get('selector') else {})}}
    req=GenerationRequest.from_dict(data); prepared=GenerationService().prepare(req)
    universe=hashlib.sha256(); seen_targets={}; families=Counter(); shapes=Counter()
    sums=defaultdict(lambda: {'count':0,'min':10**9,'max':-10**9,'sum':0,'components':Counter()})
    retained=[]
    # Instrument accepted stream, preserving Candidate identity/order and engine.
    original=prepared._planned.generator.generate_candidates
    def stream():
        for index,candidate in enumerate(original()):
            universe.update(candidate.value.encode()+b'\0')
            if candidate.value in targets:
                score=score_candidate(candidate,2026)
                seen_targets[candidate.value]={'encounter_index':index,'score':score.total,
                                               'family':candidate_family(candidate)}
            yield candidate
    prepared._planned.generator.generate_candidates=stream
    start=time.perf_counter(); cpu=time.process_time()
    for result in prepared.iter_results():
        candidate=result.candidate
        if not budget:continue
        retained.append(candidate.value);family=candidate_family(candidate);families[family]+=1
        shapes[(family,shape(candidate))]+=1
        stats=sums[family];stats['count']+=1;stats['sum']+=result.score.total
        stats['min']=min(stats['min'],result.score.total);stats['max']=max(stats['max'],result.score.total)
        for component in result.score.components:stats['components'][component.code]+=component.delta
    elapsed=time.perf_counter()-start;cpu=time.process_time()-cpu
    ranks={v:i for i,v in enumerate(retained,1) if v in targets}
    output={'evaluated':prepared.evaluated_count,'accepted_digest':universe.hexdigest(),
            'wall_seconds':elapsed,'cpu_seconds':cpu,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            'covered_targets':seen_targets,'retained_targets':ranks,'retained':retained,
            'families':dict(families),'distinct_families':len(families),
            'largest_family_share':max(families.values(),default=0)/len(retained) if retained else None,
            'largest_sibling_shape_share':max(shapes.values(),default=0)/len(retained) if retained else None,
            'scores_by_family':dict(sums)}
    if not budget:
        # Exact global score ranks for targets found, by second streaming pass.
        counts={v:1 for v in seen_targets}
        for index,candidate in enumerate(GenerationService().prepare(req).iter_candidates()):
            score=score_candidate(candidate,2026).total
            for value,info in seen_targets.items():
                if score>info['score'] or (score==info['score'] and index<info['encounter_index']):counts[value]+=1
        output['global_score_ranks']=counts
    return output


def run_worker(payload):
    p=subprocess.run([sys.executable,'-m','tests.block12_6_benchmark','--worker'],input=json.dumps(payload),
                     capture_output=True,text=True,check=True)
    return json.loads(p.stdout)


def evaluate():
    result={'policy':POLICY,'holdouts':HOLDOUTS,'diagnostic':DIAGNOSTIC,'evaluation':[],'cost_matrix':[]}
    for context in (*HOLDOUTS,DIAGNOSTIC):
        data=request_data(context);payload={'request':data,'targets':context['targets']}
        exhaustive=run_worker(payload)
        case={'name':context['name'],'denominator':len(context['targets']),'exhaustive':exhaustive,'budgets':{}}
        for k in (100,1000,10000):
            base=run_worker({**payload,'budget':k});div=run_worker({**payload,'budget':k,'selector':True})
            assert base['accepted_digest']==div['accepted_digest']==exhaustive['accepted_digest']
            b=set(base.pop('retained'));d=set(div.pop('retained'))
            case['budgets'][str(k)]={'score-v1':base,'diverse-v1':div,
                'displaced_baseline_count':len(b-d),'added_count':len(d-b),
                'lost_holdout_targets':sorted((b-d)&set(context['targets'])),
                'gained_holdout_targets':sorted((d-b)&set(context['targets']))}
        exhaustive.pop('retained'); result['evaluation'].append(case)
    context=DIAGNOSTIC
    for source in ('corporate','ptbr','combined'):
        for leet,separators,numbers in [('none','@!',True),('partial','@!#_.',True),
                                       ('full','@!',True),('none','',False)]:
            for selector in (False,True):
                data=request_data(context,source,leet,separators,numbers)
                measurement=run_worker({'request':data,'targets':context['targets'],'budget':100,'selector':selector})
                measurement.pop('retained')
                result['cost_matrix'].append({'source':source,'leet':leet,'separators':separators,
                    'numbers':numbers,'selector':'diverse-v1' if selector else 'score-v1',**measurement})
    return result


def stage_diagnostics():
    """Trace seeds, Affix construction, frontier, Policy and exhaustive separately."""
    from unittest.mock import patch
    from mimic.core.generator import Generator
    from mimic.mutators.affix import AffixMutator
    logging.disable(logging.CRITICAL)
    targets={'AcmeCorpBrasil123@':'AcmeCorpBrasil','ACMECorp2026!':'ACMECorp','Mudar@123':'Mudar','Senha2026!':'Senha'}
    results=[]
    for leet in ('none','partial','full'):
     for cap in (50,256,5000):
      for max_len in (0,12):
       seeds=set();constructed=set();survive=set();decisions={}
       compose=Generator._compose;affix=AffixMutator.mutate_candidate;raw=Generator._raw_candidates
       def tracked_compose(self,seed,stages=None):
        if seed.value in targets.values():seeds.add(seed.value)
        return compose(self,seed,stages)
       def tracked_affix(self,candidate):
        for out in affix(self,candidate):
         if out.value in targets:constructed.add(out.value)
         yield out
       def tracked_raw(self):
        for out in raw(self):
         if out.value in targets:survive.add(out.value)
         yield out
       r=GenerationRequest.from_dict({'preset':'corporate-br','organization':{'name':'Acme Corp Brasil'},'intelligence':{'reference_year':2026},'mutations':{'leet_mode':leet,'separators':'@!'},'limits':{'max_candidates_per_word':cap},'policy':{'max_len':max_len}})
       p=GenerationService().prepare(r);policy=p._planned.generator.policy.accepts
       def tracked_policy(value):
        accepted=policy(value)
        if value in targets:decisions[value]=accepted
        return accepted
       p._planned.generator.policy.accepts=tracked_policy
       with patch.object(Generator,'_compose',tracked_compose),patch.object(AffixMutator,'mutate_candidate',tracked_affix),patch.object(Generator,'_raw_candidates',tracked_raw):
        found={c.value for c in p.iter_candidates() if c.value in targets}
       results.append({'leet':leet,'cap':cap,'max_len':max_len,'evaluated':p.evaluated_count,'targets':{t:{'seed_seen':stem in seeds,'constructed':t in constructed,'survived_frontier':t in survive,'policy':decisions.get(t),'exhaustive':t in found} for t,stem in targets.items()}})
    return results


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path);parser.add_argument('--worker',action='store_true');parser.add_argument('--stages',action='store_true')
    args=parser.parse_args()
    if args.worker: print(json.dumps(worker(json.load(sys.stdin))))
    else:
        result=stage_diagnostics() if args.stages else evaluate()
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
