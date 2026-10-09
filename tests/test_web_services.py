"""SSR service knowledge, safe navigation and the existing generation flow."""
from dataclasses import replace
import html
import re
from string import Formatter

from fastapi.testclient import TestClient
import pytest

from mimic.api import create_app
from mimic.application import GenerationService
from mimic.intelligence import catalog
from mimic.web.i18n import TRANSLATIONS, translate
from mimic.web.security import HTML_CSP


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as client:
        yield client


def csrf(client):
    return re.search(r'name="csrf_token" value="([^"]+)"', client.get('/generate').text)[1]


@pytest.mark.parametrize('locale', ['pt-BR', 'en'])
@pytest.mark.parametrize('path', ['/services', '/services/grafana', '/services/rabbitmq',
    '/services/postgresql', '/services/wordpress', '/services?category=common'],
    ids=['list', 'grafana', 'rabbitmq', 'postgresql', 'wordpress', 'common'])
def test_catalog_pages_localization_and_browser_security(client, locale, path):
    client.cookies.set('mimic_locale', locale)
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers['Content-Language'] == locale
    assert response.headers['Vary'] == 'Cookie'
    assert response.headers['Content-Security-Policy'] == HTML_CSP
    assert f'lang="{locale}"' in response.text
    assert translate(locale, 'catalog.title') in response.text
    assert 'theme-init.js' in response.text and 'data-theme-toggle' in response.text
    assert '<script>' not in response.text and 'onclick=' not in response.text
    assert 'href="/services"' in response.text
    assert 'data-category="common_value"' in response.text
    if path.endswith(('postgresql', 'wordpress')):
        assert translate(locale, 'catalog.no_defaults') in response.text
        assert '<td><code>' not in response.text
    if path.endswith(('grafana', 'rabbitmq')):
        assert 'data-category="documented_default"' in response.text
        assert 'data-category="generated_candidate"' in response.text
        assert translate(locale, 'catalog.applicability') in response.text
        assert translate(locale, 'catalog.source') in response.text
        if path.endswith('rabbitmq'):
            assert 'localhost' in response.text


def test_local_search_alias_and_unknown_inputs(client):
    response = client.get('/services', params={'q': 'pgsql'})
    assert response.status_code == 200
    assert 'href="/services/postgresql"' in response.text
    assert 'href="/services/grafana"' not in response.text
    response = client.get('/services', params={'q': 'no matching service'})
    assert translate('pt-BR', 'catalog.no_services') in response.text
    assert client.get('/services/unknown').status_code == 404
    assert client.get('/services?category=unknown').status_code == 400
    assert client.get('/generate?service=unknown').status_code == 400
    assert client.get('/services', params={'q': 'x' * 201}).status_code == 422


def test_search_and_credential_values_are_escaped(client, monkeypatch):
    value = '"><script>alert(1)</script>'
    response = client.get('/services', params={'q': value})
    assert value not in response.text
    rendered = re.search(r'id="service-search"[^>]*value="([^"]*)"', response.text)[1]
    assert html.unescape(rendered) == value
    credential = replace(catalog.DEFAULT_CREDENTIALS[0], username='<script>username</script>',
                         password='<b>password</b>')
    monkeypatch.setattr(catalog, 'list_credentials', lambda service_id=None: (credential,))
    response = client.get('/services/grafana')
    assert '<script>username</script>' not in response.text and '&lt;script&gt;username&lt;/script&gt;' in response.text
    assert '<b>password</b>' not in response.text and '&lt;b&gt;password&lt;/b&gt;' in response.text


def test_generation_navigation_preselects_without_execution(client, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('GET generated candidates')
    monkeypatch.setattr(GenerationService, 'prepare', forbidden)
    page = client.get('/services/grafana')
    assert 'href="/generate?service=grafana"' in page.text
    response = client.get('/generate?service=grafana')
    assert response.status_code == 200
    assert re.search(r'name="service_profiles" value="grafana"\s+checked', response.text)
    assert not re.search(r'name="service_profiles" value="rabbitmq"\s+checked', response.text)
    assert not re.search(r'name="include_common_passwords"[^>]*checked', response.text)
    assert client.app.state.repository.list_jobs() == []
    assert 'name="csrf_token"' in response.text


def test_service_common_preview_job_and_causal_explanation(client):
    data = {'csrf_token': csrf(client), 'mode': 'quick', 'service_profiles': 'grafana',
        'intelligence_form': '1', 'intelligence_enabled': 'on', 'common_numbers': 'on', 'recent_years': 'on',
        'reference_year': '2026', 'max_candidates_per_word': '20', 'output_priority': 'exhaustive',
        'include_common_passwords': 'on', 'intent': 'preview', 'leet_mode': 'partial', 'separators': '!'}
    preview = client.post('/generate', data=data)
    assert preview.status_code == 200
    assert 'common-v1' in preview.text
    assert re.search(r'name="include_common_passwords"[^>]*checked', preview.text)
    assert client.app.state.repository.list_jobs() == []
    data['intent'] = 'generate'
    response = client.post('/generate', data=data, follow_redirects=False)
    assert response.status_code == 303
    job_id = response.headers['location'].split('/')[-1]
    assert client.app.state.job_manager.wait(job_id, 10)['status'] == 'completed'
    job = client.app.state.repository.get_job(job_id)
    assert job['request']['sources']['include_common_passwords'] is True
    assert job['request']['intelligence']['service_profiles'] == ['grafana']
    content = client.get('/api/jobs/' + job_id + '/download').text.splitlines()
    assert 'changeme' in content
    page = client.get('/jobs/' + job_id)
    assert 'knowledge.common_password' in page.text
    assert translate('pt-BR', 'catalog.common_password_origin') in page.text
    assert 'knowledge.service.grafana.token' in page.text


def test_common_only_form_is_opt_in_and_csrf_protected(client):
    data = {'csrf_token': csrf(client), 'mode': 'quick', 'intelligence_form': '1',
        'include_common_passwords': 'on', 'intent': 'generate'}
    response = client.post('/generate', data=data, follow_redirects=False)
    assert response.status_code == 303
    job_id = response.headers['location'].split('/')[-1]
    assert client.app.state.job_manager.wait(job_id, 5)['status'] == 'completed'
    assert client.get('/api/jobs/' + job_id + '/download').text.splitlines() == list(catalog.COMMON_VOCABULARY.passwords)
    data.pop('csrf_token')
    assert client.post('/generate', data=data).status_code == 403


def test_catalog_translation_parity_and_complete_metadata():
    assert TRANSLATIONS['pt-BR'].keys() == TRANSLATIONS['en'].keys()
    keys = [key for key in TRANSLATIONS['en'] if key.startswith('catalog.') or key == 'nav.services']
    assert len(keys) == 72
    for key in keys:
        pt, en = TRANSLATIONS['pt-BR'][key], TRANSLATIONS['en'][key]
        fields = lambda value: {field for _, field, _, _ in Formatter().parse(value) if field is not None}
        assert fields(pt) == fields(en) and pt.strip() and en.strip()
    for service in catalog.SERVICES:
        assert 'catalog.service.' + service.id + '.auth' in keys
        for index in range(1, len(service.references) + 1):
            assert f'catalog.service.{service.id}.source.{index}' in keys
    for credential in catalog.DEFAULT_CREDENTIALS:
        for index in range(1, len(credential.restrictions) + 1):
            assert f'catalog.credential.{credential.id}.restriction.{index}' in keys
