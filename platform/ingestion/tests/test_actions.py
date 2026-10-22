from datetime import timedelta
from unittest.mock import Mock

import pytest
from psycopg.types.json import Jsonb

from ingestion_service.actions import dispatch_once, validate_action
from ingestion_service.rules import Action, Rule
from test_storage import prepare, save


def test_action_retry_and_delivery_are_durable(ingested, monkeypatch):
    store, tenant, token, clock = prepare(ingested)
    monkeypatch.setenv('WEBHOOK_ALLOWED_HOSTS', 'receiver.test')
    rule = Rule(id='notify', dispositivo='device', tipo='limite', grandeza='pedestres_na_area', limite=5,
                acoes=[Action(tipo='webhook', destino='https://receiver.test/events')])
    with store.connect() as conn:
        conn.execute('INSERT INTO processing_rules (tenant,id,device,definition,created_at) VALUES (%s,%s,%s,%s,%s)',
                     (tenant, rule.id, 'device', Jsonb(rule.model_dump()), clock[0]))
    save(store, tenant, token, clock[0], 9)
    send = Mock(side_effect=TimeoutError('do not persist this sensitive response'))
    assert dispatch_once(store, {'webhook': send}) == 1
    assert dispatch_once(store, {'webhook': send}) == 0
    with store.connect() as conn:
        row = conn.execute('SELECT * FROM processing_actions WHERE alarm_id IN '
                           '(SELECT id FROM processing_alarms WHERE tenant=%s)', (tenant,)).fetchone()
        assert row['attempts'] == 1 and row['last_error'] == 'TimeoutError'
        assert row['delivered_at'] is None
    clock[0] += timedelta(seconds=3)
    send.side_effect = None
    assert dispatch_once(store, {'webhook': send}) == 1
    assert dispatch_once(store, {'webhook': send}) == 0
    assert send.call_count == 2
    assert send.call_args.args[1]['inquilino'] == tenant


def test_action_destinations_are_scoped(monkeypatch):
    monkeypatch.setenv('WEBHOOK_ALLOWED_HOSTS', 'receiver.test')
    validate_action({'tipo': 'webhook', 'destino': 'https://receiver.test/events'}, 't', 'd')
    validate_action({'tipo': 'topico', 'destino': 'acoes/t/d/event'}, 't', 'd')
    for action in [{'tipo': 'webhook', 'destino': 'http://127.0.0.1/admin'},
                   {'tipo': 'webhook', 'destino': 'https://user:pass@receiver.test'},
                   {'tipo': 'topico', 'destino': 'acoes/other/d/event'},
                   {'tipo': 'topico', 'destino': 'acoes/t/d/#'}]:
        with pytest.raises(ValueError):
            validate_action(action, 't', 'd')
