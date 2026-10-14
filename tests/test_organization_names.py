"""Block 12.5 lexical seeds, full engine coverage and frozen adapter contracts."""
from dataclasses import asdict, replace
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from mimic.api import create_app
from mimic.application import (GenerationRequest, GenerationService, IntelligenceOptions,
    MutationOptions, GenerationLimits, PolicyOptions, RankingOptions, SourceOptions,
    InvalidGenerationRequest)
from mimic.cli import main
from mimic.core.candidate import Candidate, Origin
from mimic.core.generator import Generator
from mimic.domain.context import ExtractedFact
from mimic.domain.models import Organization, Target
from mimic.intelligence.organization import plan_organization_names, MAX_NAMES, MAX_VARIANTS_PER_NAME
from mimic.jobs import JobManager
from mimic.persistence import DataPaths, Database, Repository
from mimic.profile.schema import TargetProfile
from mimic.web.i18n import TRANSLATIONS, translate
from mimic.web.security import HTML_CSP

NAME = 'acme hamburgueria'
REQUIRED = ('Acme2026@', 'acme2026@', 'acmehamburgueria2026@',
    'Acmehamburgueria2026@', 'acmeHamburgueria2026@', 'AcmeHamburgueria2026@',
    'Acme123@', 'acmehamburgueria123!', 'Acmehamburgueria2025@')


def request(**changes):
    return replace(GenerationRequest(organization=Organization(NAME), organization_variants=True,
        intelligence=IntelligenceOptions(reference_year=2026),
        mutations=MutationOptions(leet_mode='partial', separators='@!#$')), **changes)


def collect(config):
    prepared = GenerationService().prepare(config)
    results = list(prepared.iter_results())
    return prepared, results


def lexical(value):
    candidate = Candidate(value, (Origin('organization', 'name', value),))
    return plan_organization_names((candidate,))


@pytest.mark.parametrize('value,expected', [
    ('acme', set()),
    (NAME, {'acme', 'Acme', 'hamburgueria', 'Hamburgueria', 'acmehamburgueria',
        'Acmehamburgueria', 'acmeHamburgueria', 'AcmeHamburgueria', 'ACMEHamburgueria', 'AH', 'ah'}),
    ('  acme   hamburgueria  ', {'acmehamburgueria', 'AcmeHamburgueria', 'AH'}),
    ('acme-hamburgueria', {'acmehamburgueria', 'acmeHamburgueria', 'AH'}),
    ('acme_hamburgueria', {'acmehamburgueria', 'AH'}),
    ('acme/hamburgueria', {'acmehamburgueria', 'AH'}),
    ('casa de pão', {'casa', 'de', 'pão', 'casadepão', 'CasaDePão', 'CDP', 'casaDepão'}),
    ('casa de pão azul', {'CasaDePãoAzul', 'casadepãoAzul', 'CDPA'}),
    ('ACME hamburgueria', {'ACMEhamburgueria', 'ACMEHamburgueria', 'acmehamburgueria'}),
    ('AcmeTech', set()),
    ('São João', {'SãoJoão', 'sãoJoão', 'SJ'}),
    ('İris 東京', {'İris東京', 'İ東', 'i\u0307ris東京'}),
    ('A\u0301gua doce', {'A\u0301guaDoce', 'a\u0301guadoce', 'AD'}),
], ids=['single','two','spaces','hyphen','underscore','slash','three','four','uppercase','camel','accents','unicode','decomposed'])
def test_lexical_structures_preserve_explicit_components(value, expected):
    plan = lexical(value)
    by_value = {c.value: c for c in plan.candidates}
    assert expected <= by_value.keys()
    assert len(by_value) <= MAX_VARIANTS_PER_NAME
    for candidate in by_value.values():
        assert candidate.origins == (Origin('organization', 'name', value),)
        assert len(candidate.value) <= 256
        assert len(candidate.transformations) == 1
        params = dict(candidate.transformations[0].params)
        assert params['input'] == value and params['version'] == 'organization-name-v1'
        assert ''.join(json.loads(params['components']))
    if value == 'AcmeTech':
        assert not any(c in by_value for c in ('Acme', 'Tech', 'AT'))


@pytest.mark.parametrize('value', ['acme, hamburgueria', 'ACME S.A.', "D'Água Serviços", '<acme> loja', '🍞 casa', 'x' * 257],
    ids=['comma','dots','apostrophe','markup','emoji','oversize'])
def test_ambiguous_punctuation_and_oversize_keep_original_only(value):
    assert lexical(value).candidates == ()
    _, results = collect(request(organization=Organization(value), intelligence=IntelligenceOptions(enabled=False),
                                 mutations=MutationOptions('none', separators='')))
    assert value in {r.candidate.value for r in results}


@pytest.mark.parametrize('value', ['acme', 'ACME', 'AcmeTech'])
def test_single_lexical_names_retain_full_historical_case_and_reverse_behavior(value):
    config = request(organization=Organization(value), intelligence=IntelligenceOptions(enabled=False),
                     mutations=MutationOptions('none', separators=''))
    _, on = collect(config)
    _, off = collect(replace(config, organization_variants=False))
    assert on == off
    assert value in {r.candidate.value for r in on}


def test_many_components_and_aliases_are_bounded_without_stopword_or_pair_products():
    eight = lexical('AbcDef GhIj KlMn OpQr StUv WxYz MarcaTech OutraMarca')
    assert 'AbcDefGhIjKlMnOpQrStUvWxYzMarcaTechOutraMarca' in {c.value for c in eight.candidates}
    assert 'AGKOSWMO' in {c.value for c in eight.candidates}
    assert len(eight.candidates) <= MAX_VARIANTS_PER_NAME
    long_name = ' '.join('p' + str(i) for i in range(30))
    plan = lexical(long_name)
    assert len(plan.candidates) == 2 and plan.limited_names == 1
    assert {dict(c.transformations[0].params)['rule'] for c in plan.candidates} == {'concatenate'}
    terms = tuple(Candidate('marca ' + str(i)) for i in range(100))
    plan = plan_organization_names(terms)
    assert len(plan.candidates) <= MAX_NAMES * MAX_VARIANTS_PER_NAME
    assert plan.limited_names == 92
    assert plan == plan_organization_names(terms + terms)
    prepared = GenerationService().prepare(request(organization=Organization('x', aliases=[t.value for t in terms])))
    summary = prepared.summary().to_dict()
    assert summary['organization_variant_limited_names'] == 93
    assert 'organization name expansion limited; original seeds preserved' in prepared.warnings
    assert prepared.request.limits.max_candidates_per_word == 5000


@pytest.mark.parametrize('leet', ['none', 'partial'])
@pytest.mark.parametrize('cap', [256, 5000])
def test_full_exhaustive_pipeline_covers_all_required_examples_under_caps(leet, cap):
    prepared, results = collect(request(mutations=MutationOptions(leet, separators='@!#$'), limits=GenerationLimits(cap)))
    by_value = {r.candidate.value: r.candidate for r in results}
    assert set(REQUIRED) <= by_value.keys()
    assert {'ACMEHamburgueria', 'AH', 'ah'} <= by_value.keys()
    if cap == 5000:
        assert 'ACME' in by_value
    assert prepared.evaluated_count == len(results)
    for value in REQUIRED:
        candidate = by_value[value]
        assert candidate.origins[0].value == NAME
        assert not any(t.kind == 'leet' for t in candidate.transformations)
        assert candidate.transformations[-1].kind == 'affix'
    joined = by_value['acmeHamburgueria2026@']
    name_step = next(t for t in joined.transformations if t.kind == 'organization_name')
    assert dict(name_step.params)['case'] == 'single_initial_title'
    assert dict(name_step.params)['component'] == '1'
    assert dict(joined.transformations[-1].params)['input'] == 'acmeHamburgueria'
    assert joined.origins[-1] == Origin('knowledge', 'recent_year', '2026')


@pytest.mark.parametrize('leet', ['none', 'partial'])
@pytest.mark.parametrize('cap', [256, 5000])
@pytest.mark.parametrize('budget', ['quick', 'focused'])
def test_ranked_output_reports_retention_separately_from_full_generation(leet, cap, budget):
    config = request(mutations=MutationOptions(leet, separators='@!#$'), limits=GenerationLimits(cap))
    full, results = collect(config)
    ranked, retained = collect(replace(config, ranking=RankingOptions.from_budget(budget)))
    assert ranked.evaluated_count == full.evaluated_count
    assert len(retained) == (100 if budget == 'quick' else 1000)
    generated = {r.candidate.value: r.candidate for r in results}
    assert set(REQUIRED) <= generated.keys()
    assert all(r.candidate == generated[r.candidate.value] for r in retained)
    assert all(r.score.version == 'score-v1' for r in retained)
    # Existing templates have higher scores: new generation is no Top-K guarantee.
    assert set(REQUIRED) - {r.candidate.value for r in retained}


@pytest.mark.parametrize('leet', ['none', 'partial', 'full'])
def test_tiny_cap_and_full_leet_limitations_are_actual_pipeline_behavior(leet, caplog):
    _, results = collect(request(limits=GenerationLimits(50), mutations=MutationOptions(leet, separators='@!#$')))
    values = {r.candidate.value for r in results}
    assert 'Acme2026@' not in values and 'acmeHamburgueria2026@' not in values
    assert any('stage=AffixMutator' in record.message for record in caplog.records)
    if leet == 'full':
        assert 'Acme123@' not in values
    else:
        assert 'Acme123@' in values


@pytest.mark.parametrize('source', ['name', 'alias', 'profile', 'context', 'inherited'])
def test_explicit_company_sources_share_engine_and_keep_true_origin(source):
    config = request(intelligence=IntelligenceOptions(reference_year=2026, corporate_roles=False))
    if source == 'alias':
        config.organization = Organization('Other', aliases=[NAME, NAME], id='synthetic-org')
    elif source == 'profile':
        config.organization = None
        config.target = Target('', TargetProfile(empresa=NAME))
    elif source == 'context':
        config.organization = None
        config.context_facts = (ExtractedFact('empresa', Candidate(NAME, (Origin('context_file','web.pasted:1:empresa',NAME),))),)
    elif source == 'inherited':
        config.organization = None
        config.target = Target('', organization=Organization(NAME))
    _, results = collect(config)
    by_value = {r.candidate.value:r.candidate for r in results}
    assert set(REQUIRED) <= by_value.keys()
    origin = by_value['acmeHamburgueria2026@'].origins[0]
    assert origin.source == ('profile' if source == 'profile' else 'context_file' if source == 'context' else 'organization')
    assert origin.field == ('alias' if source == 'alias' else 'empresa' if source == 'profile' else 'web.pasted:1:empresa' if source == 'context' else 'name')
    if source == 'alias':
        params = dict(next(t for t in by_value['acmeHamburgueria2026@'].transformations if t.kind == 'organization_name').params)
        assert params['organization'] == 'Other' and params['organization_id'] == 'synthetic-org'


def test_keywords_domains_and_domain_labels_are_not_interpreted_as_names():
    prepared = GenerationService().prepare(request(organization=Organization('', keywords=[NAME], domains=['acme-hamburgueria.test']),
        intelligence=IntelligenceOptions(reference_year=2026, corporate_roles=False)))
    assert prepared.summary().organization_variant_seed_count == 0
    values = set(prepared.iter_values())
    assert 'acme-hamburgueria2026@' in values
    assert 'acmehamburgueria2026@' not in values


def test_alias_dedup_and_first_causal_derivation_preserve_original_sources():
    _, original = collect(request())
    _, duplicates = collect(request(organization=Organization(NAME, aliases=[NAME, NAME])))
    assert original == duplicates
    config = request(base_candidates=(Candidate('acme', (Origin('manual','nome','acme'),)),),
                     mutations=MutationOptions('none', separators='@!#$'))
    _, results = collect(config)
    candidate = next(r.candidate for r in results if r.candidate.value == 'acme123@')
    assert candidate.origins[0] == Origin('manual','nome','acme')
    assert not any(t.kind == 'organization_name' for t in candidate.transformations)


def test_missing_organization_no_derived_seeds_and_policy_remains_shared():
    config = request(organization=None, base_candidates=(Candidate('Other'),))
    on, a = collect(config)
    off, b = collect(replace(config, organization_variants=False))
    assert a == b and on.summary().organization_variant_seed_count == 0
    _, filtered = collect(request(policy=PolicyOptions(min_len=12, require_digit=True, require_special=True)))
    assert filtered and all(len(r.candidate.value)>=12 and any(c.isdigit() for c in r.candidate.value)
                            and any(not c.isalnum() for c in r.candidate.value) for r in filtered)


def test_ready_values_preserve_deferred_numeric_precedence(tmp_path):
    ready = tmp_path / 'ready.txt'
    ready.write_text('acmeHamburgueria2026@\n')
    config = request(sources=SourceOptions(ready_candidate_paths=(str(ready),)), limits=GenerationLimits(256))
    _, results = collect(config)
    by_value = {r.candidate.value: r.candidate for r in results}
    assert set(REQUIRED) <= by_value.keys()
    supplied = by_value['acmeHamburgueria2026@']
    assert supplied.origins[0].source == 'ready_candidate'
    assert supplied.transformations == ()


def test_prepared_plan_freezes_mutable_organization():
    config = request(organization=Organization(NAME, aliases=['Acme Foods'], id='synthetic-id'))
    expected = GenerationService().prepare(GenerationRequest.from_dict(config.to_dict()))
    prepared = GenerationService().prepare(config)
    config.organization.name = 'Changed'
    config.organization.aliases.append('Changed Alias')
    assert list(prepared.iter_results()) == list(expected.iter_results())


@pytest.mark.parametrize('invalid', [None, 0, 1, 'true', [], {}], ids=['null','zero','one','string','array','object'])
def test_request_rejects_non_boolean_switch(invalid):
    with pytest.raises(InvalidGenerationRequest):
        GenerationService().prepare(request(organization_variants=invalid))
    with pytest.raises(InvalidGenerationRequest):
        GenerationRequest.from_dict({**request().to_dict(), 'organization_variants':invalid})
    with pytest.raises(InvalidGenerationRequest):
        request(organization_variants=invalid).to_dict()


def test_old_and_explicitly_disabled_request_json_and_summary_stay_historical():
    old = request(organization_variants=False).to_dict()
    assert 'organization_variants' not in old
    restored = GenerationRequest.from_dict(old)
    assert restored.organization_variants is False and restored.to_dict() == old
    explicit = GenerationRequest.from_dict({**old,'organization_variants':False})
    assert explicit.to_dict() == old
    a, ar = collect(restored)
    b, br = collect(explicit)
    assert ar == br and a.summary().to_dict() == b.summary().to_dict()
    assert 'organization_variant_seed_count' not in a.summary().to_dict()
    assert 'acmeHamburgueria2026@' not in {r.candidate.value for r in ar}
    enabled = GenerationRequest.from_dict(request().to_dict())
    assert enabled.organization_variants is True
    assert enabled.to_dict()['organization_variants'] is True


@pytest.mark.parametrize('modern,flag,enabled', [(True,[],True),(True,['--no-organization-variants'],False),
    (False,[],False),(False,['--organization-variants'],True)], ids=['modern-default','modern-off','legacy-default','legacy-on'])
def test_cli_defaults_optout_and_legacy_contract(tmp_path, modern, flag, enabled):
    path = tmp_path/'out.txt'
    args = ['generate'] if modern else []
    assert main([*args,'--organization',NAME,'--intelligence','--reference-year','2026',
        '--separators','@!#$','--leet','partial',*flag,'--quiet','--no-banner','-o',str(path)]) == 0
    values = set(path.read_text().splitlines())
    assert (set(REQUIRED) <= values) is enabled
    if not enabled:
        assert 'acmeHamburgueria2026@' not in values


def test_modern_company_and_context_cli_defaults(tmp_path):
    context = tmp_path/'context.txt'; context.write_text('empresa: '+NAME)
    for flags in (['--company',NAME], ['--context',str(context)]):
        path=tmp_path/'out.txt'
        assert main(['generate',*flags,'--reference-year','2026','--separators','@!#$',
                     '--quiet','--no-banner','-o',str(path)]) == 0
        assert set(REQUIRED) <= set(path.read_text().splitlines())


@pytest.mark.parametrize('enabled', [False, True])
def test_jobs_frozen_snapshots_roundtrip_replay_and_restart(tmp_path, enabled):
    paths = DataPaths(tmp_path); database = Database(paths); database.initialize()
    repository = Repository(database); manager = JobManager(repository, paths)
    config = request(organization_variants=enabled, limits=GenerationLimits(256))
    expected = [r.candidate.value for r in collect(config)[1]]
    manager.start()
    try:
        job = manager.submit(config)
        config.organization_variants = not enabled
        assert manager.wait(job['id'],20)['status'] == 'completed'
        snapshot = repository.get_job(job['id'])['request']
        assert snapshot.get('organization_variants',False) is enabled
        assert manager.completed_output(job['id']).read_text().splitlines() == expected
    finally:
        manager.stop()
    restarted=JobManager(repository,paths); restarted.start()
    try:
        assert restarted.completed_output(job['id']).read_text().splitlines() == expected
        restored = GenerationRequest.from_dict(snapshot)
        replay = restarted.submit(restored)
        assert restarted.wait(replay['id'],20)['status'] == 'completed'
        assert restarted.completed_output(replay['id']).read_bytes() == restarted.completed_output(job['id']).read_bytes()
    finally:
        restarted.stop()


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as client:
        yield client


def csrf(client):
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get('/generate').text)[1]


@pytest.mark.parametrize('enabled', [False,True])
def test_api_uses_same_explicit_request_contract_and_saved_snapshot(client, enabled):
    config = request(organization_variants=enabled, limits=GenerationLimits(256))
    response=client.post('/api/jobs',json={'request':config.to_dict()})
    assert response.status_code == 201
    job_id=response.json()['id']
    assert client.app.state.job_manager.wait(job_id,20)['status'] == 'completed'
    values=client.get('/api/jobs/'+job_id+'/download').text.splitlines()
    assert values == [r.candidate.value for r in collect(config)[1]]
    assert client.get('/api/jobs/'+job_id).json()['request'].get('organization_variants',False) is enabled
    assert (set(REQUIRED) <= set(values)) is enabled


@pytest.mark.parametrize('locale',['pt-BR','en'])
@pytest.mark.parametrize('marker,checked,enabled', [(True,True,True),(True,False,False),(False,True,False)],
    ids=['new-on','new-off','old-post'])
def test_web_default_marker_preview_error_job_and_localization(client, monkeypatch, locale, marker, checked, enabled):
    client.cookies.set('mimic_locale',locale)
    initial=client.get('/generate')
    assert re.search(r'name="organization_variants"[^>]*checked',initial.text)
    assert 'name="organization_variants_form" value="1"' in initial.text
    assert initial.headers['Content-Security-Policy'] == HTML_CSP
    assert translate(locale,'organization_variants.help') in initial.text
    data={'csrf_token':csrf(client),'mode':'quick','empresa':NAME,'reference_year':'2026',
          'separators':'@!#$','leet_mode':'partial','max_candidates_per_word':'256','intent':'preview'}
    if marker: data['organization_variants_form']='1'
    if checked: data['organization_variants']='on'
    def forbidden(*args,**kwargs):
        raise AssertionError('Preview generated the wordlist')
    with monkeypatch.context() as m:
        m.setattr(Generator,'generate_candidates',forbidden)
        page=client.post('/generate',data=data)
    assert page.status_code == 200 and client.app.state.repository.list_jobs() == []
    assert bool(re.search(r'name="organization_variants"[^>]*checked',page.text)) is enabled
    assert (translate(locale,'organization_variants.count',count=11) in page.text) is enabled
    invalid=client.post('/generate',data={**data,'reference_year':'bad'})
    assert invalid.status_code == 422
    assert bool(re.search(r'name="organization_variants"[^>]*checked',invalid.text)) is enabled
    data['intent']='generate'
    response=client.post('/generate',data=data,follow_redirects=False)
    assert response.status_code == 303
    job_id=response.headers['location'].split('/')[-1]
    assert client.app.state.job_manager.wait(job_id,20)['status'] == 'completed'
    values=set(client.get('/api/jobs/'+job_id+'/download').text.splitlines())
    assert (set(REQUIRED)<=values) is enabled
    assert client.app.state.repository.get_job(job_id)['request'].get('organization_variants',False) is enabled
    assert client.post('/generate',data={**data,'csrf_token':'bad'}).status_code == 403


def test_web_organization_selection_inherits_control_and_api_rejects_invalid_flag(client):
    org=client.post('/api/organizations',json={'name':NAME}).json()
    page=client.get('/generate',params={'organization_id':org['id']})
    assert re.search(r'name="organization_variants"[^>]*checked',page.text)
    data={'csrf_token':csrf(client),'mode':'organization','organization_id':org['id'],
          'organization_variants_form':'1','organization_variants':'on','intent':'preview','reference_year':'2026'}
    assert client.post('/generate',data=data).status_code == 200
    assert client.post('/api/jobs',json={'request':{**request().to_dict(),'organization_variants':1}}).status_code == 422


def test_complete_output_and_metadata_are_hashseed_independent(tmp_path):
    script='''from dataclasses import asdict
import hashlib,json,logging
from mimic.application import *
from mimic.domain.models import Organization
logging.disable(logging.CRITICAL)
evidence=[]
for mode in ['none','partial','full']:
 for budget in ['exhaustive','quick','focused']:
  r=GenerationRequest(organization=Organization('São AcmeTech',aliases=['ACME hamburgueria','São AcmeTech']),organization_variants=True,intelligence=IntelligenceOptions(reference_year=2026),mutations=MutationOptions(mode,separators='@!'),limits=GenerationLimits(256),ranking=RankingOptions.from_budget(budget))
  p=GenerationService().prepare(r);h=hashlib.sha256()
  for result in p.iter_results():h.update(json.dumps(asdict(result),sort_keys=True).encode())
  evidence.append([r.to_dict(),p.summary().to_dict(),p.warnings,p.evaluated_count,h.hexdigest()])
print(json.dumps(evidence,sort_keys=True))'''
    outputs=[]
    for seed in ('1','42','777'):
        result=subprocess.run([sys.executable,'-B','-c',script],env={**os.environ,'PYTHONHASHSEED':seed,
            'PYTHONDONTWRITEBYTECODE':'1'},capture_output=True,text=True,check=True)
        outputs.append(result.stdout)
    assert outputs[0] == outputs[1] == outputs[2]
