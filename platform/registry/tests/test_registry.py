import json
from datetime import timedelta

import pytest

from registry_service.broker import export


def post(client, path, payload, expected=201, **kwargs):
    response = client.post('/api/v1/' + path, json=payload, **kwargs)
    assert response.status_code == expected, response.text
    return response.json()


def device(client, name='semaforo-01', profile='semaforo-v1'):
    post(client, 'sites', {'id': 'centro', 'nome': 'Centro'})
    post(client, 'sites/centro/areas', {'id': 'praca', 'nome': 'Praça'})
    return post(client, 'dispositivos', {'id': name, 'nome': 'Travessia', 'site': 'centro',
                                       'area': 'praca', 'perfil': profile})


def test_registry_flow_and_secret_hygiene(setup):
    client, repo, tenant, other, other_headers = setup
    domains = client.get('/api/v1/catalogo/dominios').json()
    assert {d['id'] for d in domains['items']} == {'agricultura', 'mobilidade'}
    created = device(client)
    assert created['status'] == 'offline'
    assert created['topico_base'] == f'{tenant}/centro/mobilidade/semaforo-01'
    assert len(created['credencial']['token']) >= 32
    for path in ['/api/v1/dispositivos', '/api/v1/dispositivos/semaforo-01']:
        response = client.get(path)
        assert response.status_code == 200
        assert 'token' not in response.text and 'mqtt_hash' not in response.text
        assert response.headers['cache-control'] == 'no-store'
    with repo.connect() as conn:
        row = conn.execute('SELECT token_digest,mqtt_hash FROM registry_devices WHERE tenant=%s', (tenant,)).fetchone()
    assert created['credencial']['token'] not in json.dumps(row)
    assert row['mqtt_hash'].startswith('$7$100000$')
    assert client.get('/api/v1/dispositivos/semaforo-01', headers=other_headers).status_code == 404
    assert client.get('/api/v1/dispositivos', headers=other_headers).json()['items'] == []


def test_tenant_scoped_foreign_keys_and_duplicate_ids(setup):
    client, repo, tenant, other, other_headers = setup
    device(client)
    post(client, 'dispositivos', {'id': 'foreign', 'nome': 'Other', 'site': 'centro',
                                 'area': 'praca', 'perfil': 'semaforo-v1'}, expected=422, headers=other_headers)
    post(client, 'sites', {'id': 'centro', 'nome': 'Duplicate'}, expected=409)
    post(client, 'sites', {'id': 'centro', 'nome': 'Allowed in other tenant'}, headers=other_headers)
    assert client.delete('/api/v1/dispositivos/semaforo-01/credenciais', headers=other_headers).status_code == 404
    assert not client.get('/api/v1/dispositivos/semaforo-01').json()['credencial_revogada']


def test_profile_driven_online_status_and_revocation(setup):
    client, repo, tenant, other, other_headers = setup
    created = device(client, profile='solo-horario-v1')
    auth = {'Authorization': 'Bearer ' + created['credencial']['token']}
    path = '/api/v1/dispositivos/semaforo-01/heartbeat'
    assert client.post(path, params={'inquilino': other}, headers=auth).status_code == 401
    assert client.post(path, params={'inquilino': tenant}, headers=auth).status_code == 204
    repo.test_now[0] += timedelta(minutes=6)
    assert client.get('/api/v1/dispositivos/semaforo-01').json()['status'] == 'online'
    repo.test_now[0] += timedelta(hours=3)
    assert client.get('/api/v1/dispositivos/semaforo-01').json()['status'] == 'offline'
    assert client.post(path, params={'inquilino': tenant}, headers=auth).status_code == 204
    assert client.delete('/api/v1/dispositivos/semaforo-01/credenciais').json()['revogado']
    assert client.delete('/api/v1/dispositivos/semaforo-01/credenciais').status_code == 200
    assert client.post(path, params={'inquilino': tenant}, headers=auth).status_code == 401
    assert client.get('/api/v1/dispositivos/semaforo-01').json()['status'] == 'offline'


def test_new_domain_without_code_change_and_pagination(setup):
    client, repo, tenant, other, other_headers = setup
    post(client, 'catalogo/dominios', {'id': 'recursos_hidricos', 'nome': 'Água'})
    post(client, 'perfis', {'id': 'nivel', 'nome': 'Nível', 'dominio': 'recursos_hidricos',
                          'intervalo_esperado_s': 900, 'grandezas': {'nivel': {'unidade': 'm', 'minimo': 0, 'maximo': 20}}})
    created = device(client, profile='nivel')
    assert created['dominio'] == 'recursos_hidricos'
    for i in range(3):
        post(client, 'sites', {'id': f'local-{i}', 'nome': 'Irrigação'})
    first = client.get('/api/v1/sites', params={'size': 2, 'sort': 'nome', 'filter': 'Irrigação'}).json()
    second = client.get('/api/v1/sites', params={'size': 2, 'page': 2, 'sort': 'nome', 'filter': 'Irrigação'}).json()
    assert first['total'] == 3
    assert len(first['items']) == 2 and len(second['items']) == 1
    assert {x['id'] for x in first['items']}.isdisjoint({x['id'] for x in second['items']})
    assert client.get('/api/v1/sites', params={'sort': 'id; DROP TABLE registry_sites'}).status_code == 422
    assert client.get('/api/v1/sites', params={'size': 201}).status_code == 422
    assert client.get('/api/v1/sites/centro/areas').json()['total'] == 1


@pytest.mark.parametrize('change', [
    {'intervalo_esperado_s': 0}, {'grandezas': {}}, {'grandezas': {'a': {'unidade': 'bananas', 'minimo': 0, 'maximo': 1}}},
    {'grandezas': {'a': {'unidade': 'm', 'minimo': 10, 'maximo': 1}}}, {'dominio': 'missing'}, {'id': 'a/#'},
])
def test_invalid_profiles(setup, change):
    client, *_ = setup
    model = {'id': 'invalid', 'nome': 'Invalid', 'dominio': 'mobilidade', 'intervalo_esperado_s': 5,
             'grandezas': {'a': {'unidade': '1', 'minimo': 0, 'maximo': 1}}}
    post(client, 'perfis', model | change, expected=422)


def test_authentication_and_injected_tenant(setup):
    client, *_ = setup
    assert client.get('/api/v1/sites', headers={'Authorization': ''}).status_code == 401
    assert client.get('/api/v1/sites', headers={'Authorization': 'Bearer wrong'}).status_code == 401
    post(client, 'sites', {'id': 'site', 'nome': 'Site', 'inquilino': 'another'}, expected=422)


def test_export_and_revocation(setup, tmp_path):
    client, repo, tenant, *_ = setup
    created = device(client)
    generation = export(repo, tmp_path)
    acl = (tmp_path / generation / 'acl').read_text()
    password = (tmp_path / generation / 'passwords').read_text()
    assert f'topic write {tenant}/centro/mobilidade/semaforo-01/telemetria' in acl
    assert f'topic read {tenant}/centro/mobilidade/semaforo-01/comando' in acl
    assert created['credencial']['usuario'] in password
    assert created['credencial']['token'] not in password
    client.delete('/api/v1/dispositivos/semaforo-01/credenciais')
    revoked = export(repo, tmp_path)
    assert created['credencial']['usuario'] not in (tmp_path / revoked / 'passwords').read_text()
    assert 'topic deny #' in (tmp_path / revoked / 'acl').read_text()
    assert revoked in (tmp_path / 'active.conf').read_text()


def test_restart_preserves_state_and_seed_is_idempotent(setup):
    client, repo, tenant, other, _ = setup
    created = device(client)
    from registry_service.api import DEFAULT_SEED
    from registry_service.repository import Registry
    restarted = Registry(repo.dsn)
    restarted.initialize([tenant, other], DEFAULT_SEED)
    assert restarted.get_device(tenant, created['id'])['mqtt_username'] == created['mqtt_username']
    assert restarted.listing(tenant, 'dominios', 1, 10, 'id', '')['total'] == 2
