"""Independent Gate 14 regressions: descriptor ownership and atomic publication."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import errno
import os
from pathlib import Path
import threading

import pytest

from mimic.cli import main
from mimic.intelligence import catalog
from mimic.application import GenerationRequest, GenerationService
from fastapi.testclient import TestClient
from mimic.api import create_app


@pytest.mark.parametrize('failure', ['open', 'write', 'fsync', 'publish', None])
def test_csv_descriptor_and_staging_cleanup_at_every_boundary(tmp_path, monkeypatch, failure):
    import mimic.cli as cli

    descriptors = []
    original_open = os.fdopen
    original_mkstemp = cli.tempfile.mkstemp

    def capture(*args, **kwargs):
        descriptor, name = original_mkstemp(*args, **kwargs)
        descriptors.append(descriptor)
        return descriptor, name

    def fail(*args, **kwargs):
        raise OSError('Gate 14 simulated ' + str(failure) + ' failure')

    class FailedWrite:
        def __init__(self, stream): self.stream = stream
        def __enter__(self): return self
        def __exit__(self, *args): return self.stream.__exit__(*args)
        def write(self, value):
            self.stream.write(value[:11])
            self.stream.flush()
            fail()

    monkeypatch.setattr(cli.tempfile, 'mkstemp', capture)
    if failure == 'open':
        monkeypatch.setattr(cli.os, 'fdopen', fail)
    elif failure == 'write':
        monkeypatch.setattr(cli.os, 'fdopen', lambda *a, **kw: FailedWrite(original_open(*a, **kw)))
    elif failure == 'fsync':
        monkeypatch.setattr(cli.os, 'fsync', fail)
    elif failure == 'publish':
        monkeypatch.setattr(cli.os, 'link', fail)

    destination = tmp_path / 'catalog.csv'
    assert main(['credentials', 'export', '--output', str(destination)]) == (0 if failure is None else 2)
    leaked = []
    for descriptor in descriptors:
        try:
            os.fstat(descriptor)
        except OSError as error:
            assert error.errno == errno.EBADF
        else:
            leaked.append(descriptor)
            os.close(descriptor)  # Keep the failing-before reproduction isolated.
    assert not leaked, 'CSV export leaked its raw file descriptor'
    assert not list(tmp_path.glob('.mimic-catalog-*.part'))
    if failure is None:
        assert destination.read_bytes() == catalog.credentials_csv().encode()
    else:
        assert not destination.exists()


def test_csv_two_real_writers_publish_one_complete_file(tmp_path, monkeypatch):
    barrier = threading.Barrier(2)
    original_link = os.link

    def synchronized_link(source, target):
        barrier.wait(timeout=10)
        return original_link(source, target)

    monkeypatch.setattr(os, 'link', synchronized_link)
    destination = tmp_path / 'catalog.csv'
    with ThreadPoolExecutor(max_workers=2) as workers:
        statuses = list(workers.map(lambda _: main(['credentials', 'export', '--output', str(destination)]), range(2)))
    assert sorted(statuses) == [0, 2]
    assert destination.read_bytes() == catalog.credentials_csv().encode()
    assert list(tmp_path.iterdir()) == [destination]


@pytest.mark.parametrize('value', [None, 7, {}, [], '', ' ', 'x'*4097, '\udfff',
    'line\nbreak', '\u202evalue', 'x\x7f', 'x\u0085'])
@pytest.mark.parametrize('field', ['version_scope', 'password', 'applicability'])
def test_new_pair_metadata_adversarial_types_and_text(field, value):
    # A missing scope is legal at the model level for historical records, but
    # catalog validation requires one for the new revision's documented pairs.
    with pytest.raises((ValueError, TypeError)):
        changed = replace(catalog.DEFAULT_CREDENTIALS[2], **{field:value})
        catalog.validate_catalog(credentials=(changed,))


@pytest.mark.parametrize('url', ['http://docs.example.org', 'https://user@docs.example.org',
    'https://docs..example.org', 'https://docs.example.org:65536',
    'https://docs.example.org/\npath', 'javascript:alert(1)', None, 42])
def test_new_pair_documentation_url_is_not_executable_or_malformed(url):
    with pytest.raises((ValueError, TypeError)):
        replace(catalog.DEFAULT_CREDENTIALS[2], source_url=url)


@pytest.mark.parametrize('service,organization,corporate', [
    (None,True,False), ('wordpress',True,False), ('zabbix',True,False),
    ('zabbix',False,False), (None,True,True), ('zabbix',True,True)])
def test_passive_pair_fixture_cannot_change_any_generation_context(monkeypatch, service, organization, corporate):
    data={'intelligence':{'reference_year':2026,'service_profiles':[service] if service else []},
        'mutations':{'leet_mode':'none','separators':'!'},
        'limits':{'max_candidates_per_word':10},'ranking':{'enabled':True,'budget':20}}
    if organization:data['organization']={'name':'Synthetic'}
    if corporate:data['preset']='corporate-br'
    request=GenerationRequest.from_dict(data)
    expected=[r.to_dict() for r in GenerationService().prepare(request).iter_results()]
    fixture=replace(catalog.DEFAULT_CREDENTIALS[2], username='Gate14OnlyUsername',
        password='Gate14OnlyPassword')
    monkeypatch.setattr(catalog,'DEFAULT_CREDENTIALS',(fixture,))
    def forbidden(*args,**kwargs):raise AssertionError('Passive credential adapter consulted')
    monkeypatch.setattr(catalog,'list_credentials',forbidden)
    results=[r.to_dict() for r in GenerationService().prepare(request).iter_results()]
    assert results==expected
    assert 'Gate14OnlyPassword' not in repr(results) and 'Gate14OnlyUsername' not in repr(results)
    if not service:
        assert not any(o['field'].startswith('service.') for r in results for o in r['candidate']['origins'])


def test_commented_accounts_and_unassociated_common_values_are_not_pairs():
    for service in ('jenkins','tomcat','redis','opensearch'):
        assert catalog.list_credentials(service)==()
        assert catalog.get_service(service) in catalog.list_services(service)
    assert not any(c.service_id=='tomcat' and c.username in ('tomcat','both','role1','admin')
        for c in catalog.DEFAULT_CREDENTIALS)
    assert not any(c.service_id=='redis' and c.username=='default' for c in catalog.DEFAULT_CREDENTIALS)
    assert catalog.common_vocabulary().passwords==('admin','password','changeme','welcome','123456','mudar')


def test_new_service_and_pair_html_remain_text(tmp_path, monkeypatch):
    hostile='\"><img src=x onerror=window.GATE14_XSS=1>'
    original=catalog.get_service
    service=replace(original('zabbix'),aliases=(hostile,),display_name=hostile)
    credential=replace(catalog.DEFAULT_CREDENTIALS[2],username=hostile,password=hostile)
    monkeypatch.setattr(catalog,'get_service',lambda identity, **kw: service if identity=='zabbix' else original(identity,**kw))
    monkeypatch.setattr(catalog,'list_credentials',lambda identity=None, **kw:(credential,) if identity=='zabbix' else ())
    with TestClient(create_app(data_dir=tmp_path)) as client:
        response=client.get('/services/zabbix')
        assert response.status_code==200
        assert hostile not in response.text
        assert '&lt;img src=x onerror=window.GATE14_XSS=1&gt;' in response.text
        assert "default-src 'self'" in response.headers['Content-Security-Policy']
        assert client.get('/services',params={'q':'x'*201}).status_code==422
        assert client.post('/generate',data={'service_profiles':'zabbix','intent':'preview'}).status_code==403
