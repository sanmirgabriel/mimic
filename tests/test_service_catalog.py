"""Evidence, association and offline behavior of the small service catalog."""
import csv
from dataclasses import FrozenInstanceError, replace
import io
import json

import pytest

from mimic.intelligence import catalog
from mimic.intelligence.builtins import SERVICE_PROFILES
from mimic.intelligence.models import DefaultCredential, ServiceKnowledge, CommonCredentialVocabulary
from mimic.cli import main


def test_catalog_identity_relationships_and_deterministic_order():
    catalog.validate_catalog()
    ids = ['wordpress', 'mysql', 'postgresql', 'mssql', 'windows-ad', 'grafana', 'rabbitmq']
    assert [s.id for s in catalog.list_services()] == ids
    assert [p.id for p in SERVICE_PROFILES] == ids
    assert [c.id for c in catalog.list_credentials()] == ['grafana-initial-admin', 'rabbitmq-initial-guest']
    for service in catalog.SERVICES:
        assert service.catalog_version == catalog.CATALOG_VERSION
        assert service.description and service.authentication_notes and service.references
        assert all(url.startswith('https://') for title, url in service.references)
    for credential in catalog.DEFAULT_CREDENTIALS:
        assert credential.type == 'documented_default'
        assert credential.source_title and credential.source_url and credential.applicability
        assert credential.restrictions and credential.record_version
        assert credential.service_id in ids
    assert catalog.common_vocabulary().type == 'common_value'


@pytest.mark.parametrize('service_id', ['wordpress', 'postgresql', 'mysql', 'mssql', 'windows-ad'])
def test_no_universal_default_pairs(service_id):
    assert catalog.list_credentials(service_id) == ()
    assert catalog.get_service(service_id).authentication_notes


def test_verified_initial_defaults_keep_conditions():
    grafana, = catalog.list_credentials('grafana')
    assert (grafana.username, grafana.password) == ('admin', 'admin')
    assert 'Initial' in grafana.applicability
    assert any('Custom configuration' in r for r in grafana.restrictions)
    assert any('password change' in r for r in grafana.restrictions)
    rabbitmq, = catalog.list_credentials('rabbitmq')
    assert (rabbitmq.username, rabbitmq.password) == ('guest', 'guest')
    assert 'blank broker' in rabbitmq.applicability
    assert any('localhost' in r for r in rabbitmq.restrictions)
    assert any('definitions' in r for r in rabbitmq.restrictions)
    assert 'OS user' in catalog.get_service('postgresql').authentication_notes
    assert 'choose' in catalog.get_service('wordpress').authentication_notes


@pytest.mark.parametrize('query,expected', [(' GrAfAnA ', ['grafana']), ('pgsql', ['postgresql']),
    ('AMQP', ['rabbitmq']), ('wp', ['wordpress']), ('no-such-service', [])])
def test_local_search(query, expected):
    assert [s.id for s in catalog.list_services(query)] == expected


def test_catalog_models_are_frozen_and_json_roundtrip():
    for value in (catalog.SERVICES[0], catalog.DEFAULT_CREDENTIALS[0], catalog.COMMON_VOCABULARY):
        with pytest.raises(FrozenInstanceError):
            value.id = 'changed'
        decoded = type(value)(**json.loads(json.dumps(value.to_dict())))
        assert decoded == value


@pytest.mark.parametrize('change', [dict(id='bad id'), dict(username=''), dict(source_title=''),
    dict(source_url='javascript:alert(1)'), dict(source_url='https://user:pass@example.test'),
    dict(applicability=''), dict(type='common_value'), dict(restrictions=()), dict(password='\ud800')],
    ids=['id', 'username', 'source-title', 'scheme', 'userinfo', 'condition', 'type', 'restrictions', 'unicode'])
def test_invalid_default_metadata_is_rejected(change):
    with pytest.raises((ValueError, TypeError)):
        replace(catalog.DEFAULT_CREDENTIALS[0], **change)


def test_duplicates_and_dangling_service_rejected():
    with pytest.raises(ValueError, match='duplicate service'):
        catalog.validate_catalog(catalog.SERVICES + (catalog.SERVICES[0],))
    with pytest.raises(ValueError, match='duplicate documented'):
        catalog.validate_catalog(credentials=catalog.DEFAULT_CREDENTIALS * 2)
    with pytest.raises(ValueError, match='duplicate documented'):
        catalog.validate_catalog(credentials=(catalog.DEFAULT_CREDENTIALS[0],
            replace(catalog.DEFAULT_CREDENTIALS[0], id='different-id')))
    with pytest.raises(ValueError, match='unknown service'):
        catalog.validate_catalog(credentials=(replace(catalog.DEFAULT_CREDENTIALS[0], service_id='missing'),))
    with pytest.raises(ValueError):
        replace(catalog.COMMON_VOCABULARY, passwords=('same', 'same'))


def test_documented_csv_keeps_pairs_and_restrictions():
    rows = list(csv.DictReader(io.StringIO(catalog.credentials_csv('rabbitmq'))))
    assert len(rows) == 1
    assert list(rows[0]) == ['service', 'username', 'password', 'type', 'source_url', 'applicability']
    assert rows[0]['username'] == rows[0]['password'] == 'guest'
    assert rows[0]['type'] == 'documented_default'
    assert 'localhost' in rows[0]['applicability'] and 'definitions' in rows[0]['applicability']
    assert list(csv.DictReader(io.StringIO(catalog.credentials_csv('wordpress')))) == []


def test_csv_quoting_and_spreadsheet_formula_safety():
    credential = replace(catalog.DEFAULT_CREDENTIALS[0], username='=1+1', password='comma,"quote"',
                         applicability='@formula', version_scope='Fixture scope')
    row, = list(csv.DictReader(io.StringIO(catalog._credential_rows_csv((credential,)))))
    assert row['username'] == "'=1+1"
    assert row['password'] == 'comma,"quote"'
    assert row['applicability'].startswith("'@formula")
    assert 'Fixture scope' in row['applicability']


def test_common_export_has_independent_lists_no_pairs():
    rows = list(csv.DictReader(io.StringIO(catalog.common_csv())))
    assert len(rows) == 12
    assert all(row['type'] == 'common_value' and 'service' not in row for row in rows)
    assert [r['value'] for r in rows if r['category'] == 'username'] == list(catalog.COMMON_VOCABULARY.usernames)
    assert [r['value'] for r in rows if r['category'] == 'password'] == list(catalog.COMMON_VOCABULARY.passwords)


def test_cli_services_and_defaults_share_catalog(capsys):
    assert main(['services', 'list']) == 0
    listing = capsys.readouterr().out
    assert all(s.id in listing for s in catalog.SERVICES)
    assert main(['services', 'show', 'grafana']) == 0
    details = capsys.readouterr().out
    assert 'Contextual tokens: grafana' in details and 'Documented defaults: 1' in details
    assert 'https://grafana.com/' in details and 'configured differently' in details
    assert main(['credentials', 'list', '--service', 'rabbitmq']) == 0
    listing = capsys.readouterr().out
    assert 'guest / guest (documented_default)' in listing and 'localhost' in listing
    assert main(['credentials', 'list', '--service', 'wordpress']) == 0
    assert capsys.readouterr().out.strip() == 'No documented default credentials in this catalog for this service.'
    assert main(['services', 'show', 'unknown']) == 1
    assert 'unknown service' in capsys.readouterr().err


def test_cli_common_and_exports_preserve_operator_files(tmp_path, capsys):
    assert main(['credentials', 'list', '--category', 'common']) == 0
    listing = capsys.readouterr().out
    assert 'Common usernames:' in listing and 'Common weak passwords:' in listing
    assert 'not prevalence statistics' in listing and 'root:welcome' not in listing
    path = tmp_path / 'defaults.csv'
    assert main(['credentials', 'export', '--service', 'grafana', '--format', 'csv', '--output', str(path)]) == 0
    assert path.read_text() == catalog.credentials_csv('grafana')
    original = path.read_bytes()
    assert main(['credentials', 'export', '--output', str(path)]) == 2
    assert path.read_bytes() == original
    assert main(['credentials', 'list', '--service', 'grafana', '--category', 'common']) == 1
    common = tmp_path / 'common.csv'
    assert main(['credentials', 'export', '--category', 'common', '--output', str(common)]) == 0
    assert common.read_text() == catalog.common_csv()
