"""Block 14 evidence, immutable historical views, passive catalog and adapters."""
import csv
from dataclasses import asdict, replace
import html
import io
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys

from fastapi.testclient import TestClient
import pytest

from mimic.api import create_app
from mimic.application import (GenerationRequest, GenerationService, IntelligenceOptions,
    GenerationLimits, MutationOptions, RankingOptions, InvalidGenerationRequest)
from mimic.cli import main
from mimic.domain.models import Organization
from mimic.intelligence import catalog
from mimic.intelligence.builtins import SERVICE_PROFILES, SERVICE_PROFILES_V1, get_service_profile
from mimic.intelligence.planning import plan_intelligence
from mimic.ranking.scoring import score_candidate
from mimic.web.i18n import TRANSLATIONS, translate
from mimic.web.security import HTML_CSP

NEW = ('zabbix', 'sonarqube', 'jenkins', 'tomcat', 'redis', 'opensearch')


def request(service, **kwargs):
    return GenerationRequest(intelligence=IntelligenceOptions(reference_year=2026,
        corporate_roles=False, service_profiles=(service,)),
        mutations=MutationOptions(leet_mode='none', separators='!'),
        limits=GenerationLimits(20), **kwargs)


def test_exact_v1_records_order_metadata_and_csv():
    original = json.loads((Path(__file__).parent / 'fixtures/service-catalog-v1.json').read_text())
    actual = {'profiles': [asdict(p) for p in SERVICE_PROFILES[:7]],
        'services': [s.to_dict() for s in catalog.list_services(version='service-catalog-v1')],
        'credentials': [c.to_dict() for c in catalog.list_credentials(version='service-catalog-v1')],
        'common': catalog.common_vocabulary().to_dict(),
        'csv': catalog.credentials_csv(version='service-catalog-v1')}
    assert json.loads(json.dumps(actual)) == original
    assert SERVICE_PROFILES[:7] == SERVICE_PROFILES_V1
    assert catalog.SERVICES[:7] == catalog.SERVICES_V1
    assert catalog.DEFAULT_CREDENTIALS[:2] == catalog.DEFAULT_CREDENTIALS_V1
    catalog.validate_catalog(catalog.SERVICES_V1, catalog.DEFAULT_CREDENTIALS_V1, profiles=SERVICE_PROFILES_V1)


def test_expanded_view_and_record_versions_are_distinct():
    assert catalog.CATALOG_VERSION == 'service-catalog-v2'
    assert len(catalog.SERVICES) == len(SERVICE_PROFILES) == 13
    assert tuple(s.id for s in catalog.SERVICES[7:]) == NEW
    assert len(catalog.DEFAULT_CREDENTIALS) == 4
    assert all(s.catalog_version == 'service-catalog-v1' for s in catalog.SERVICES[:7])
    assert all(s.catalog_version == 'service-catalog-v2' for s in catalog.SERVICES[7:])
    assert all(p.version == 'knowledge-v1' for p in SERVICE_PROFILES[:7])
    assert all(p.version == 'knowledge-v2' for p in SERVICE_PROFILES[7:])
    assert all(c.record_version == '1' for c in catalog.DEFAULT_CREDENTIALS)
    for s in catalog.SERVICES[7:]:
        assert type(s)(**json.loads(json.dumps(s.to_dict()))) == s
    for c in catalog.DEFAULT_CREDENTIALS[2:]:
        assert type(c)(**json.loads(json.dumps(c.to_dict()))) == c


@pytest.mark.parametrize('operation', ['services', 'service', 'credentials', 'csv'])
def test_unknown_collection_versions_fail_clearly(operation):
    call = {'services': lambda: catalog.list_services(version='service-catalog-v99'),
        'service': lambda: catalog.get_service('wordpress', version='service-catalog-v99'),
        'credentials': lambda: catalog.list_credentials(version='service-catalog-v99'),
        'csv': lambda: catalog.credentials_csv(version='service-catalog-v99')}[operation]
    with pytest.raises(ValueError, match='unsupported service catalog version'):
        call()


def test_v1_cannot_resolve_new_service_and_old_id_cannot_be_retagged():
    with pytest.raises(ValueError, match='unknown service'):
        catalog.get_service('zabbix', version='service-catalog-v1')
    with pytest.raises(ValueError, match='unknown service'):
        catalog.list_credentials('zabbix', version='service-catalog-v1')
    for index,version in ((0,'service-catalog-v2'),(7,'service-catalog-v1'),(7,'service-catalog-v99')):
        services=list(catalog.SERVICES);services[index]=replace(services[index],catalog_version=version)
        with pytest.raises(ValueError, match='version'):
            catalog.validate_catalog(services=services)
    with pytest.raises(ValueError, match='common password collection version'):
        catalog.common_vocabulary('common-v2')


@pytest.mark.parametrize('service,user,password,scope', [
    ('zabbix','Admin','zabbix','7.4'), ('sonarqube','admin','admin','2025.1')])
def test_new_documented_pairs_have_explicit_official_associations(service,user,password,scope):
    credential, = catalog.list_credentials(service)
    knowledge = catalog.get_service(service)
    assert (credential.username,credential.password) == (user,password)
    assert scope in credential.version_scope and scope in credential.source_url
    assert (credential.source_title,credential.source_url) in knowledge.references
    assert credential.applicability.startswith('Initial ')
    assert 'first login' in ' '.join(credential.restrictions).lower() or 'First setup' in ' '.join(credential.restrictions)
    assert 'other releases' in ' '.join(credential.restrictions)
    assert scope in knowledge.authentication_notes
    assert 'change' in knowledge.authentication_notes.lower()
    row, = csv.DictReader(io.StringIO(catalog.credentials_csv(service)))
    assert row['username'] == user and row['password'] == password
    assert row['source_url'] == credential.source_url
    for condition in (credential.applicability,*credential.restrictions,credential.version_scope):
        assert condition in row['applicability']


@pytest.mark.parametrize('service,terms', [
    ('jenkins',('automatically generated','installation-specific','first administrator','no release range')),
    ('tomcat',('11.0.27','no manager-gui user','commented','explicitly configured','every installed')),
    ('redis',('Redis 6+','default','nopass','without AUTH','requirepass','Protected mode','Redis Cloud','RBAC')),
    ('opensearch',('2.12','new cluster','custom admin password','Existing configured clusters','Historical demo','managed')),
])
def test_no_fixed_pair_services_still_have_authentication_evidence(service,terms):
    assert catalog.list_credentials(service) == ()
    knowledge=catalog.get_service(service)
    assert knowledge.references
    for term in terms:
        assert term in knowledge.authentication_notes


@pytest.mark.parametrize('service',NEW)
def test_search_discovers_id_name_alias_and_profile_tokens(service):
    knowledge=catalog.get_service(service);profile=get_service_profile(service)
    for query in (service,knowledge.display_name,*knowledge.aliases,*profile.tokens):
        assert knowledge in catalog.list_services(' '+query.upper()+' ')
    assert profile.tokens and profile.roles
    assert len(profile.tokens) <= 2 and len(profile.roles) == 1
    assert all(token.casefold() in (service,'sonar') for token in profile.tokens)


@pytest.mark.parametrize('query,expected',[('CI/CD','jenkins'),('DevSecOps','sonarqube'),('cache','redis'),('Java','tomcat')])
def test_description_search_supplies_categories_without_new_schema(query,expected):
    assert [s.id for s in catalog.list_services(query)] == [expected]


@pytest.mark.parametrize('kind',['missing-profile','missing-knowledge','duplicate-profile','alias-cross','alias-case','profile-version','profile-token'])
def test_structural_catalog_defects_are_rejected(kind):
    services=list(catalog.SERVICES);profiles=list(SERVICE_PROFILES)
    if kind=='missing-profile':profiles.pop()
    elif kind=='missing-knowledge':services.pop()
    elif kind=='duplicate-profile':profiles.append(profiles[0])
    elif kind=='alias-cross':services[-1]=replace(services[-1],aliases=(' WP ',))
    elif kind=='alias-case':services[-1]=replace(services[-1],aliases=('Open Search','open search'))
    elif kind=='profile-version':profiles[-1]=replace(profiles[-1],version='knowledge-v99')
    elif kind=='profile-token':profiles[-1]=replace(profiles[-1],tokens=('bad\nvalue',))
    with pytest.raises(ValueError):
        catalog.validate_catalog(services=services,profiles=profiles)


@pytest.mark.parametrize('change', [dict(record_version='2'),dict(version_scope=None),
    dict(catalog_version='service-catalog-v1'),dict(source_url='https://example.test/unrelated'),
    dict(service_id='nonexistent')],ids=['revision','scope','catalog','evidence','dangling'])
def test_invalid_expanded_credentials_fail_validation(change):
    with pytest.raises(ValueError):
        catalog.validate_catalog(credentials=(replace(catalog.DEFAULT_CREDENTIALS[2],**change),))


def test_same_pair_with_changed_prose_is_still_duplicate():
    first=catalog.DEFAULT_CREDENTIALS[2]
    second=replace(first,id='duplicate-example',applicability='Different wording is not different evidence.')
    with pytest.raises(ValueError,match='duplicate documented'):
        catalog.validate_catalog(credentials=(first,second))


@pytest.mark.parametrize('character',['\x00','\x85','\n','\r','\u2028','\u2029','\u202e','\u2066','\u200b','\ud800'],
    ids=['nul','c1','lf','cr','ls','ps','bidi','isolate','zero-width','surrogate'])
def test_unsafe_unicode_is_rejected_in_every_metadata_channel(character):
    for obj,field in ((catalog.SERVICES[7],'authentication_notes'),(catalog.SERVICES[7],'description'),
        (catalog.DEFAULT_CREDENTIALS[2],'password'),(catalog.DEFAULT_CREDENTIALS[2],'version_scope'),
        (catalog.DEFAULT_CREDENTIALS[2],'source_url')):
        with pytest.raises(ValueError):
            replace(obj,**{field:'value'+character})


@pytest.mark.parametrize('service',NEW)
def test_cli_new_services_and_safe_csv_publication(service,tmp_path,capsys):
    assert main(['services','show',service]) == 0
    text=capsys.readouterr().out
    assert catalog.get_service(service).authentication_notes in text
    assert 'knowledge-v2' in text
    assert main(['services','list','--search',catalog.get_service(service).display_name]) == 0
    assert service in capsys.readouterr().out
    assert main(['credentials','list','--service',service]) == 0
    text=capsys.readouterr().out
    assert ('No documented' in text) == (not catalog.list_credentials(service))
    output=tmp_path/'catalog.csv'
    assert main(['credentials','export','--service',service,'--output',str(output)]) == 0
    assert output.read_text() == catalog.credentials_csv(service)
    assert main(['credentials','export','--service',service,'--output',str(output)]) == 2
    assert output.read_text() == catalog.credentials_csv(service)


@pytest.mark.parametrize('service',NEW)
@pytest.mark.parametrize('locale',['pt-BR','en'])
def test_web_complete_localized_evidence_and_opt_in_navigation(service,locale,tmp_path,caplog):
    with TestClient(create_app(data_dir=tmp_path)) as client:
        client.cookies.set('mimic_locale',locale)
        response=client.get('/services/'+service)
        assert response.status_code == 200
        assert response.headers['Content-Security-Policy'] == HTML_CSP
        assert response.headers['Content-Language'] == locale
        assert 'service-catalog-v2' in response.text and 'knowledge-v2' in response.text
        for suffix in ('description','auth'):
            key='catalog.service.'+service+'.'+suffix
            assert key in TRANSLATIONS[locale]
            assert html.escape(translate(locale,key),quote=False) in response.text
        for _,url in catalog.get_service(service).references:
            assert html.escape(url) in response.text
        for credential in catalog.list_credentials(service):
            assert translate(locale,'catalog.credential.'+credential.id+'.version_scope') in response.text
        if not catalog.list_credentials(service):
            assert translate(locale,'catalog.no_defaults') in response.text
        assert translate(locale,'catalog.documented_help') in response.text
        assert translate(locale,'catalog.common_help') in response.text
        assert 'href="/generate?service='+service+'"' in response.text
        page=client.get('/generate?service='+service).text
        selected=re.findall(r'name="service_profiles" value="([^"]+)"\s+checked',page)
        assert selected == [service]
        assert client.app.state.repository.list_jobs() == []
        assert not re.search(r'name="include_common_passwords"[^>]*checked',page)
    assert 'Missing Web translation' not in caplog.text


@pytest.mark.parametrize('service',NEW)
def test_new_profiles_use_existing_templates_scores_and_families_only(service):
    req=request(service,organization=Organization('Synthetic'),ranking=RankingOptions(True,30,selector='diverse-v1'))
    assert GenerationRequest.from_dict(json.loads(json.dumps(req.to_dict()))).to_dict() == req.to_dict()
    prepared=GenerationService().prepare(req);results=list(prepared.iter_results())
    assert results and len({r.candidate.value for r in results}) == len(results) == 30
    assert prepared.evaluated_count >= len(results)
    assert all(r.score == score_candidate(r.candidate,2026) for r in results)
    fields={o.field for r in results for o in r.candidate.origins if o.field.startswith('service.')}
    assert fields and all(f.startswith('service.'+service+'.') for f in fields)
    assert all(r.selection.family_version == 'candidate-family-v1' for r in results)
    profile=get_service_profile(service)
    plan=plan_intelligence(req.intelligence)
    assert len(plan.seeds) == len(profile.tokens)+len(profile.roles)+2*len(profile.tokens)*len(profile.roles)
    assert prepared.summary().knowledge_version == 'knowledge-v1'


@pytest.mark.parametrize('service',NEW)
def test_catalog_is_passive_even_when_selected(service,monkeypatch):
    reference = [r.to_dict() for r in GenerationService().prepare(request(service)).iter_results()]
    def forbidden(*args,**kwargs):raise AssertionError('documented pairs or network consulted')
    monkeypatch.setattr(catalog,'list_credentials',forbidden)
    monkeypatch.setattr(catalog,'DEFAULT_CREDENTIALS', (replace(catalog.DEFAULT_CREDENTIALS[0],
        password='CatalogOnlyCanaryV14'),))
    monkeypatch.setattr(catalog,'DEFAULT_CREDENTIALS_V1', ())
    monkeypatch.setattr(socket,'create_connection',forbidden)
    monkeypatch.setattr(socket,'getaddrinfo',forbidden)
    prepared=GenerationService().prepare(request(service))
    results=list(prepared.iter_results())
    assert [r.to_dict() for r in results] == reference
    assert all(o.field != 'documented_default' for r in results for o in r.candidate.origins)
    assert all(not o.field.startswith('service.') or o.field.startswith('service.'+service+'.')
        for r in results for o in r.candidate.origins)
    assert [s.id for s in catalog.list_services(service)] == [service]


@pytest.mark.parametrize('service',NEW)
def test_api_job_roundtrip_and_restart_with_new_explicit_service(service,tmp_path):
    req=request(service,ranking=RankingOptions(True,10))
    expected=''.join(GenerationService().prepare(req).iter_values()).encode()
    with TestClient(create_app(data_dir=tmp_path)) as client:
        response=client.post('/api/jobs',json={'request':req.to_dict()})
        assert response.status_code == 201
        identity=response.json()['id']
        job=client.app.state.job_manager.wait(identity,10)
        assert job['status'] == 'completed'
        assert job['request'] == json.loads(json.dumps(req.to_dict()))
        body=client.get('/api/jobs/'+identity+'/download').content
        assert body.replace(b'\n',b'') == expected
        rows=client.get('/api/jobs/'+identity+'/candidates').json()
        assert len(rows) == 10
    with TestClient(create_app(data_dir=tmp_path)) as client:
        assert client.get('/api/jobs/'+identity+'/download').content == body
        assert client.get('/api/jobs/'+identity+'/candidates').json() == rows


def test_unknown_service_request_still_fails_before_generation():
    req=request('future-service')
    with pytest.raises(InvalidGenerationRequest,match='unknown service profile'):
        GenerationService().prepare(req)


def test_all_new_profiles_and_catalog_are_hashseed_deterministic():
    script='''
import json
from mimic.application import *
from mimic.domain.models import Organization
from mimic.intelligence.catalog import credentials_csv
out=[]
for service in ('zabbix','sonarqube','jenkins','tomcat','redis','opensearch'):
 r=GenerationRequest.from_dict({'preset':'corporate-br','organization':{'name':'Synthetic'},
 'intelligence':{'reference_year':2026,'service_profiles':[service]},
 'mutations':{'leet_mode':'none','separators':'!'},'limits':{'max_candidates_per_word':10},
 'ranking':{'enabled':True,'budget':20,'selector':'diverse-v1'}})
 p=GenerationService().prepare(r)
 out.append({'request':r.to_dict(),'summary':p.summary().to_dict(),'warnings':p.warnings,
 'results':[r.to_dict() for r in p.iter_results()],'evaluated':p.evaluated_count})
print(json.dumps({'cases':out,'csv':credentials_csv()},sort_keys=True))
'''
    outputs=[subprocess.check_output([sys.executable,'-B','-c',script],env={**os.environ,
        'PYTHONHASHSEED':seed,'PYTHONDONTWRITEBYTECODE':'1'}) for seed in ('1','42','777')]
    assert outputs[0] == outputs[1] == outputs[2]
