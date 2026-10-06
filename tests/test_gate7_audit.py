"""Gate 7 regression contracts for gaps found in the pre-commit audit."""
from dataclasses import asdict, replace
import json
from pathlib import Path
import re
import threading

import pytest

from mimic.application import (
    GenerationLimits, GenerationRequest, GenerationService, IntelligenceOptions,
    InvalidGenerationRequest, MutationOptions, PolicyOptions, SourceOptions,
)
from mimic.core.candidate import Candidate, Origin, Transformation
from mimic.domain.models import Organization, Target
from mimic.profile.schema import TargetProfile
from tests.test_web_ui import web, submit


def request(**kwargs):
    return GenerationRequest(
        intelligence=kwargs.pop('intelligence',IntelligenceOptions(reference_year=2026, service_profiles=('wordpress',))),
        mutations=kwargs.pop('mutations',MutationOptions(leet_mode='none',separators='!#*@')),
        limits=kwargs.pop('limits',GenerationLimits(max_candidates_per_word=500)),
        **kwargs,
    )


def candidates(r):
    return {c.value:c for c in GenerationService().prepare(r).iter_candidates()}


def test_ready_beats_knowledge_numeric_affix(tmp_path):
    path=tmp_path/'ready.txt'
    path.write_text('Acme123\nAcme123!\n',encoding='utf-8')
    cs=candidates(request(organization=Organization('ACME'),limits=GenerationLimits(),sources=SourceOptions(ready_candidate_paths=(str(path),))))
    for line,value in enumerate(('Acme123','Acme123!'),1):
        assert cs[value]==Candidate(value,(Origin('ready_candidate',f'{path}:{line}',value),))
    assert cs['Acme2026#'].origins==(Origin('organization','name','ACME'),Origin('knowledge','recent_year','2026'))


def test_empty_intelligence_rejected_before_iteration():
    with pytest.raises(InvalidGenerationRequest,match='contextual seed'):
        GenerationService().prepare(request(intelligence=IntelligenceOptions(reference_year=2026)))


def test_service_only_has_no_unanchored_global_roles():
    r=request()
    cs=candidates(r)
    assert 'admin123!' in cs
    assert cs['admin123!'].origins==(Origin('knowledge','service.wordpress.role','admin'),Origin('knowledge','common_number','123'))
    assert not any(o==Origin('knowledge','role','support') for c in cs.values() for o in c.origins)


def test_explicit_derivation_still_beats_ready_and_empty_vocabulary_stream(tmp_path):
    path=tmp_path/'ready.txt';path.write_text('ACME123!\nAcme123!\n',encoding='utf-8')
    explicit=Candidate('123',(Origin('manual','number','123'),))
    r=request(target=Target('',TargetProfile(empresa='ACME')),organization=Organization('ACME'),
              number_candidates=(explicit,),sources=SourceOptions(ready_candidate_paths=(str(path),)),limits=GenerationLimits())
    c=candidates(r)['Acme123!']
    assert c==Candidate('Acme123!',(Origin('profile','empresa','ACME'),*explicit.origins),(
        Transformation('case',(('mode','title'),)),Transformation('affix',(
            ('input','Acme'),('token','123'),('placement','suffix'),('separator','!'),
            ('separator_position','after'),('input_steps','1'),('token_steps','0')))))
    # No roles/templates: delayed affixes must still run after the ready stream.
    minimal=replace(r.intelligence,corporate_roles=False,service_profiles=())
    after=candidates(request(organization=Organization('ACME'),intelligence=minimal,
                 sources=r.sources,limits=GenerationLimits()))
    assert after['Acme123!'].transformations==()
    assert after['Acme2026#'].origins[-1]==Origin('knowledge','recent_year','2026')


def test_profile_beats_organization_exact_template_cause():
    r=request(target=Target('',TargetProfile(empresa='ACME')),organization=Organization('ACME',aliases=['ACME']),limits=GenerationLimits())
    c=candidates(r)['Acmeadmin123!']
    assert c==Candidate('Acmeadmin123!',(
        Origin('profile','empresa','ACME'),Origin('knowledge','role','admin'),Origin('knowledge','common_number','123')),
        (Transformation('knowledge_template',(('left','ACME'),('right','admin'),('template','organization_role'),('version','knowledge-v1'))),
         Transformation('case',(('mode','title'),)),Transformation('affix',(
             ('input','Acmeadmin'),('token','123'),('placement','suffix'),('separator','!'),
             ('separator_position','after'),('input_steps','2'),('token_steps','0')))))


def test_dataset_loses_to_knowledge_numeric_and_template(tmp_path):
    path=tmp_path/'dataset.txt';path.write_text('Acme123!\nAcmeadmin123!\n',encoding='utf-8')
    r=request(organization=Organization('ACME'),sources=SourceOptions(dataset_paths=(str(path),)),limits=GenerationLimits())
    with_dataset=candidates(r)
    baseline=candidates(replace(r,sources=SourceOptions()))
    for value in ('Acme123!','Acmeadmin123!'):
        assert with_dataset[value]==baseline[value]
        assert all(origin.source!='dataset' for origin in with_dataset[value].origins)


@pytest.mark.parametrize('year,window',[(4,(4,3,2,1)),(2026,(2026,2025,2024,2023)),(9999,(9999,9998,9997,9996))])
def test_recent_year_boundaries(year,window):
    from mimic.intelligence.planning import recent_years
    assert recent_years(year)==window
    r=request(organization=Organization('ACME'),intelligence=IntelligenceOptions(reference_year=year))
    assert GenerationService().prepare(r).summary().recent_years==window


def test_reference_capture_survives_changed_application_clock(monkeypatch):
    import mimic.application.requests as module
    class AtSubmit:
        @staticmethod
        def today():
            from datetime import date
            return date(2026,12,31)
    monkeypatch.setattr(module,'date',AtSubmit)
    r=request(organization=Organization('ACME'),intelligence=IntelligenceOptions())
    payload=json.loads(json.dumps(r.to_dict()))
    class ExecutionClock:
        @staticmethod
        def today():
            raise AssertionError('clock consulted after construction/snapshot')
    monkeypatch.setattr(module,'date',ExecutionClock)
    after=GenerationRequest.from_dict(payload)
    assert after.intelligence.reference_year==2026
    assert after.to_dict()==r.to_dict()
    assert candidates(after)['ACME2026#'].origins[-1]==Origin('knowledge','recent_year','2026')


@pytest.mark.parametrize('toggles',[True,False])
def test_rich_intelligence_request_roundtrip(tmp_path,toggles):
    from mimic.domain.context import ExtractedFact
    r=request(target=Target('João',TargetProfile(nome='João',empresa='São Paulo',apelidos=['Jô']),
                            organization=Organization('Herdada')),
              organization=Organization('São Paulo',aliases=['Árvore'],domains=['ACME.COM.BR']),
              intelligence=IntelligenceOptions(enabled=toggles,common_numbers=toggles,recent_years=toggles,
                                               corporate_roles=toggles,service_profiles=('wordpress','mysql'),reference_year=2026),
              sources=SourceOptions(dataset_paths=(str(tmp_path/'dataset.txt'),),ready_candidate_paths=(str(tmp_path/'ready.txt'),),include_ptbr=True),
              policy=PolicyOptions(min_len=8,max_len=32,require_digit=True,require_special=True),
              limits=GenerationLimits(150,30),base_candidates=(Candidate('Ana',(Origin('manual','name','Ana'),)),),
              context_facts=(ExtractedFact('pet',Candidate('Luna',(Origin('manual','pet','Luna'),))),))
    data1=r.to_dict()
    data2=GenerationRequest.from_dict(json.loads(json.dumps(data1,ensure_ascii=False))).to_dict()
    assert data1==data2


@pytest.mark.parametrize('domain,expected',[
    ('acme.com.br','acme'),('portal.acme.com.br','portal'),('ACME.COM.BR','acme'),
    ('sub.domain.example','sub'),('localhost',None),('https://acme.com.br',None),
    ('a_b.test',None),('-bad.test',None),('acme..br',None),('acme.com.br.','acme'),
])
def test_first_dns_label_exact_rule(domain,expected):
    r=request(organization=Organization('',domains=[domain]))
    terms=GenerationService()._organization_terms(r,[])
    if expected is None:
        assert terms==()
    else:
        assert terms==(Candidate(expected,(Origin('organization','domain',domain),),(
            Transformation('organization_domain_label',(('input',domain),('rule','first_dns_label'))),)),)


def test_profile_vocab_defensive_immutability():
    from dataclasses import FrozenInstanceError
    from mimic.intelligence import ServiceProfile
    from mimic.intelligence.builtins import get_service_profile
    profile=get_service_profile('wordpress')
    with pytest.raises(AttributeError): profile.roles.append('contamination')
    with pytest.raises(FrozenInstanceError): profile.roles=('changed',)
    values=['admin']
    custom=ServiceProfile('custom','Custom',values,values,'v1')
    values.append('changed')
    assert custom.tokens==custom.roles==('admin',)
    assert get_service_profile('wordpress').roles==('admin','editor')


def test_multi_service_templates_remain_internally_coherent():
    from mimic.intelligence.planning import plan_intelligence
    options=IntelligenceOptions(reference_year=2026,service_profiles=('wordpress','mysql'))
    plan=plan_intelligence(options,(Candidate('ACME',(Origin('organization','name','ACME'),)),))
    for seed in plan.seeds:
        profile_ids={origin.field.split('.')[1] for origin in seed.candidate.origins if origin.field.startswith('service.')}
        assert len(profile_ids)<=1
    r=request(organization=Organization('ACME'),intelligence=options,limits=GenerationLimits())
    cs=candidates(r)
    assert 'wproot123!' not in cs and 'mysqleditor123!' not in cs
    assert cs['mysqldba123!'].origins==(
        Origin('knowledge','service.mysql.token','mysql'),Origin('knowledge','service.mysql.role','dba'),
        Origin('knowledge','common_number','123'))
    assert [step.kind for step in cs['mysqldba123!'].transformations]==['knowledge_template','case','affix']
    assert cs['wpadmin123!'].origins==(
        Origin('knowledge','service.wordpress.token','wp'),Origin('knowledge','service.wordpress.role','admin'),
        Origin('knowledge','common_number','123'))


def test_generic_combine_receives_only_explicit_partners(monkeypatch,tmp_path):
    from mimic.mutators.combine import CombineMutator
    calls=[]
    original=CombineMutator.mutate_candidate
    def record(self,candidate):
        calls.append(candidate)
        yield from original(self,candidate)
    monkeypatch.setattr(CombineMutator,'mutate_candidate',record)
    ready=tmp_path/'ready.txt';ready.write_text('ready-exact\n',encoding='utf-8')
    r=request(target=Target('Ana',TargetProfile(nome='Ana',apelidos=['Bia'],empresa='ACME')),
              organization=Organization('ACME'),sources=SourceOptions(ready_candidate_paths=(str(ready),)),
              mutations=MutationOptions(leet_mode='none',separators='!',combine=True),limits=GenerationLimits(50))
    cs=candidates(r)
    assert calls and {candidate.value for candidate in calls}=={'Ana','Bia'}
    assert all(origin.source=='profile' and origin.field in ('nome','apelidos') for c in calls for origin in c.origins)
    assert 'ACMEadminACME' not in cs
    assert all(sum(step.kind=='knowledge_template' for step in c.transformations)<=1 for c in cs.values())


def test_reverse_retains_causal_template_history():
    cs=candidates(request(organization=Organization('ACME')))
    original=cs['ACMEadmin']
    assert cs['nimdaEMCA']==Candidate('nimdaEMCA',original.origins,
                                    (original.transformations[0],Transformation('reverse')))


@pytest.mark.parametrize('policy',[
    PolicyOptions(min_len=15),PolicyOptions(require_digit=True),PolicyOptions(require_special=True),
    PolicyOptions(min_len=8,require_digit=True,require_special=True),
])
def test_intelligence_obeys_policy(policy):
    from mimic.core.policy import PasswordPolicy
    cs=candidates(request(organization=Organization('ACME'),policy=policy))
    assert cs and all(PasswordPolicy(**asdict(policy)).accepts(value) for value in cs)


def test_generic_seed_stages_use_existing_engine_and_policy():
    from mimic.core.generator import Generator
    from mimic.core.seed import Seed
    from mimic.mutators.case import CaseMutator
    from mimic.mutators.affix import AffixMutator
    source=Candidate('opaque',(Origin('test','seed','opaque'),))
    token=Candidate('7',(Origin('test','token','7'),))
    g=Generator([], [CaseMutator()], seeds=[Seed(source,stages=(AffixMutator([token],''),))])
    actual=list(g.generate_candidates())
    assert actual[0]==source
    assert actual[1].origins==source.origins+token.origins
    assert actual[1].value=='opaque7' and actual[1].transformations[0].kind=='affix'
    with pytest.raises(ValueError,match='Ready candidates'):
        Seed(source,mutable=False,stages=(CaseMutator(),))


def test_web_disable_is_persisted_and_old_api_requests_work(web):
    client,app=web
    old={'base_candidates':[{'value':'Legacy','origins':[{'source':'manual','field':'name','value':'Legacy'}]}],
         'mutations':{'leet_mode':'none'}}
    response=client.post('/api/jobs',json={'request':old})
    assert response.status_code==201
    old_job=app.state.job_manager.wait(response.json()['id'],5)
    assert old_job['status']=='completed' and old_job['request']['intelligence']['enabled'] is False
    assert old_job['candidate_count']==4
    response=submit(client,'/generate',{'mode':'quick','empresa':'ACME','intelligence_form':'1','leet_mode':'none'},follow_redirects=False)
    assert response.status_code==303
    job=app.state.job_manager.wait(response.headers['location'].split('/')[-1],5)
    assert job['status']=='completed' and job['request']['intelligence']['enabled'] is False
    assert job['candidate_count']==4


def test_unknown_service_cli_application_and_web(web,capsys):
    from mimic.cli import main
    with pytest.raises(SystemExit) as error:
        main(['generate','--service','does-not-exist'])
    assert error.value.code==2 and 'invalid choice' in capsys.readouterr().err
    with pytest.raises(InvalidGenerationRequest,match='unknown service profile'):
        GenerationService().prepare(request(intelligence=IntelligenceOptions(reference_year=2026,service_profiles=('does-not-exist',))))
    client,_=web
    response=submit(client,'/generate',{'mode':'quick','empresa':'ACME','intelligence_form':'1',
                                      'intelligence_enabled':'on','service_profiles':'does-not-exist','intent':'preview'})
    assert response.status_code==422 and 'unknown service profile' in response.text


def test_preview_no_files_open_even_with_ready_and_deferred_affixes(monkeypatch):
    from mimic.core.generator import Generator
    def forbidden(*args,**kwargs):
        raise AssertionError('preview executed candidates or opened a corpus')
    r=request(organization=Organization('ACME'),sources=SourceOptions(dataset_paths=('not-read.txt',),ready_candidate_paths=('not-read-ready.txt',)))
    monkeypatch.setattr(Generator,'generate_candidates',forbidden)
    monkeypatch.setattr(Path,'open',forbidden)
    p=GenerationService().prepare(r)
    summary=p.summary().to_dict()
    assert (summary['knowledge_seed_count'],summary['knowledge_template_seed_count'],summary['service_derived_seed_count'],summary['knowledge_number_count'])==(38,28,20,14)


def test_python310_syntax_and_generic_core_text():
    import ast
    root=Path(__file__).parents[1]/'mimic'
    for path in root.rglob('*.py'):
        ast.parse(path.read_text(),feature_version=(3,10))
    for path in (root/'core').glob('*.py'):
        text=path.read_text()
        assert not any(term in text for term in ('Organization','ServiceProfile','wordpress','mysql','reference_year','knowledge'))


@pytest.mark.parametrize('kwargs',[
    {'target':Target('')}, {'base_candidates':(Candidate(' '),)},
    {'organization':Organization(' ',aliases=[' '])},
])
def test_blank_values_are_not_contextual_anchors(kwargs):
    with pytest.raises(InvalidGenerationRequest,match='contextual seed'):
        GenerationService().prepare(request(intelligence=IntelligenceOptions(reference_year=2026),**kwargs))


def test_deferred_affixes_are_hash_seed_independent(tmp_path):
    import os,subprocess,sys
    ready=tmp_path/'ready.txt';ready.write_text('ACME123!\n',encoding='utf-8')
    r=request(organization=Organization('ACME'),target=Target('Ana',TargetProfile(nome='Ana',apelidos=['Bia'])),
              sources=SourceOptions(ready_candidate_paths=(str(ready),)),limits=GenerationLimits(50),
              mutations=MutationOptions(leet_mode='partial',combine=True))
    script='''
import json,sys
from dataclasses import asdict
from mimic.application import GenerationRequest,GenerationService
r=GenerationRequest.from_dict(json.load(sys.stdin))
print(json.dumps([asdict(c) for c in GenerationService().prepare(r).iter_candidates()],ensure_ascii=False))
'''
    results=[]
    for seed in ('1','42','777'):
        results.append(subprocess.check_output([sys.executable,'-B','-c',script],input=json.dumps(r.to_dict()).encode(),
            env={**os.environ,'PYTHONHASHSEED':seed,'PYTHONDONTWRITEBYTECODE':'1'},stderr=subprocess.DEVNULL))
    assert results[0]==results[1]==results[2]
