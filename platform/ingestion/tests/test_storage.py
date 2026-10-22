from datetime import timedelta

from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from ingestion_service.query_api import create_app
from ingestion_service.rules import Rule, evaluate_absence
from ingestion_service.storage import Storage
from registry_service.security import Administrators
from test_ingestion import message


def prepare(ingested):
    repo, tenant, token, clock = ingested
    store = Storage(repo.dsn, clock=repo.clock)
    store.initialize_storage()
    return store, tenant, token, clock


def save(store, tenant, token, timestamp, value):
    item = message(tenant, timestamp, value)
    store.receive(item, token=token)
    store.persist(tenant, item['id_mensagem'])
    return item


def test_storage_idempotency_late_history_and_tenant_queries(ingested):
    store, tenant, token, clock = prepare(ingested)
    admins = Administrators([{'inquilino': tenant, 'token': 'a'*40}, {'inquilino': 'other', 'token': 'b'*40}])
    current = save(store, tenant, token, clock[0], 2)
    assert not store.persist(tenant, current['id_mensagem'])
    save(store, tenant, token, clock[0] - timedelta(minutes=1), 1)
    with TestClient(create_app(store, admins)) as client:
        headers = {'Authorization': 'Bearer ' + 'a'*40}
        assert client.get('/api/v1/telemetria').status_code == 401
        history = client.get('/api/v1/telemetria', headers=headers).json()
        assert history['total'] == 2
        assert history['items'][1]['flags']['atrasado']
        state = client.get('/api/v1/dispositivos/device/ultimo-estado', headers=headers).json()
        assert state[0]['dados']['pedestres_na_area']['valor'] == 2
        assert client.get('/api/v1/telemetria', headers={'Authorization': 'Bearer ' + 'b'*40}).json()['total'] == 0


def test_limit_alarm_lifecycle_ignores_late_and_suspect(ingested):
    store, tenant, token, clock = prepare(ingested)
    admins = Administrators([{'inquilino': tenant, 'token': 'a'*40}])
    with TestClient(create_app(store, admins)) as client:
        client.headers['Authorization'] = 'Bearer ' + 'a'*40
        response = client.post('/api/v1/regras', json={'id': 'busy', 'dispositivo': 'device', 'tipo': 'limite',
                                                     'grandeza': 'pedestres_na_area', 'limite': 5})
        assert response.status_code == 201
        save(store, tenant, token, clock[0] - timedelta(minutes=1), 9)
        save(store, tenant, token, clock[0], 10001)
        assert client.get('/api/v1/alarmes').json()['total'] == 0
        clock[0] += timedelta(seconds=1)
        save(store, tenant, token, clock[0], 8)
        alarms = client.get('/api/v1/alarmes').json()['items']
        assert len(alarms) == 1 and alarms[0]['status'] == 'ativo'
        identifier = alarms[0]['id']
        assert client.post(f'/api/v1/alarmes/{identifier}/reconhecer').status_code == 200
        clock[0] += timedelta(seconds=1)
        save(store, tenant, token, clock[0], 9)
        assert client.get('/api/v1/alarmes').json()['total'] == 1
        clock[0] += timedelta(seconds=1)
        save(store, tenant, token, clock[0], 1)
        assert client.get('/api/v1/alarmes').json()['items'][0]['status'] == 'resolvido'


def test_absence_and_window_rules(ingested):
    store, tenant, token, clock = prepare(ingested)
    with store.connect() as conn:
        for model in [Rule(id='silent', dispositivo='device', tipo='ausencia', janela_s=10),
                      Rule(id='average', dispositivo='device', tipo='janela', grandeza='pedestres_na_area', limite=5)]:
            conn.execute('INSERT INTO processing_rules (tenant,id,device,definition,created_at) VALUES (%s,%s,%s,%s,%s)',
                         (tenant, model.id, 'device', Jsonb(model.model_dump()), clock[0]))
    save(store, tenant, token, clock[0], 8)
    clock[0] += timedelta(seconds=11)
    evaluate_absence(store)
    with store.connect() as conn:
        alarms = conn.execute('SELECT rule_id FROM processing_alarms WHERE tenant=%s', (tenant,)).fetchall()
    assert {row['rule_id'] for row in alarms} == {'silent', 'average'}
