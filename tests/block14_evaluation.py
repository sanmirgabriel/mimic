"""Synthetic Block 14 cost/causality evidence; no network or credential checks.

Run ``python -m tests.block14_evaluation``. Each case runs in a fresh process;
RSS includes the interpreter/imports and Core dedup. Timing is observational.
"""
from collections import Counter
from dataclasses import replace
from unittest.mock import patch
import argparse
import hashlib
import json
import logging
import resource
import subprocess
import sys
import time

from mimic.application import GenerationRequest, GenerationService
from mimic.intelligence.builtins import get_service_profile

CASES = ('no-service', 'old-service', 'new-service', 'organization-new', 'corporate-br-new')


def configuration(case):
    data = {'organization': {'name': 'Synthetic'},
        'intelligence': {'reference_year': 2026},
        'mutations': {'leet_mode': 'partial', 'separators': '!'},
        'limits': {'max_candidates_per_word': 50},
        'ranking': {'enabled': True, 'budget': 100}}
    if case == 'old-service':
        data['intelligence']['service_profiles'] = ['wordpress']
    elif case in ('new-service', 'organization-new', 'corporate-br-new'):
        data['intelligence']['service_profiles'] = ['zabbix']
    if case in ('old-service', 'new-service'):
        data.pop('organization')
    if case == 'corporate-br-new':
        data['preset'] = 'corporate-br'
        data['ranking']['selector'] = 'diverse-v1'
    return data


def measure(case):
    from mimic.ranking.families import candidate_family
    logging.disable(logging.CRITICAL)
    start = time.perf_counter()
    req = GenerationRequest.from_dict(configuration(case))
    prepared = GenerationService().prepare(req)
    prepare_seconds = time.perf_counter() - start
    start = time.perf_counter()
    results = list(prepared.iter_results())
    elapsed = time.perf_counter() - start
    values = [r.candidate.value for r in results]
    summary = prepared.summary().to_dict()
    profiles = [get_service_profile(s) for s in req.intelligence.service_profiles]
    normal_peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # A separate diagnostic replay counts only global dedup after existing stage
    # caps/dedup. Its extra set, counters and runtime are excluded from metrics.
    from mimic.core.generator import Generator
    from mimic.application import RankingOptions
    raw = 0
    seen = set()
    original = Generator._raw_candidates
    def observed(engine):
        nonlocal raw
        for candidate in original(engine):
            raw += 1
            seen.add(candidate.value)
            yield candidate
    families = Counter()
    with patch.object(Generator, '_raw_candidates', observed):
        diagnostic = GenerationService().prepare(replace(req, ranking=RankingOptions()))
        for candidate in diagnostic.iter_candidates():
            families[candidate_family(candidate)] += 1
    assert diagnostic.evaluated_count == prepared.evaluated_count
    return {'case': case, 'request': req.to_dict(), 'summary': summary,
        'service_tokens': [t for p in profiles for t in p.tokens],
        'service_roles': [v for p in profiles for v in p.roles],
        'service_seeds': summary['service_derived_seed_count'],
        'templates': summary['knowledge_template_seed_count'],
        'accepted': prepared.evaluated_count, 'retained': len(results),
        'duplicate_retained': len(values) - len(set(values)),
        'raw_after_stage_caps': raw, 'global_duplicates_removed': raw-len(seen),
        'unique_before_policy': len(seen), 'accepted_families': dict(families),
        'families': dict(Counter(candidate_family(r.candidate) for r in results)),
        'scores': dict(Counter(r.score.total for r in results)),
        'origins': dict(Counter(o.source+'.'+o.field for r in results for o in r.candidate.origins)),
        'result_sha256': hashlib.sha256(json.dumps([r.to_dict() for r in results],
            sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
        'wordlist_sha256': hashlib.sha256(('\n'.join(values)+'\n').encode()).hexdigest(),
        'warnings': prepared.warnings, 'prepare_seconds': prepare_seconds,
        'generate_seconds': elapsed, 'peak_rss_kib': normal_peak_rss}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=CASES)
    args = parser.parse_args()
    if args.case:
        output = measure(args.case)
    else:
        output = [json.loads(subprocess.check_output([sys.executable, '-B', '-m',
            'tests.block14_evaluation', '--case', case])) for case in CASES]
    print(json.dumps(output,ensure_ascii=False,sort_keys=True,indent=2))


if __name__ == '__main__':
    main()
