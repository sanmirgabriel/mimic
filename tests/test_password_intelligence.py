"""Block 7: bounded knowledge inputs, exact causality and shared adapter flows."""
from __future__ import annotations

import ast
import json
import logging
import os
from dataclasses import asdict, replace
from pathlib import Path
import re
import subprocess
import sys
import threading

import pytest

from mimic.application import (
    GenerationLimits, GenerationRequest, GenerationService, IntelligenceOptions,
    InvalidGenerationRequest, MutationOptions, PolicyOptions, SourceOptions,
)
from mimic.cli import main
from mimic.core.candidate import Candidate, Origin, Transformation
from mimic.domain.context import ExtractedFact
from mimic.domain.models import Organization, Target
from mimic.intelligence.builtins import (
    COMMON_NUMBERS, CORPORATE_ROLES, KNOWLEDGE_VERSION, SERVICE_PROFILES, get_service_profile,
)
from mimic.intelligence.planning import plan_intelligence, recent_years
from mimic.jobs import JobManager
from mimic.profile.schema import TargetProfile
from tests.test_local_api_jobs import store
from tests.test_web_ui import web, submit, token


def request(**kwargs):
    return GenerationRequest(
        intelligence=kwargs.pop('intelligence', IntelligenceOptions(reference_year=2026, service_profiles=('wordpress',))),
        mutations=kwargs.pop('mutations', MutationOptions(leet_mode='none', separators='!#*@')),
        **kwargs,
    )


@pytest.fixture(scope='module')
def organization_candidates():
    return {c.value: c for c in GenerationService().prepare(request(organization=Organization('ACME'))).iter_candidates()}


def test_common_numbers_and_recent_years_exact():
    assert COMMON_NUMBERS == ('123', '321', '1234', '4321', '12345', '123456', '000', '0000', '111', '1111')
    assert recent_years(2026) == (2026, 2025, 2024, 2023)
    plan = plan_intelligence(IntelligenceOptions(reference_year=2026))
    assert plan.numbers == tuple(
        Candidate(value, (Origin('knowledge', field, value),))
        for field, values in (('common_number', COMMON_NUMBERS), ('recent_year', ('2026','2025','2024','2023')))
        for value in values
    )
    assert plan_intelligence(IntelligenceOptions(enabled=False)).numbers == ()
    assert plan_intelligence(IntelligenceOptions(reference_year=2026, common_numbers=False, recent_years=False)).numbers == ()


def test_corporate_roles_and_templates_are_structured():
    term = Candidate('ACME', (Origin('organization', 'name', 'ACME'),))
    plan = plan_intelligence(IntelligenceOptions(reference_year=2026), (term,))
    by_value = {s.candidate.value: s for s in plan.seeds}
    for role in CORPORATE_ROLES:
        assert by_value[role].candidate == Candidate(role, (Origin('knowledge', 'role', role),))
    assert by_value['ACMEadmin'].candidate == Candidate('ACMEadmin', (
        Origin('organization', 'name', 'ACME'), Origin('knowledge', 'role', 'admin'),
    ), (Transformation('knowledge_template', (
        ('template', 'organization_role'), ('left', 'ACME'), ('right', 'admin'), ('version', 'knowledge-v1'),
    )),))
    assert by_value['adminACME'].candidate.origins == (
        Origin('knowledge', 'role', 'admin'), Origin('organization', 'name', 'ACME'))
    assert all(seed.mutable and not seed.combinable for seed in plan.seeds)
    disabled = plan_intelligence(IntelligenceOptions(reference_year=2026, corporate_roles=False), (term,))
    assert [seed.candidate.value for seed in disabled.seeds] == []


@pytest.mark.parametrize('service_id,display,tokens,roles', [
    ('wordpress','WordPress',('WordPress','wp'),('admin','editor')),
    ('mysql','MySQL',('mysql','sql','db'),('root','dba')),
    ('postgresql','PostgreSQL',('postgresql','postgres','db'),('postgres','dba')),
    ('mssql','Microsoft SQL Server',('mssql','sql','db'),('sa','dba')),
    ('windows-ad','Windows / Active Directory',('windows','AD'),('administrator','svc')),
])
def test_service_profiles(service_id, display, tokens, roles):
    profile = get_service_profile(service_id)
    assert (profile.id, profile.display_name, profile.tokens, profile.roles, profile.version) == (
        service_id, display, tokens, roles, KNOWLEDGE_VERSION)
    term = Candidate('ACME', (Origin('organization','name','ACME'),))
    plan = plan_intelligence(IntelligenceOptions(reference_year=2026, corporate_roles=False, service_profiles=(service_id,)), (term,))
    seeds = {}
    for seed in plan.seeds:
        seeds.setdefault(seed.candidate.value, seed.candidate)
    for value in tokens:
        assert seeds[value].origins == (Origin('knowledge',f'service.{service_id}.token',value),)
        assert any(s.candidate.value == 'ACME' + value and s.candidate.origins == term.origins + seeds[value].origins for s in plan.seeds)
        assert any(s.candidate.value == value + 'ACME' and s.candidate.origins == seeds[value].origins + term.origins for s in plan.seeds)
        assert seeds[value + roles[0]].origins == seeds[value].origins + (Origin('knowledge',f'service.{service_id}.role',roles[0]),)
    assert len({p.id for p in SERVICE_PROFILES}) == 5


@pytest.mark.parametrize('config', [
    {'enabled':'yes'}, {'common_numbers':1}, {'recent_years':'false'}, {'corporate_roles':[]},
    {'reference_year':True}, {'reference_year':2026.5}, {'reference_year':3}, {'reference_year':10000},
    {'service_profiles':'wordpress'}, {'service_profiles':['unknown']}, {'extra':True},
])
def test_invalid_options_rejected(config):
    with pytest.raises(InvalidGenerationRequest):
        GenerationRequest.from_dict({'intelligence': config})


def test_reference_year_capture_and_json_roundtrip():
    r = request(organization=Organization('São Paulo', aliases=['Árvore']), intelligence=IntelligenceOptions(
        service_profiles=['wordpress','mysql','wordpress'], common_numbers=False, corporate_roles=False, reference_year=2026))
    payload = json.loads(json.dumps(r.to_dict(), ensure_ascii=False))
    after = GenerationRequest.from_dict(payload)
    assert after.to_dict() == r.to_dict()
    assert after.intelligence == IntelligenceOptions(
        common_numbers=False, corporate_roles=False, service_profiles=('wordpress','mysql'), reference_year=2026)
    assert after.organization.name == 'São Paulo'
    captured = GenerationRequest(intelligence=IntelligenceOptions())
    assert type(captured.intelligence.reference_year) is int
    assert GenerationRequest.from_dict(captured.to_dict()).intelligence.reference_year == captured.intelligence.reference_year
    assert GenerationRequest.from_dict({}).intelligence.enabled is False


def affix_steps(value, token, separator):
    return Transformation('affix', (
        ('input', value), ('token', token), ('placement','suffix'), ('separator',separator),
        ('separator_position','after'), ('input_steps','1'), ('token_steps','0'),
    ))


def test_organization_only_numeric_provenance_exact(organization_candidates):
    for value, token, sep, field in (('Acme123!', '123','!','common_number'), ('Acme2026#','2026','#','recent_year')):
        assert organization_candidates[value] == Candidate(value, (
            Origin('organization','name','ACME'), Origin('knowledge',field,token),
        ), (Transformation('case',(('mode','title'),)), affix_steps('Acme',token,sep)))
    assert organization_candidates['123Acme'].origins == (
        Origin('organization','name','ACME'), Origin('knowledge','common_number','123'))
    assert dict(organization_candidates['123Acme'].transformations[-1].params)['placement'] == 'prefix'
    assert organization_candidates['Acme@123'].origins == organization_candidates['Acme123!'].origins


@pytest.mark.parametrize('value,left,right,field,template_id,token,separator', [
    ('Acmeadmin123!','ACME','admin','role','organization_role','123','!'),
    ('adminACME123*','admin','ACME','role','organization_role_reverse','123','*'),
    ('wpACME123#','wp','ACME','service.wordpress.token','organization_service_reverse','123','#'),
    ('ACMEWordPress123#','ACME','WordPress','service.wordpress.token','organization_service','123','#'),
])
def test_template_family_exact_causal_metadata(organization_candidates, value, left, right, field, template_id, token, separator):
    operands = tuple(Origin('organization','name',v) if v == 'ACME' else Origin('knowledge',field,v) for v in (left,right))
    seed_value = left + right
    case_mode = 'title' if value == 'Acmeadmin123!' else 'original'
    case_value = seed_value.title() if case_mode == 'title' else seed_value
    assert organization_candidates[value] == Candidate(value, operands + (Origin('knowledge','common_number',token),), (
        Transformation('knowledge_template', (
            ('template',template_id), ('left',left), ('right',right), ('version','knowledge-v1'))),
        Transformation('case',(('mode',case_mode),)),
        Transformation('affix', (
            ('input',case_value), ('token',token), ('placement','suffix'), ('separator',separator),
            ('separator_position','after'), ('input_steps','2'), ('token_steps','0'))),
    ))


def test_role_affix_exact(organization_candidates):
    assert organization_candidates['admin321@'] == Candidate('admin321@', (
        Origin('knowledge','role','admin'), Origin('knowledge','common_number','321'),
    ), (Transformation('case',(('mode','original'),)), affix_steps('admin','321','@')))


@pytest.mark.parametrize('mode', ['profile','context'])
def test_company_field_preserves_origin(mode):
    kwargs = {'target':Target('',TargetProfile(empresa='ACME'))} if mode == 'profile' else {
        'context_facts':(ExtractedFact('empresa',Candidate('ACME',(Origin('profile','empresa','ACME'),))),)}
    candidates = {c.value:c for c in GenerationService().prepare(request(**kwargs)).iter_candidates()}
    assert candidates['Acme123!'].origins == (Origin('profile','empresa','ACME'),Origin('knowledge','common_number','123'))
    assert candidates['Acmeadmin123!'].origins == (
        Origin('profile','empresa','ACME'), Origin('knowledge','role','admin'), Origin('knowledge','common_number','123'))


def test_organization_alias_domains_and_prepared_isolation():
    org = Organization('', aliases=['Lab'], domains=['ACME.com.br', 'https://skip.test', 'single', '-bad.test'])
    r = request(organization=org, limits=GenerationLimits(max_candidates_per_word=200))
    plan = GenerationService().prepare(r)
    org.aliases.append('Changed')
    candidates = {c.value:c for c in plan.iter_candidates()}
    assert candidates['acme123!'].origins == (Origin('organization','domain','ACME.com.br'),Origin('knowledge','common_number','123'))
    assert candidates['acme123!'].transformations == (
        Transformation('organization_domain_label',(('input','ACME.com.br'),('rule','first_dns_label'))),
        Transformation('case',(('mode','original'),)),
        Transformation('affix',(('input','acme'),('token','123'),('placement','suffix'),('separator','!'),
                                ('separator_position','after'),('input_steps','2'),('token_steps','0'))))
    assert candidates['Lab123!'].origins[0] == Origin('organization','alias','Lab')
    assert 'Changed' not in candidates
    assert all('skipadmin' != c for c in candidates)


@pytest.mark.parametrize('source,expected', [('target','profile'),('organization','organization'),('ready','ready_candidate'),('knowledge','knowledge'),('dataset','dataset'),('ptbr','dataset')])
def test_encounter_precedence(tmp_path, source, expected):
    # admin is supplied by knowledge; Senha is also in PT-BR.
    value = 'Senha' if source in ('dataset','ptbr') else 'admin'
    corpus = tmp_path / 'dataset.txt'
    ready = tmp_path / 'ready.txt'
    corpus.write_text(value + '\n', encoding='utf-8')
    ready.write_text(value + '\n', encoding='utf-8')
    kwargs = {'sources': SourceOptions(dataset_paths=(str(corpus),) if source != 'ptbr' else (),
                ready_candidate_paths=(str(ready),) if source in ('target','organization','ready') else (), include_ptbr=True)}
    if source == 'target':
        kwargs['target'] = Target('', TargetProfile(nome=value))
    if source == 'organization':
        kwargs['organization'] = Organization(value)
    if source == 'knowledge':
        kwargs['organization'] = Organization('ACME')
    kwargs['intelligence'] = IntelligenceOptions(reference_year=2026, corporate_roles=source not in ('dataset','ptbr'))
    c = next(c for c in GenerationService().prepare(request(**kwargs)).iter_candidates() if c.value == value)
    assert c.origins[0].source == expected
    if source == 'ptbr':
        assert c.origins[0].field.startswith('ptbr.')
    if source == 'ready':
        assert c.transformations == ()


def test_ready_template_collision_bypass_and_explicit_number_precedence(tmp_path):
    ready = tmp_path / 'ready.txt'
    ready.write_text('ACMEadmin123!\n', encoding='utf-8')
    r = request(organization=Organization('ACME'), sources=SourceOptions(ready_candidate_paths=(str(ready),)),
                mutations=MutationOptions(leet_mode='none', combine=True, separators='!'))
    candidates = {c.value:c for c in GenerationService().prepare(r).iter_candidates()}
    assert candidates['ACMEadmin123!'].origins[0].source == 'ready_candidate'
    assert candidates['ACMEadmin123!'].transformations == ()
    assert 'ACMEadmin123!123' not in candidates
    explicit = request(target=Target('',TargetProfile(nome='Zed',data_nascimento='01/01/2026')),
                       number_candidates=(Candidate('123',(Origin('manual','number','123'),)),))
    candidates = {c.value:c for c in GenerationService().prepare(explicit).iter_candidates()}
    assert candidates['Zed123!'].origins[-1] == Origin('manual','number','123')
    assert candidates['Zed2026#'].origins[-1] == Origin('profile','data_nascimento','01/01/2026')


def test_preview_is_lazy_and_metadata_exact(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('preview must not execute or read corpora')
    monkeypatch.setattr('mimic.core.generator.Generator.generate_candidates', forbidden)
    monkeypatch.setattr('mimic.application.generation.stream_dataset', forbidden)
    p = GenerationService().prepare(request(organization=Organization('ACME')))
    summary = p.summary()
    assert (summary.intelligence_enabled,summary.common_numbers_enabled,summary.corporate_roles_enabled) == (True,True,True)
    assert summary.recent_years == (2026,2025,2024,2023)
    assert summary.reference_year == 2026 and summary.service_profiles == ('WordPress',)
    assert summary.knowledge_seed_count == 38 and summary.knowledge_number_count == 14
    assert summary.knowledge_version == 'knowledge-v1'
    with pytest.raises(InvalidGenerationRequest, match='contextual seed'):
        GenerationService().prepare(request(intelligence=IntelligenceOptions(reference_year=2026)))


def test_modern_cli_defaults_disable_and_legacy(tmp_path, monkeypatch):
    class NoStdin:
        def __iter__(self):
            raise AssertionError('organization/company/service must not read stdin')
    monkeypatch.setattr('sys.stdin',NoStdin())
    out = tmp_path / 'out.txt'
    def generate(args):
        assert main(args + ['--reference-year','2026','--leet','none','--quiet','-o',str(out)]) == 0
        return out.read_text().splitlines()
    modern = generate(['generate','-c','ACME'])
    assert 'Acme123!' in modern and 'Acmeadmin123!' in modern
    disabled = generate(['generate','-c','ACME','--no-intelligence'])
    legacy = generate(['-c','ACME'])
    assert disabled == legacy == ['ACME','acme','Acme','EMCA']
    org = generate(['generate','--organization','ACME','--service','wordpress'])
    assert 'wpACME123#' in org
    service = generate(['generate','--service','mysql'])
    assert 'mysqldba123!' in service


def test_cli_help_and_debug(tmp_path, capsys, caplog):
    with pytest.raises(SystemExit):
        main(['generate','--help'])
    help_text = capsys.readouterr().out
    for value in ('--no-intelligence','--organization','--reference-year','windows-ad','postgresql'):
        assert value in help_text
    with caplog.at_level(logging.DEBUG, logger='mimic'):
        assert main(['generate','--organization','ACME','--service','wordpress','--reference-year','2026',
                     '--leet','none','--max-per-word','60','--debug','--quiet','-o',str(tmp_path/'debug.txt')]) == 0
    record = next(r for r in caplog.records if r.getMessage().startswith('ACMEadmin123! <-'))
    assert 'organization.name=ACME + knowledge.role=admin + knowledge.common_number=123' in record.getMessage()
    assert 'knowledge_template(' in record.getMessage() and 'affix(' in record.getMessage()


def test_hash_seed_determinism():
    script = """
import json
from dataclasses import asdict
from mimic.application import *
from mimic.domain.models import Organization
r=GenerationRequest(organization=Organization('São Paulo',domains=['acme.com.br']),
 intelligence=IntelligenceOptions(reference_year=2026,service_profiles=('wordpress','mysql')),
 limits=GenerationLimits(max_candidates_per_word=40))
print(json.dumps([asdict(c) for c in GenerationService().prepare(r).iter_candidates()],ensure_ascii=False))
"""
    outputs = [subprocess.check_output([sys.executable,'-B','-c',script], env={**os.environ,'PYTHONHASHSEED':seed},stderr=subprocess.DEVNULL)
               for seed in ('1','777','42')]
    assert outputs[0] == outputs[1] == outputs[2]


def test_representative_default_cardinality():
    r = request(organization=Organization('ACME'), mutations=MutationOptions())
    p = GenerationService().prepare(r)
    assert p.summary().knowledge_seed_count == 38
    count = sum(1 for _ in p.iter_candidates())
    assert 10_000 < count < 180_000
    capped = GenerationService().prepare(request(organization=Organization('ACME'), limits=GenerationLimits(max_candidates_per_word=50)))
    assert sum(1 for _ in capped.iter_candidates()) <= 40 * 51


def test_job_snapshot_frozen_while_worker_waits(tmp_path):
    paths, repo = store(tmp_path)
    entered, release = threading.Event(), threading.Event()
    class BlockingService(GenerationService):
        def prepare(self, r):
            entered.set()
            assert release.wait(5)
            return super().prepare(r)
    manager = JobManager(repo, paths, service=BlockingService())
    manager.start()
    try:
        r = request(organization=Organization('ACME'), limits=GenerationLimits(max_candidates_per_word=50))
        job = manager.submit(r)
        assert entered.wait(5)
        r.intelligence = replace(r.intelligence,reference_year=2030,service_profiles=('mysql',), enabled=False, common_numbers=False, recent_years=False, corporate_roles=False)
        r.organization.name = 'Changed'
        snapshot = repo.get_job(job['id'])['request']
        assert snapshot['intelligence'] == IntelligenceOptions(reference_year=2026,service_profiles=('wordpress',)).to_dict()
        assert snapshot['organization']['name'] == 'ACME' and snapshot['target'] is None
        release.set()
        assert manager.wait(job['id'],5)['status'] == 'completed'
        values = paths.output(job['id']).read_text().splitlines()
        assert 'ACME123!' in values and 'Changed' not in values
    finally:
        release.set()
        manager.stop()


def test_web_defaults_selectors_organization_only_preview_job_download(web, monkeypatch):
    client, app = web
    page = client.get('/generate').text
    for field in ('intelligence_enabled','common_numbers','recent_years','corporate_roles'):
        assert re.search(r'name="' + field + r'"[^>]*checked',page)
    for profile in SERVICE_PROFILES:
        assert f'value="{profile.id}"' in page
    created = submit(client,'/organizations/new',{'name':'ACME'}, follow_redirects=False)
    org_id = created.headers['location'].split('/')[-1]
    assert f'/generate?organization_id={org_id}' in client.get(created.headers['location']).text
    page = client.get('/generate?organization_id=' + org_id).text
    assert 'value="organization" checked' in page
    values = {'mode':'organization','organization_id':org_id,'intelligence_form':'1','intelligence_enabled':'on',
              'common_numbers':'on','recent_years':'on','corporate_roles':'on','service_profiles':'wordpress',
              'reference_year':'2026','leet_mode':'none','separators':'!#','max_candidates_per_word':'100'}
    from mimic.application.generation import PreparedGeneration
    with monkeypatch.context() as m:
        m.setattr(PreparedGeneration,'iter_candidates',lambda *_: pytest.fail('preview executed'))
        response = submit(client,'/generate',{**values,'intent':'preview'})
    assert response.status_code == 200
    for text in ('Password Intelligence: enabled','2023–2026','Services: WordPress','Knowledge seeds: 38'):
        assert text in response.text
    assert re.search(r'name="service_profiles" value="wordpress"[^>]*checked',response.text)
    assert app.state.repository.list_jobs() == []
    response = submit(client,'/generate',values,follow_redirects=False)
    assert response.status_code == 303
    job_id = response.headers['location'].split('/')[-1]
    job = app.state.job_manager.wait(job_id,5)
    assert job['status'] == 'completed' and job['target_id'] is None
    assert job['request']['target'] is None and job['request']['intelligence']['reference_year'] == 2026
    preview = app.state.repository.list_preview(job_id)
    c = next(c for c in preview if c['value'] == 'ACME123!')
    assert c['origins'] == [asdict(Origin('organization','name','ACME')), asdict(Origin('knowledge','common_number','123'))]
    assert c['transformations'][-1]['kind'] == 'affix'
    assert 'Password Intelligence' in client.get(response.headers['location']).text
    download = client.get('/api/jobs/' + job_id + '/download')
    assert download.status_code == 200 and 'ACMEadmin123!' in download.text.splitlines()
    assert client.get('/api/targets').json() == []


def test_web_disable_validation_and_multiple_services(web):
    client,app = web
    base = {'mode':'quick','empresa':'ACME','intelligence_form':'1','leet_mode':'none','intent':'preview'}
    disabled = submit(client,'/generate',base)
    assert disabled.status_code == 200 and 'Password Intelligence: off' in disabled.text
    assert 'Knowledge seeds: 0' in disabled.text
    invalid = submit(client,'/generate',{**base,'intelligence_enabled':'on','service_profiles':'unknown'})
    assert invalid.status_code == 422 and 'unknown service profile' in invalid.text
    invalid = submit(client,'/generate',{**base,'reference_year':'2026.5'})
    assert invalid.status_code == 422 and 'Reference year must be a whole number' in invalid.text
    data = {**base,'intelligence_enabled':'on','service_profiles':['wordpress','mysql']}
    multiple = submit(client,'/generate',data)
    assert multiple.status_code == 200 and 'Services: WordPress, MySQL' in multiple.text
    assert app.state.repository.list_jobs() == []


def test_import_boundaries():
    root = Path(__file__).parents[1] / 'mimic'
    forbidden = {
        'core':('mimic.intelligence','mimic.domain','mimic.application','mimic.web','mimic.api','mimic.jobs'),
        'intelligence':('mimic.cli','mimic.web','mimic.api','mimic.application','mimic.domain'),
        'domain':('mimic.application','mimic.intelligence'),
    }
    for package,prefixes in forbidden.items():
        for path in (root/package).rglob('*.py'):
            tree = ast.parse(path.read_text())
            imports = [node.module for node in ast.walk(tree) if isinstance(node,ast.ImportFrom) and node.module]
            imports += [a.name for node in ast.walk(tree) if isinstance(node,ast.Import) for a in node.names]
            assert not any(module.startswith(prefixes) for module in imports), path
    assert 'mimic.intelligence.planning' in (root/'application/generation.py').read_text()
