"""Independent Gate 14 evidence. Run by absolute path with PYTHONPATH=base or branch.

Modes: historical, contexts, catalog, jobs-create, jobs-reopen, determinism.
The last two job modes take the same external data directory. No network required.
"""

from collections import Counter
from dataclasses import asdict
import hashlib
import io
import json
import logging
from pathlib import Path
import resource
import sys
import tempfile
import time

logging.disable(logging.CRITICAL)
from mimic.application import (GenerationRequest, GenerationService, IntelligenceOptions,
    GenerationLimits, MutationOptions, RankingOptions, SourceOptions)
from mimic.domain.models import Organization, Target
from mimic.profile.schema import TargetProfile
from mimic.ranking.families import candidate_family


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def configuration(service=None, *, organization=True, corporate=False, mode='partial', budget='quick'):
    data = {'intelligence': {'reference_year': 2026, 'service_profiles': [service] if service else []},
        'mutations': {'leet_mode': mode, 'separators': '@!'},
        'limits': {'max_candidates_per_word': 30},
        'ranking': RankingOptions.from_budget(budget).to_dict()}
    if organization: data['organization'] = {'name': 'Synthetic Brasil', 'aliases': ['SB']}
    if corporate:
        data['preset'] = 'corporate-br'
        data['ranking']['selector'] = 'diverse-v1'
    return data


def observe(request):
    start = time.perf_counter()
    prepared = GenerationService().prepare(request)
    results = list(prepared.iter_results())
    elapsed = time.perf_counter() - start
    values = [r.candidate.value for r in results]
    assert len(values) == len(set(values))
    return {'request': request.to_dict(), 'summary': prepared.summary().to_dict(),
        'warnings': prepared.warnings, 'evaluated': prepared.evaluated_count, 'retained': len(results),
        'metadata_sha256': digest([r.to_dict() for r in results]),
        'wordlist_sha256': hashlib.sha256(''.join(v+'\n' for v in values).encode()).hexdigest(),
        'families': dict(Counter(candidate_family(r.candidate) for r in results)),
        'origins': dict(Counter(o.source+'.'+o.field for r in results for o in r.candidate.origins)),
        'seconds': elapsed, 'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}


def historical():
    cases = {}
    for service in (None, 'wordpress', 'mysql', 'postgresql', 'mssql', 'windows-ad', 'grafana', 'rabbitmq'):
        for mode in ('none', 'partial', 'full'):
            for budget in ('exhaustive', 'quick', 'focused'):
                key = f'{service}-{mode}-{budget}'
                cases[key] = GenerationRequest.from_dict(configuration(service, mode=mode, budget=budget))
    cases['acme-wordpress-2026'] = GenerationRequest(organization=Organization('ACME'),
        intelligence=IntelligenceOptions(reference_year=2026, service_profiles=('wordpress',)),
        ranking=RankingOptions(True, 100))
    cases['profile-date'] = GenerationRequest(target=Target('Ana', TargetProfile(nome='Ana',
        empresa='Empresa Composta', data_nascimento='01/02/1999')),
        mutations=MutationOptions(leet_mode='full', combine=True), limits=GenerationLimits(30),
        ranking=RankingOptions(True, 100, selector='diverse-v1'))
    cases['ptbr-common'] = GenerationRequest(sources=SourceOptions(include_ptbr=True,
        include_common_passwords=True), intelligence=IntelligenceOptions(reference_year=2026),
        mutations=MutationOptions(leet_mode='none'), ranking=RankingOptions(True,100))
    cases['corporate-br'] = GenerationRequest.from_dict(configuration(corporate=True))
    from mimic.packs import PackRegistry
    registry = PackRegistry(Path(tempfile.mkdtemp(prefix='gate14-pack-')))
    for identity, kind, data in [('seed', 'seed', b'Aurora\nNova\n'), ('ready', 'ready', b'Mudar2026!\nadmin\n')]:
        registry.import_stream(io.BytesIO(data), id=identity, version='1', kind=kind,
            filename='synthetic.txt', language='pt-BR')
    request = GenerationRequest(sources=SourceOptions(packs=tuple(registry.reference(i+'@1')
        for i in ('seed','ready'))), intelligence=IntelligenceOptions(reference_year=2026),
        mutations=MutationOptions(leet_mode='none'), ranking=RankingOptions(True,100))
    # Registry paths are external environmental inputs; use an identical fixed path
    # in both processes by accepting the caller's TMPDIR, then compare pack content
    # and all candidate provenance. The request itself includes only stable refs.
    cases['packs'] = request
    output = {}
    for key, request in cases.items():
        if key == 'packs':
            prepared = GenerationService(registry).prepare(request)
            results = list(prepared.iter_results())
            output[key] = {'request': request.to_dict(), 'summary': prepared.summary().to_dict(),
                'warnings': prepared.warnings, 'evaluated': prepared.evaluated_count,
                'retained': len(results), 'metadata_sha256': digest([r.to_dict() for r in results]),
                'wordlist_sha256': hashlib.sha256(''.join(r.candidate.value+'\n' for r in results).encode()).hexdigest()}
        else:
            output[key] = observe(request)
    assert (output['acme-wordpress-2026']['evaluated'], output['acme-wordpress-2026']['retained']) == (159175,100)
    return output


def contexts():
    return {label: observe(GenerationRequest.from_dict(configuration(service,
        organization=organization, corporate=corporate))) for label, service, organization, corporate in (
        ('organization', None, True, False), ('organization-old', 'wordpress', True, False),
        ('organization-new', 'zabbix', True, False), ('new-only', 'zabbix', False, False),
        ('corporate-br', None, True, True), ('corporate-br-new', 'zabbix', True, True))}


def catalog_evidence():
    from mimic.intelligence import catalog
    from mimic.intelligence.builtins import SERVICE_PROFILES
    from fastapi.testclient import TestClient
    from mimic.api import create_app
    start=time.perf_counter()
    for _ in range(100): catalog.validate_catalog()
    validation=(time.perf_counter()-start)/100
    searches = ('', 'ADMIN', 'sql', 'CI/CD', 'sonar', 'redis', 'WP', '不存在', 'x'*10000)
    start=time.perf_counter()
    for _ in range(100):
        for query in searches: catalog.list_services(query)
    search=(time.perf_counter()-start)/900
    with TestClient(create_app(data_dir=tempfile.mkdtemp(prefix='gate14-render-'))) as client:
        start=time.perf_counter()
        for service in catalog.SERVICES:
            for _ in range(5): assert client.get('/services/'+service.id).status_code == 200
        render=(time.perf_counter()-start)/(5*len(catalog.SERVICES))
    return {'services': [s.to_dict() for s in catalog.SERVICES],
        'profiles': [asdict(p) for p in SERVICE_PROFILES],
        'credentials': [c.to_dict() for c in catalog.DEFAULT_CREDENTIALS],
        'common': catalog.common_vocabulary().to_dict(), 'csv':catalog.credentials_csv(),
        'search':{q:[s.id for s in catalog.list_services(q)] for q in searches},
        'validation_seconds':validation,'search_seconds':search,'render_seconds':render,
        'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}


def jobs(root, reopen=False):
    from mimic.persistence import DataPaths, Database, Repository
    from mimic.jobs import JobManager
    from mimic.api import create_app
    from fastapi.testclient import TestClient
    paths=DataPaths(root); db=Database(paths); db.initialize(); repo=Repository(db)
    manager=JobManager(repo,paths); manager.start()
    evidence=[]
    try:
        if not reopen:
            for service in ('wordpress','mysql','postgresql','mssql','windows-ad','grafana','rabbitmq',None):
                request=GenerationRequest.from_dict(configuration(service, corporate=service is None))
                job=manager.submit(request); job=manager.wait(job['id'],60)
                assert job['status']=='completed',job
        for job in repo.list_jobs():
            request=GenerationRequest.from_dict(job['request'])
            prepared=GenerationService().prepare(request); results=list(prepared.iter_results())
            expected=''.join(r.candidate.value+'\n' for r in results).encode()
            assert manager.completed_output(job['id']).read_bytes()==expected
            rows=repo.list_preview(job['id'])
            for row in rows: row.pop('job_id')
            evidence.append({'id':job['id'],'request':job['request'],
                'evaluated':job['evaluated_count'],'retained':job['candidate_count'],
                'preview':rows,'output_sha256':hashlib.sha256(expected).hexdigest()})
    finally: manager.stop()
    with TestClient(create_app(data_dir=root)) as client:
        for row in evidence:
            response=client.get('/api/jobs/'+row['id']+'/download'); assert response.status_code==200
            assert hashlib.sha256(response.content).hexdigest()==row['output_sha256']
            assert client.get('/api/jobs/'+row['id']+'/candidates').status_code==200
    return evidence


if __name__ == '__main__':
    mode=sys.argv[1]
    if mode=='historical': output=historical()
    elif mode=='contexts': output=contexts()
    elif mode=='catalog': output=catalog_evidence()
    elif mode.startswith('jobs-'): output=jobs(Path(sys.argv[2]),mode=='jobs-reopen')
    elif mode=='determinism':
        output={'catalog':catalog_evidence(),'contexts':contexts(),
            'jobs':jobs(Path(tempfile.mkdtemp(prefix='gate14-seed-jobs-')))}
        # Measured clocks/RSS and opaque job UUIDs are explicitly outside the
        # deterministic generation contract. Preserve all request and preview data.
        for key in ('validation_seconds','search_seconds','render_seconds','peak_rss_kib'):
            output['catalog'].pop(key)
        for case in output['contexts'].values():
            case.pop('seconds');case.pop('peak_rss_kib')
        for job in output['jobs']: job.pop('id')
        output['jobs'].sort(key=lambda job:digest(job['request']))
    else: raise ValueError(mode)
    print(json.dumps(output,ensure_ascii=False,sort_keys=True,indent=2))
