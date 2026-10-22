from datetime import timedelta
from unittest.mock import Mock

import pytest

from ingestion_service.twins import set_desired, get_twin, dispatch_twins
from iot_shared.canonical import envelope
from test_storage import prepare


def test_desired_retry_report_convergence_and_local_drift(ingested):
    store, tenant, token, clock = prepare(ingested)
    set_desired(store, tenant, 'device', {'wait': 15})
    send = Mock()
    assert get_twin(store, tenant, 'device')['pendente']
    assert dispatch_twins(store, send) == 1
    first = send.call_args.args[0]
    assert first['action']['dados']['parametros'] == {'wait': 15}
    assert dispatch_twins(store, send) == 0
    clock[0] += timedelta(seconds=31)
    assert dispatch_twins(store, send) == 1
    assert send.call_args.args[0]['id'] == first['id']

    def report(value):
        clock[0] += timedelta(seconds=31)
        item = envelope({'inquilino': tenant, 'site': 'site', 'dominio': 'mobilidade', 'dispositivo': 'device'},
                        'estado', {'wait': value}, occurred_at=clock[0].isoformat().replace('+00:00', 'Z'))
        store.receive(item, token=token)
        store.persist(tenant, item['id_mensagem'])

    report(15)
    assert not get_twin(store, tenant, 'device')['pendente']
    assert dispatch_twins(store, send) == 0
    report(10)
    assert dispatch_twins(store, send) == 1
    assert send.call_args.args[0]['id'] != first['id']


def test_desired_limits_and_tenant_isolation(ingested):
    store, tenant, token, clock = prepare(ingested)
    for invalid in [{}, {'wait': -1}, {'wait': float('nan')}, {'modo': 'demo'}, {'roi': [1, 0, 0, 1]}]:
        with pytest.raises(ValueError):
            set_desired(store, tenant, 'device', invalid)
    with pytest.raises(LookupError):
        set_desired(store, 'other', 'device', {'wait': 15})
