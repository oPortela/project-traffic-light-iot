import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from ingestion_service.api import create_app
from ingestion_service.outbox import publish_pending
from ingestion_service.pipeline import Rejected
from iot_shared.canonical import envelope, topic


def message(tenant, now, value=1):
    return envelope({'inquilino': tenant, 'site': 'site', 'dominio': 'mobilidade', 'dispositivo': 'device'},
                    'telemetria', {'pedestres_na_area': {'valor': value, 'unidade': '1'}},
                    occurred_at=now.isoformat().replace('+00:00', 'Z'))


def test_state_profile_rejects_images_and_arbitrary_objects(ingested):
    repo, tenant, token, clock = ingested
    identity = {'inquilino': tenant, 'site': 'site', 'dominio': 'mobilidade', 'dispositivo': 'device'}
    for data in [{'imagem': 'base64-image'}, {'roi': {'faces': [1]}}, {'modo': 'person-name'}]:
        item = envelope(identity, 'estado', data, occurred_at=clock[0].isoformat().replace('+00:00', 'Z'))
        with pytest.raises(Rejected):
            repo.receive(item, token=token)
    item = envelope(identity, 'estado', {'modo': 'demo', 'roi': [0, 0, 1, 1]},
                    occurred_at=clock[0].isoformat().replace('+00:00', 'Z'))
    assert repo.receive(item, token=token)['status'] == 'aceita'


def test_durable_accept_dedup_late_and_suspect(ingested):
    repo, tenant, token, clock = ingested
    item = message(tenant, clock[0])
    assert repo.receive(item, token=token)['status'] == 'aceita'
    assert repo.receive(item, token=token)['status'] == 'duplicada'
    late = repo.receive(message(tenant, clock[0] - timedelta(seconds=60), 10001), token=token)
    assert late['atrasado']
    assert late['suspeitas'] == ['pedestres_na_area']
    assert repo.get_device(tenant, 'device')['status'] == 'online'
    with repo.connect() as conn:
        assert conn.execute('SELECT count(*) AS n FROM ingest_messages WHERE tenant=%s AND published_at IS NULL',
                            (tenant,)).fetchone()['n'] == 2


def test_concurrent_retries_only_create_one_message(ingested):
    repo, tenant, token, clock = ingested
    item = message(tenant, clock[0])
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: repo.receive(item, token=token)['status'], range(8)))
    assert results.count('aceita') == 1
    assert results.count('duplicada') == 7


def test_authentication_revocation_and_topic_binding(ingested):
    repo, tenant, token, clock = ingested
    item = message(tenant, clock[0])
    with pytest.raises(Rejected) as err:
        repo.receive(item, token='invalid')
    assert err.value.status == 401
    with pytest.raises(Rejected) as err:
        repo.receive(item, mqtt_topic=topic(item).replace('/site/', '/wrong/'))
    assert err.value.status == 403
    assert repo.receive(item, mqtt_topic=topic(item))['status'] == 'aceita'
    repo.revoke(tenant, 'device')
    with pytest.raises(Rejected):
        repo.receive(message(tenant, clock[0]), token=token)


def test_invalid_payload_has_dlq_reason_without_raw_data(ingested):
    repo, tenant, token, clock = ingested
    item = message(tenant, clock[0])
    item['dados'] = {'imagem': 'private-image-data'}
    with pytest.raises(Rejected):
        repo.receive(item, token=token)
    with repo.connect() as conn:
        row = conn.execute('SELECT * FROM ingest_dead_letters WHERE tenant=%s', (tenant,)).fetchone()
    assert row['errors'][0]['codigo'] == 'schema_invalido'
    assert 'private-image-data' not in str(row)


def test_id_conflict_and_future_date(ingested):
    repo, tenant, token, clock = ingested
    item = message(tenant, clock[0])
    repo.receive(item, token=token)
    item['dados']['pedestres_na_area']['valor'] = 2
    with pytest.raises(Rejected) as err:
        repo.receive(item, token=token)
    assert err.value.status == 409
    with pytest.raises(Rejected):
        repo.receive(message(tenant, clock[0] + timedelta(seconds=60)), token=token)


def test_batch_keeps_valid_items_when_others_fail(ingested):
    repo, tenant, token, clock = ingested
    messages = [message(tenant, clock[0]), {}, message(tenant, clock[0], 2), None]
    with TestClient(create_app(repo)) as client:
        assert client.post('/api/v1/ingestao', json=messages[0]).status_code == 401
        response = client.post('/api/v1/ingestao/lote', json={'mensagens': messages},
                               headers={'Authorization': 'Bearer ' + token})
        assert response.status_code == 202
        assert [r['status'] for r in response.json()['resultados']] == ['aceita', 'rejeitada', 'aceita', 'rejeitada']


def test_outbox_survives_nats_failure(ingested):
    repo, tenant, token, clock = ingested
    item = message(tenant, clock[0])
    repo.receive(item, token=token)
    failed = AsyncMock()
    failed.publish.side_effect = TimeoutError('NATS unavailable')
    with pytest.raises(TimeoutError):
        asyncio.run(publish_pending(repo, failed))
    successful = AsyncMock()
    assert asyncio.run(publish_pending(repo, successful)) >= 1
    calls = successful.publish.call_args_list
    assert any(call.kwargs['headers']['Nats-Msg-Id'] == tenant + ':' + item['id_mensagem'] for call in calls)
    with repo.connect() as conn:
        assert conn.execute('SELECT published_at FROM ingest_messages WHERE tenant=%s',
                            (tenant,)).fetchone()['published_at'] is not None
