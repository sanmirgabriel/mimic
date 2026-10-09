"""Pack SSR and API integrate the same registry with request-local presentation."""
from dataclasses import asdict
import hashlib
import html
import io
import json
from pathlib import Path
from markupsafe import escape

from fastapi.testclient import TestClient
import pytest

from mimic.api import create_app
from mimic.application import GenerationRequest, SourceOptions, RankingOptions
from mimic.packs import PackRegistry, PackReference
from mimic.packs import registry as storage
from mimic.web.i18n import translate
from tests.test_web_i18n import token


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(data_dir=tmp_path/'custom-data')) as client:
        yield client


def upload(client, *, contents=b'Example2026!\n', id='example', version='1', kind='ready', **values):
    return client.post('/packs/import',data={'csrf_token':token(client), 'id':id,'version':version,
        'kind':kind,'language':'pt-BR','license':'NOASSERTION',**values},
        files={'pack_file':('local.txt',contents)},follow_redirects=False)


@pytest.mark.parametrize('locale', ['pt-BR','en'])
def test_pack_management_versioning_integrity_and_escaping(client,locale):
    client.cookies.set('mimic_locale',locale)
    assert translate(locale,'pack.empty') in client.get('/packs').text
    hostile='<script>alert("x")</script>'
    response=upload(client,name=hostile,description=hostile,attribution=hostile)
    assert response.status_code==303 and response.headers['location']=='/packs/example@1'
    page=client.get(response.headers['location'])
    assert page.headers['content-language']==locale and f'lang="{locale}"' in page.text
    assert hostile not in page.text and str(escape(hostile)) in page.text
    assert translate(locale,'pack.license_unknown') in page.text
    assert translate(locale,'pack.recorded') in page.text
    assert upload(client,name=hostile,description=hostile,attribution=hostile).status_code==303
    assert upload(client).status_code==422
    conflict=upload(client,contents=b'different\n')
    assert conflict.status_code==422 and translate(locale,'pack.error.conflict') in conflict.text
    assert upload(client,version='2').status_code==303
    verified=client.post('/packs/example@1/verify',data={'csrf_token':token(client)})
    assert verified.status_code==200 and translate(locale,'pack.verified') in verified.text
    registry=PackRegistry(client.app.state.job_manager.paths)
    assert len(registry.list())==2
    path=registry.root/'example'/'1'/'corpus.txt';path.write_bytes(b'tampered\n')
    failed=client.post('/packs/example@1/verify',data={'csrf_token':token(client)})
    assert failed.status_code==422 and translate(locale,'pack.error.digest') in failed.text


@pytest.mark.parametrize('locale', ['pt-BR','en'])
@pytest.mark.parametrize('problem,key', [('utf8','utf8'),('kind','kind'),('identity','identity'),
    ('file','file'),('url','metadata'),('size','size_limit')])
def test_import_errors_localized_and_registry_stays_empty(client,locale,problem,key,monkeypatch):
    client.cookies.set('mimic_locale',locale)
    kwargs={}
    if problem=='utf8':kwargs['contents']=b'\xff'
    if problem=='kind':kwargs['kind']='auto'
    if problem=='identity':kwargs['id']='../../outside'
    if problem=='url':kwargs['source_url']='javascript:alert(1)'
    if problem=='size':
        monkeypatch.setattr('mimic.web.routes.MAX_UPLOAD_BYTES',2)
    if problem=='file':
        response=client.post('/packs/import',data={'csrf_token':token(client),'path':'/etc/passwd'})
    else:response=upload(client,**kwargs)
    assert response.status_code==422 and translate(locale,'pack.error.'+key) in response.text
    registry=PackRegistry(client.app.state.job_manager.paths)
    assert registry.list()==[]
    assert not list(registry.root.glob('.import-*'))


def test_csrf_origin_and_browser_paths_cannot_import(client):
    data={'id':'bad','version':'1','kind':'seed'}
    assert client.post('/packs/import',data=data,files={'pack_file':('ok.txt',b'ok')}).status_code==403
    data['csrf_token']=token(client)
    assert client.post('/packs/import',data=data,files={'pack_file':('ok.txt',b'ok')},
        headers={'origin':'https://external.test'}).status_code==403
    assert client.post('/packs/import',data=data,files={'pack_file':('../../escape.txt',b'ok')}).status_code==422
    assert PackRegistry(client.app.state.job_manager.paths).list()==[]


def test_firefox_null_origin_requires_same_origin_signal_and_csrf(client):
    headers={'origin':'null','sec-fetch-site':'same-origin'}
    values={'csrf_token':token(client),'id':'firefox','version':'1','kind':'ready'}
    assert client.post('/packs/import',data=values,files={'pack_file':('local.txt',b'Example2026!\n')},
        headers=headers,follow_redirects=False).status_code==303
    assert client.post('/packs/firefox@1/verify',data={'csrf_token':token(client)},headers=headers).status_code==200
    assert client.post('/packs/firefox@1/verify',headers=headers).status_code==403
    for unsafe in ({'origin':'null'}, {'origin':'null','sec-fetch-site':'cross-site'},
                   {'origin':'https://external.test','sec-fetch-site':'same-origin'}):
        assert client.post('/packs/firefox@1/verify',data={'csrf_token':token(client)},headers=unsafe).status_code==403


@pytest.mark.parametrize('locale', ['pt-BR','en'])
def test_selection_preview_lazy_completed_download_and_provenance(client,locale,monkeypatch):
    client.cookies.set('mimic_locale',locale)
    assert upload(client,contents='Example2026!\nrecepção\n'.encode()).status_code==303
    assert upload(client,id='second',contents=b'Example2026!\nUnique2026!\n').status_code==303
    page=client.get('/generate')
    assert 'value="example@1"' in page.text and 'value="second@1"' in page.text
    data={'csrf_token':token(client),'mode':'quick','intelligence_form':'1','intent':'preview',
          'packs':['second@1','example@1'],'output_priority':'quick','leet_mode':'full','combine':'on'}
    with monkeypatch.context() as guard:
        guard.setattr(storage,'inspect_stream',lambda *a,**kw:pytest.fail('preview read corpus'))
        preview=client.post('/generate',data=data)
    assert preview.status_code==200
    assert translate(locale,'pack.selected') in preview.text
    digest=PackRegistry(client.app.state.job_manager.paths).get('example@1').sha256
    assert digest in preview.text and 'checked' in preview.text
    data['intent']='generate'
    submitted=client.post('/generate',data=data,follow_redirects=False)
    assert submitted.status_code==303
    job_id=submitted.headers['location'].split('/')[-1]
    job=client.app.state.job_manager.wait(job_id,10)
    assert job['status']=='completed' and job['candidate_count']==3
    assert [p['id'] for p in job['request']['sources']['packs']]==['second','example']
    assert job['request']['sources']['packs'][1]['sha256']==digest
    download=client.get('/api/jobs/'+job_id+'/download')
    assert set(download.text.splitlines())=={'Example2026!','Unique2026!','recepção'}
    candidates=client.get('/api/jobs/'+job_id+'/candidates').json()
    assert all(c['transformations']==[] and c['score']==50 for c in candidates)
    common=next(c for c in candidates if c['value']=='Example2026!')
    assert common['origins'][0]['field']=='pack:second@1:1'
    with monkeypatch.context() as guard:
        guard.setattr(storage,'inspect_stream',lambda *a,**kw:pytest.fail('job render read corpus'))
        details=client.get('/jobs/'+job_id)
    assert details.status_code==200 and digest in details.text and 'pack:second@1:1' in details.text
    # Historical metadata remains visible even if the managed source becomes unavailable.
    (PackRegistry(client.app.state.job_manager.paths).root/'example'/'1'/'manifest.json').unlink()
    historical=client.get('/jobs/'+job_id)
    assert historical.status_code==200 and digest in historical.text


def test_api_minimal_reference_freezes_metadata_and_old_requests_unchanged(client):
    assert upload(client).status_code==303
    registry=PackRegistry(client.app.state.job_manager.paths)
    metadata=registry.get('example@1')
    payload=GenerationRequest(sources=SourceOptions(packs=(PackReference('example','1',metadata.sha256),))).to_dict()
    response=client.post('/api/jobs',json={'request':payload})
    assert response.status_code==201
    job=client.app.state.job_manager.wait(response.json()['id'],10)
    assert job['status']=='completed'
    assert job['request']['sources']['packs'][0]['metadata']==metadata.to_dict()
    for reference in [{'id':'example','version':'1','sha256':'0'*64},
                      {'id':'../example','version':'1','sha256':metadata.sha256},
                      {'id':'missing','version':'1','sha256':metadata.sha256}]:
        payload['sources']['packs']=[reference]
        assert client.post('/api/jobs',json={'request':payload}).status_code==422
    snapshots=[]
    for locale in ('pt-BR','en'):
        client.cookies.set('mimic_locale',locale)
        snapshots.append(client.get('/api/jobs/'+job['id']+'/candidates').json())
    assert snapshots[0]==snapshots[1]
    old=GenerationRequest.from_dict({'sources':{'include_ptbr':True}})
    assert 'packs' not in old.to_dict()['sources']


@pytest.mark.parametrize('locale', ['pt-BR','en'])
def test_generation_selection_errors_are_localized(client,locale):
    client.cookies.set('mimic_locale',locale)
    response=client.post('/generate',data={'csrf_token':token(client),'mode':'quick',
        'nome':'Pedro','packs':'missing@1','intent':'preview'})
    assert response.status_code==422 and translate(locale,'pack.error.unavailable') in response.text


def test_catalog_contains_every_pack_error_and_theme_tokens_unchanged():
    from mimic.web.i18n import TRANSLATIONS
    from string import Formatter
    for key in TRANSLATIONS['en']:
        if key.startswith('pack.') or key=='nav.packs':
            assert TRANSLATIONS['pt-BR'][key]
            assert [f for _,f,_,_ in Formatter().parse(TRANSLATIONS['en'][key]) if f]==[
                f for _,f,_,_ in Formatter().parse(TRANSLATIONS['pt-BR'][key]) if f]
    css=Path('mimic/web/static/app.css').read_text()
    assert '.pack-digest' in css and 'var(--muted)' in css
