"""Independent Gate 12.5 adversarial fixtures and contract regressions."""
from dataclasses import replace
import json

import pytest

from mimic.application import GenerationRequest, GenerationService
from mimic.core.candidate import Candidate, Origin
from mimic.domain.models import Organization
from mimic.intelligence.organization import plan_organization_names


@pytest.mark.parametrize('name', ['İ' * 128 + ' a', 'İ' * 128 + ' İ', 'İ' * 127 + ' a b c d e f g h'],
                         ids=['one-overflow','multiple-overflows','fallback-and-overflow'])
def test_unicode_output_ceiling_reports_each_limited_name_once(name):
    origin = Origin('organization', 'name', name)
    plan = plan_organization_names((Candidate(name, (origin,)),))
    assert plan.candidates
    assert max(len(candidate.value) for candidate in plan.candidates) <= 256
    assert plan.limited_names == 1
    prepared = GenerationService().prepare(GenerationRequest(
        organization=Organization(name), organization_variants=True))
    assert prepared.summary().organization_variant_limited_names == 1
    assert 'organization name expansion limited; original seeds preserved' in prepared.warnings
    assert all(candidate.origins == (origin,) for candidate in plan.candidates)

from collections import Counter
from dataclasses import asdict
import io
import re
import threading
from pathlib import Path

from fastapi.testclient import TestClient
from mimic.api import create_app
from mimic.application import (GenerationLimits, IntelligenceOptions, MutationOptions,
    PolicyOptions, SourceOptions, RankingOptions, InvalidGenerationRequest)
from mimic.domain.context import ExtractedFact
from mimic.domain.models import Target
from mimic.profile.schema import TargetProfile
from mimic.packs import PackRegistry
from mimic.core.generator import Generator
from mimic.jobs import JobManager
from mimic.persistence import DataPaths, Database, Repository
from mimic.ranking.scoring import score_candidate
from mimic.web.i18n import TRANSLATIONS, translate
from string import Formatter

NAME = 'acme hamburgueria'
NINE = ('Acme2026@','acme2026@','acmehamburgueria2026@','Acmehamburgueria2026@',
        'acmeHamburgueria2026@','AcmeHamburgueria2026@','Acme123@',
        'acmehamburgueria123!','Acmehamburgueria2025@')


def configured(**changes):
    return replace(GenerationRequest(organization=Organization(NAME), organization_variants=True,
        intelligence=IntelligenceOptions(reference_year=2026),
        mutations=MutationOptions('none',separators='@!#$'), limits=GenerationLimits(256)), **changes)


@pytest.mark.parametrize('separator', [' ', '   ', '\t', '\n', '\r', '\v', '\f', '\u00a0', '\u2003', '\u202f', '\x1c', '-', '_', '/', '\u2013', '\u2014'],
    ids=['space','spaces','tab','newline','return','vertical-tab','form-feed','nbsp','em-space','narrow-nbsp','python-fs-whitespace','hyphen','underscore','slash','en-dash','em-dash'])
def test_scanner_exact_documented_whitespace_and_delimiters(separator):
    name='acme'+separator+'hamburgueria'
    source=Candidate(name,(Origin('organization','name',name),))
    plan=plan_organization_names((source,))
    assert {c.value for c in plan.candidates} == {'acme','Acme','hamburgueria','Hamburgueria',
        'acmehamburgueria','Acmehamburgueria','acmeHamburgueria','AcmeHamburgueria','ACMEHamburgueria','AH','ah'}
    assert all(json.loads(dict(c.transformations[-1].params)['components']) == ['acme','hamburgueria'] for c in plan.candidates)
    assert all(c.origins==source.origins for c in plan.candidates)


@pytest.mark.parametrize('marker', ['\x00','\x01','\x7f','\u200b','\u200d','\ufeff',',','.',"'",'🍞'],
                         ids=['nul','control','del','zero-width-space','zwj','bom','comma','dot','apostrophe','emoji'])
def test_unrecognized_marks_are_never_deleted_to_create_new_components(marker):
    assert plan_organization_names((Candidate('acme'+marker+' hamburgueria'),)).candidates == ()


@pytest.mark.parametrize('name', ['', ' \t ', 'AcmeTech', 'ACME', 'x'*100_000],
                         ids=['empty','blank','camelcase','single-uppercase','extreme-length'])
def test_no_arbitrary_segmentation_or_extreme_input_scan(name,monkeypatch):
    def forbidden(*args):raise AssertionError('oversized input classified')
    if len(name)>256:monkeypatch.setattr('mimic.intelligence.organization.unicodedata.category',forbidden)
    assert plan_organization_names((Candidate(name),)).candidates == ()


def test_component_rules_reconstruct_the_actual_value_and_first_cause():
    name='ßtraße İris 123'
    source=Candidate(name,(Origin('organization','name',name),))
    plan=plan_organization_names((source,),organization_name=name,organization_id='synthetic')
    seen=set()
    for c in plan.candidates:
        assert c.value not in seen;seen.add(c.value)
        assert c.origins==source.origins
        params=dict(c.transformations[-1].params);parts=json.loads(params['components'])
        assert parts==['ßtraße','İris','123'] and params['version']=='organization-name-v1'
        assert params['organization']==name and params['organization_id']=='synthetic'
        lower=[p.lower() for p in parts];title=[p[:1].upper()+p[1:].lower() for p in parts]
        rule,case=params['rule'],params['case']
        if rule=='component':
            index=int(params['component']);values={'original':parts,'lower':lower,'initial_title':title};expected=values[case][index]
        elif rule=='acronym':
            assert params['component']==''
            initials='ßİ1';expected=initials.upper() if case=='upper' else initials.lower()
        elif case=='single_initial_title':
            index=int(params['component']);values=lower.copy();values[index]=title[index];expected=''.join(values)
        elif case=='first_upper_rest_initial_title':expected=parts[0].upper()+''.join(title[1:])
        else:expected=''.join({'original':parts,'lower':lower,'all_initial_title':title}[case])
        assert c.value==expected
    assert 'SSİ1' in seen and 'ßi\u03071' in seen
    repeated=plan_organization_names((Candidate('a a'),))
    component=next(c for c in repeated.candidates if c.value=='a')
    assert dict(component.transformations[0].params)['component']=='0'


@pytest.mark.parametrize('count',[5,8,9],ids=['five','eight','nine-fallback'])
def test_many_component_contract_has_no_pair_products_or_masks(count):
    parts=['Abc'+str(i) for i in range(count)];name=' '.join(parts)
    plan=plan_organization_names((Candidate(name),))
    assert len(plan.candidates)<=24
    assert ''.join(parts) in {c.value for c in plan.candidates}
    rules={dict(c.transformations[0].params)['rule'] for c in plan.candidates}
    assert rules==({'concatenate'} if count==9 else {'component','concatenate','acronym'})
    assert all(dict(c.transformations[0].params)['case']!='single_initial_title' for c in plan.candidates)
    assert plan.limited_names==(1 if count==9 else 0)


def test_first_eight_names_skip_late_classification_and_limit_output(monkeypatch):
    import mimic.intelligence.organization as module
    original=module.unicodedata.category;calls=[]
    def counted(character):
        assert character!='Ω';calls.append(character);return original(character)
    monkeypatch.setattr(module.unicodedata,'category',counted)
    first=tuple(Candidate('marca'+str(i)+' loja') for i in range(8))
    plan=plan_organization_names(first+tuple(Candidate('Ω '+str(i)) for i in range(100)))
    assert len(plan.candidates)<=192 and plan.limited_names==100
    assert len(calls)<=sum(len(c.value) for c in first)
    assert all(len(c.value)<=256 for c in plan.candidates)
    assert plan_organization_names(first+first)==plan_organization_names(first)


def test_256_ceiling_is_for_lexical_seeds_and_policy_controls_final_length():
    name='ß'*128+' x'
    plan=plan_organization_names((Candidate(name),))
    assert all(len(c.value)<=256 for c in plan.candidates)
    options=dict(organization=Organization(name),intelligence=IntelligenceOptions(enabled=False),
                 mutations=MutationOptions('none',separators=''))
    values=list(GenerationService().prepare(configured(**options)).iter_values())
    assert any(len(v)>256 for v in values)  # Historical Case can expand after planning.
    limited=GenerationService().prepare(configured(**options,policy=PolicyOptions(max_len=256)))
    assert all(len(v)<=256 for v in limited.iter_values())


def test_all_four_sources_keep_profile_first_without_foreign_identity():
    config=configured(target=Target('',TargetProfile(empresa=NAME)),
        context_facts=(ExtractedFact('empresa',Candidate(NAME,(Origin('context_file','ctx:empresa',NAME),))),),
        organization=Organization(NAME,aliases=[NAME],id='foreign-id'))
    candidates={c.value:c for c in GenerationService().prepare(config).iter_candidates()}
    c=candidates['acmeHamburgueria2026@']
    assert c.origins[0]==Origin('profile','empresa',NAME)
    params=dict(next(t for t in c.transformations if t.kind=='organization_name').params)
    assert params['organization_id']=='' and params['organization']==NAME
    assert dict(c.transformations[-1].params)['input']=='acmeHamburgueria'


def test_structural_seeds_noncombinable_and_planner_runs_once(monkeypatch):
    import mimic.application.generation as module
    original=module.plan_organization_names;calls=[]
    def counted(*args,**kwargs):calls.append(args);return original(*args,**kwargs)
    monkeypatch.setattr(module,'plan_organization_names',counted)
    p=GenerationService().prepare(configured(mutations=MutationOptions('none',True,'@!#$')))
    specs=list(p._planned.generator.seeds)
    lexical=[s for s in specs if any(t.kind=='organization_name' for t in s.candidate.transformations)]
    assert len(calls)==1 and len(lexical)==11
    assert all(s.mutable and not s.combinable and s.stages is None for s in lexical)
    assert p.summary().knowledge_seed_count==18
    assert sum(any(t.kind=='knowledge_template' for t in s.candidate.transformations) for s in specs)==12
    assert all(not any(t.kind=='organization_name' for t in s.candidate.transformations)
               for s in specs if any(t.kind=='knowledge_template' for t in s.candidate.transformations))


@pytest.mark.parametrize('source',['ready-file','ready-pack','seed-pack','dataset','none','off-ready'],
                         ids=['ready-file','ready-pack','seed-pack','dataset','no-ready','intelligence-off'])
def test_source_precedence_and_exact_number_replay(tmp_path,monkeypatch,source):
    path=tmp_path/'values.txt';path.write_text('acmeHamburgueria2026@\nacmeHamburgueria123@\n')
    registry=PackRegistry(tmp_path/'registry');sources=SourceOptions()
    if source in ('ready-pack','seed-pack'):
        registry.import_stream(io.BytesIO(path.read_bytes()),id='synthetic',version='1',
            kind='ready' if source=='ready-pack' else 'seed',filename='synthetic.txt')
        sources=SourceOptions(packs=(registry.reference('synthetic@1'),))
    elif source in ('ready-file','off-ready'):sources=SourceOptions(ready_candidate_paths=(str(path),))
    elif source=='dataset':sources=SourceOptions(dataset_paths=(str(path),))
    numbers=(Candidate('123',(Origin('manual','numbers','123'),)),)
    config=configured(sources=sources,number_candidates=numbers,
        intelligence=IntelligenceOptions(enabled=source!='off-ready',reference_year=2026))
    seen=[];original=Generator._compose
    def tracked(self,candidate,stages=None):
        if candidate.value=='acmeHamburgueria':
            effective=self.stages if stages is None else stages
            affix=next(s for s in effective if type(s).__name__=='AffixMutator')
            seen.append(tuple(c.value for c in affix.numbers))
        return original(self,candidate,stages)
    monkeypatch.setattr(Generator,'_compose',tracked)
    p=GenerationService(registry).prepare(config);candidates={c.value:c for c in p.iter_candidates()}
    assert p.evaluated_count==len(candidates)
    deferred=source in ('ready-file','ready-pack')
    assert len(seen)==(2 if deferred else 1)
    assert seen[0]==('123',) if deferred or source=='off-ready' else len(seen[0])==15
    explicit=candidates['acmeHamburgueria123@']
    assert explicit.origins[0].source=='organization' and explicit.origins[-1].source=='manual'
    year=candidates.get('acmeHamburgueria2026@')
    assert year is not None
    if source in ('ready-file','ready-pack','off-ready'):
        assert year.origins[0].source=='ready_candidate' and not year.transformations
    else:
        assert year.origins[0].source=='organization' and year.origins[-1]==Origin('knowledge','recent_year','2026')


def test_preview_reads_no_corpus_or_candidate_stream(tmp_path,monkeypatch):
    missing=tmp_path/'not-opened.txt'
    def forbidden(*args,**kwargs):raise AssertionError('preview executed a corpus/candidate stream')
    monkeypatch.setattr(Generator,'generate_candidates',forbidden)
    monkeypatch.setattr(PackRegistry,'open_verified',forbidden)
    p=GenerationService().prepare(configured(sources=SourceOptions(dataset_paths=(str(missing),),ready_candidate_paths=(str(missing),))))
    assert p.summary().organization_variant_seed_count==11 and p.summary().dataset_line_count is None


@pytest.mark.parametrize('value',['true','false',0,1,None,[],{},object()],
                         ids=['true-string','false-string','zero','one','null','array','object','foreign-object'])
def test_no_boolean_coercion_at_any_request_boundary(value):
    config=configured(organization_variants=value)
    with pytest.raises(InvalidGenerationRequest):config.validate()
    with pytest.raises(InvalidGenerationRequest):config.to_dict()
    with pytest.raises(InvalidGenerationRequest):GenerationRequest.from_dict({'organization_variants':value})


def test_prepared_year_and_restored_switch_never_use_live_clock(monkeypatch):
    import mimic.application.requests as module
    config=configured()
    payload=json.loads(json.dumps(config.to_dict()))
    class NoClock:
        @staticmethod
        def today():raise AssertionError('restored request consulted live clock')
    monkeypatch.setattr(module,'date',NoClock)
    restored=GenerationRequest.from_dict(payload)
    assert restored.organization_variants is True
    assert list(GenerationService().prepare(config).iter_candidates())==list(GenerationService().prepare(restored).iter_candidates())


def store(tmp_path):
    paths=DataPaths(tmp_path);db=Database(paths);db.initialize();return paths,Repository(db)


def test_job_snapshot_freezes_every_original_organization_field(tmp_path):
    paths,repo=store(tmp_path);manager=JobManager(repo,paths);manager.start()
    config=configured(organization=Organization(NAME,aliases=['Acme Foods'],id='synthetic-id'),ranking=RankingOptions.from_budget('quick'))
    expected=[r.candidate.value for r in GenerationService().prepare(config).iter_results()]
    try:
        job=manager.submit(config)
        config.organization.name='Changed';config.organization.aliases[:]=['Changed Alias'];config.organization.id='changed-id'
        config.organization.domains.append('changed.test');config.organization_variants=False
        assert manager.wait(job['id'],20)['status']=='completed'
        saved=repo.get_job(job['id'])['request']
        assert saved['organization_variants'] is True and saved['organization']['name']==NAME
        assert saved['organization']['id']=='synthetic-id' and saved['organization']['aliases']==['Acme Foods']
        assert saved['organization']['domains']==[]
        assert manager.completed_output(job['id']).read_text().splitlines()==expected
        with repo.database.connection() as connection:
            assert connection.execute('PRAGMA user_version').fetchone()[0]==2
    finally:manager.stop()
    restarted=JobManager(repo,paths);restarted.start()
    try:
        assert restarted.completed_output(job['id']).read_text().splitlines()==expected
        assert GenerationRequest.from_dict(saved).organization_variants is True
    finally:restarted.stop()


def test_cancel_true_job_and_recover_old_and_new_snapshots(tmp_path):
    paths,repo=store(tmp_path);entered=threading.Event();release=threading.Event()
    class BlockingService(GenerationService):
        def prepare(self,request):
            prepared=super().prepare(request);iterate=prepared.iter_results
            def delayed(checkpoint=None):
                entered.set();assert release.wait(10);yield from iterate(checkpoint)
            prepared.iter_results=delayed;return prepared
    manager=JobManager(repo,paths,service=BlockingService());manager.start()
    try:
        job=manager.submit(configured())
        assert entered.wait(5);assert manager.cancel(job['id'])['cancel_requested']
        release.set();assert manager.wait(job['id'],10)['status']=='cancelled'
        assert repo.get_job(job['id'])['request']['organization_variants'] is True
        assert not paths.output(job['id']).exists()
    finally:release.set();manager.stop()
    old=repo.create_job(configured(organization_variants=False).to_dict(),None,None)
    new=repo.create_job(configured().to_dict(),None,None);repo.start_job(new['id'])
    part=paths.output(new['id']).with_name('wordlist.txt.part');part.parent.mkdir(parents=True);part.write_text('partial')
    restarted=JobManager(repo,paths);restarted.start()
    try:
        assert repo.get_job(old['id'])['status']==repo.get_job(new['id'])['status']=='failed'
        assert not part.exists()
        assert GenerationRequest.from_dict(repo.get_job(old['id'])['request']).organization_variants is False
        assert GenerationRequest.from_dict(repo.get_job(new['id'])['request']).organization_variants is True
    finally:restarted.stop()


@pytest.mark.parametrize('locale',['pt-BR','en'])
def test_web_unicode_limit_warning_escaping_and_marked_preview(tmp_path,locale,monkeypatch):
    with TestClient(create_app(data_dir=tmp_path)) as client:
        client.cookies.set('mimic_locale',locale)
        page=client.get('/generate');csrf=re.search(r'name="csrf_token" value="([^"]+)"',page.text)[1]
        def forbidden(*args,**kwargs):raise AssertionError('preview generated candidates')
        monkeypatch.setattr(Generator,'generate_candidates',forbidden)
        org=client.post('/api/organizations',json={'name':'İ'*128+' a'}).json()
        data={'csrf_token':csrf,'mode':'organization','organization_id':org['id'],'organization_variants_form':'1',
              'organization_variants':'on','intent':'preview','reference_year':'2026'}
        response=client.post('/generate',data=data)
        assert response.status_code==200 and translate(locale,'warning.organization_names') in response.text
        assert re.search(r'name="organization_variants"[^>]*checked',response.text)
        assert 'Content-Security-Policy' in response.headers
        hostile=client.post('/api/organizations',json={'name':'<img src=https://example.test onerror=alert(1)> loja'}).json()
        response=client.post('/generate',data={**data,'organization_id':hostile['id']})
        assert response.status_code==200 and '<img src=https://example.test' not in response.text
        assert '&lt;img' in response.text
        assert client.app.state.repository.list_jobs()==[]
        assert client.post('/generate',data={**data,'csrf_token':'bad'}).status_code==403


def test_api_old_false_true_payloads_and_candidate_preview(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as client:
        old=configured(organization_variants=False).to_dict()
        for payload,enabled in [(old,False),({**old,'organization_variants':False},False),({**old,'organization_variants':True},True)]:
            response=client.post('/api/jobs',json={'request':payload});assert response.status_code==201
            id=response.json()['id'];assert client.app.state.job_manager.wait(id,20)['status']=='completed'
            saved=client.get('/api/jobs/'+id).json()['request']
            assert saved.get('organization_variants',False) is enabled
            preview=client.get('/api/jobs/'+id+'/candidates').json()
            assert preview and preview[0]['origins']
            values=set(client.get('/api/jobs/'+id+'/download').text.splitlines())
            assert (set(NINE)<=values) is enabled
        for invalid in ['true','false',0,1,None,[],{}]:
            assert client.post('/api/jobs',json={'request':{**old,'organization_variants':invalid}}).status_code==422


def test_catalog_584_keys_and_every_placeholder_set_remains_identical():
    a,b=TRANSLATIONS['pt-BR'],TRANSLATIONS['en'];assert len(a)==len(b)==584 and a.keys()==b.keys()
    fields=lambda value:{field for _,field,_,_ in Formatter().parse(value) if field is not None}
    assert all(fields(a[key])==fields(b[key]) and a[key].strip() and b[key].strip() for key in a)
