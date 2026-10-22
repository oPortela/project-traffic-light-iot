from datetime import datetime, timedelta, timezone

import httpx
import pytest
from cryptography.fernet import Fernet, InvalidToken

from edge_service.queue import Queue
from edge_service.sync import synchronize
from iot_shared.canonical import envelope


def reading(index=0):
    return envelope({'inquilino': 'farm', 'site': 'field', 'dominio': 'agricultura', 'dispositivo': 'soil'},
                    'telemetria', {'umidade_solo': {'valor': 42, 'unidade': '%'}},
                    occurred_at=(datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(hours=index)).isoformat()
                    .replace('+00:00', 'Z'))


def test_encryption_commit_restart_capacity_and_dedup(tmp_path):
    key, path = Fernet.generate_key(), tmp_path / 'queue.db'
    queue = Queue(path, key, capacity=1)
    message = reading()
    assert queue.put('route', message)
    assert not queue.put('route', message)
    with pytest.raises(BufferError):
        queue.put('route', reading(1))
    assert b'umidade_solo' not in path.read_bytes()
    assert Queue(path, key).pending()[0]['message'] == message
    with pytest.raises(InvalidToken):
        Queue(path, Fernet.generate_key()).pending()
    message['dados']['umidade_solo']['valor'] = 43
    with pytest.raises(ValueError):
        queue.put('route', message)


def test_72_hours_disconnect_replay_and_lost_confirmation(tmp_path):
    clock = [0]
    queue = Queue(tmp_path / 'queue.db', Fernet.generate_key(), clock=lambda: clock[0])
    routes = {'route': {'token': 'device-token'}}
    for hour in range(72):
        queue.put('route', reading(hour))
        clock[0] += 3600
    assert queue.stats()['total'] == 72
    with httpx.Client(base_url='http://central', transport=httpx.MockTransport(
            lambda request: httpx.Response(503))) as client:
        assert synchronize(queue, routes, client) == 72
    assert queue.stats()['total'] == 72
    clock[0] += 301
    persisted = set()

    def receiver(request):
        import json
        messages = json.loads(request.content)['mensagens']
        results = []
        for index, message in enumerate(messages):
            identifier = message['id_mensagem']
            results.append({'indice': index, 'id_mensagem': identifier,
                            'status': 'duplicada' if identifier in persisted else 'aceita'})
            persisted.add(identifier)
        return httpx.Response(202, json={'resultados': results})

    def lost_response(request):
        receiver(request)
        raise httpx.ReadTimeout('ACK lost', request=request)

    with httpx.Client(base_url='http://central', transport=httpx.MockTransport(lost_response)) as client:
        synchronize(queue, routes, client)
    assert queue.stats()['total'] == 72 and len(persisted) == 72
    clock[0] += 301
    with httpx.Client(base_url='http://central', transport=httpx.MockTransport(receiver)) as client:
        synchronize(queue, routes, client)
    assert queue.stats()['total'] == 0 and len(persisted) == 72


def test_partial_confirmation_quarantine_and_bad_response(tmp_path):
    clock = [100]
    queue = Queue(tmp_path / 'queue.db', Fernet.generate_key(), clock=lambda: clock[0])
    for index in range(3):
        queue.put('route', reading(index))
    rows = queue.pending()
    results = [{'indice': 0, 'status': 'aceita', 'id_mensagem': rows[0]['id']},
               {'indice': 1, 'status': 'rejeitada', 'http_status': 400},
               {'indice': 2, 'status': 'rejeitada', 'http_status': 401}]
    with httpx.Client(base_url='http://central', transport=httpx.MockTransport(
            lambda request: httpx.Response(202, json={'resultados': results}))) as client:
        synchronize(queue, {'route': {'token': 'token'}}, client)
    assert queue.stats()['total'] == 2 and queue.stats()['quarentena'] == 1
    clock[0] += 301
    assert len(queue.pending()) == 1
    with httpx.Client(base_url='http://central', transport=httpx.MockTransport(
            lambda request: httpx.Response(202, json={'resultados': []}))) as client:
        synchronize(queue, {'route': {'token': 'token'}}, client)
    assert queue.stats()['total'] == 2
