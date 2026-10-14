"""Frequency SSR is read-only, localized, confined and escaped."""
from dataclasses import replace
import json
import logging

from fastapi.testclient import TestClient
import pytest

from mimic.api import create_app
from mimic.application import GenerationService
from mimic.application.observations import PatternAnalysisService
from mimic.frequencies import FrequencyRegistry
from mimic.web.i18n import TRANSLATIONS, translate
from mimic.web.security import HTML_CSP
from tests.test_frequencies import example


@pytest.mark.parametrize('locale', ['pt-BR', 'en'])
@pytest.mark.parametrize('path', ['/frequencies', '/frequencies/synthetic-a@1'])
def test_localized_readonly_frequency_views(tmp_path, monkeypatch, locale, path):
    d = example(); FrequencyRegistry(tmp_path).import_dataset(d)
    def forbidden(*args, **kwargs): raise AssertionError('unexpected generation or analysis')
    monkeypatch.setattr(GenerationService, 'prepare', forbidden)
    monkeypatch.setattr(PatternAnalysisService, 'analyze', forbidden)
    with TestClient(create_app(data_dir=tmp_path)) as client:
        client.cookies.set('mimic_locale', locale)
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers['Content-Security-Policy'] == HTML_CSP
        assert response.headers['Cache-Control'] == 'no-store'
        assert response.headers['Content-Language'] == locale
        assert translate(locale, 'frequency.distinction') in response.text
        assert translate(locale, 'frequency.privacy') in response.text
        assert 'type="file"' not in response.text
        if '@' in path:
            assert d.sha256 in response.text and '30/100' in response.text
            assert 'CC0-1.0' in response.text and d.source.attribution in response.text
            assert translate(locale, 'frequency.missing') in response.text
        assert client.get('/api/jobs').json() == []
        assert not (tmp_path / 'uploads').exists()
        assert client.post('/frequencies', files={'file':('raw.txt', b'PrivateSentinel')}).status_code == 405


def test_web_metadata_escaping_unknown_values_and_search(tmp_path):
    d = example(); marker = '<script>alert("fixture")</script>'
    d = replace(d, source=replace(d.source, title=marker, methodology='Unicode: ação e evidência',
                                license='NOASSERTION', redistribution='unknown'))
    FrequencyRegistry(tmp_path).import_dataset(d)
    with TestClient(create_app(data_dir=tmp_path)) as client:
        page = client.get('/frequencies/synthetic-a@1')
        assert page.status_code == 200 and marker not in page.text and '&lt;script&gt;' in page.text
        assert translate('pt-BR', 'frequency.unknown_rights') in page.text
        assert client.get('/frequencies?q=ação').status_code == 200
        assert 'synthetic-a@1' not in client.get('/frequencies?q=unmatched-query').text
        hostile = client.get('/frequencies', params={'q':marker})
        assert hostile.status_code == 200 and marker not in hostile.text


@pytest.mark.parametrize('mode', ['malformed', 'digest', 'symlink', 'missing', 'directory-error'])
def test_web_invalid_evidence_never_reflected_or_logged(tmp_path, caplog, monkeypatch, mode):
    r = FrequencyRegistry(tmp_path); d = example(); r.import_dataset(d)
    path = r.root / (d.identity + '.json')
    if mode == 'malformed': path.write_bytes(b'{"passwords":["PrivateSentinel"]}')
    if mode == 'digest':
        envelope = json.loads(path.read_bytes()); envelope['dataset']['source']['title'] = 'PrivateSentinel'; path.write_text(json.dumps(envelope))
    if mode == 'symlink':
        outside = tmp_path / 'private.json'; outside.write_bytes(path.read_bytes()); path.unlink(); path.symlink_to(outside)
    if mode == 'missing': path.unlink()
    if mode == 'directory-error':
        import os
        original = os.open
        def denied(value, *args, **kwargs):
            if value == 'frequencies': raise PermissionError('PrivateSentinel')
            return original(value, *args, **kwargs)
        monkeypatch.setattr(os, 'open', denied)
    with caplog.at_level(logging.DEBUG), TestClient(create_app(data_dir=tmp_path), raise_server_exceptions=False) as client:
        response = client.get('/frequencies/synthetic-a@1')
        assert response.status_code == 422 and 'PrivateSentinel' not in response.text + caplog.text
        assert response.headers['Cache-Control'] == 'no-store'
        assert translate('pt-BR', 'frequency.invalid') in response.text
        assert client.get('/api/jobs').json() == []
        assert not (tmp_path / 'uploads').exists()


def test_empty_registry_does_not_create_directory_and_translations_match(tmp_path):
    with TestClient(create_app(data_dir=tmp_path)) as client:
        response = client.get('/frequencies')
        assert response.status_code == 200 and translate('pt-BR','frequency.empty') in response.text
        assert not (tmp_path / 'frequencies').exists()
    assert TRANSLATIONS['en'].keys() == TRANSLATIONS['pt-BR'].keys()
    keys = [key for key in TRANSLATIONS['en'] if key.startswith('frequency.')]
    assert len(keys) >= 25 and all(TRANSLATIONS[locale][key] for locale in ('en','pt-BR') for key in keys)
