"""Real HTTP -> JetStream -> TimescaleDB smoke (requires an isolated stack)."""
import json
import os
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from iot_shared.canonical import envelope  # noqa: E402


def wait_for(check, timeout=30):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        result = check()
        if result:
            return result
        time.sleep(.2)
    raise AssertionError('Timed out waiting for durable consumer')


def main():
    admin = json.loads(Path(os.environ['REGISTRY_ADMINS_FILE']).read_text(encoding='utf-8'))[0]
    identifier = 'smoke-' + uuid4().hex[:10]
    headers = {'Authorization': 'Bearer ' + admin['token']}
    with httpx.Client(base_url=os.environ.get('REGISTRY_URL', 'http://127.0.0.1:8001'), headers=headers) as registry:
        response = registry.post('/api/v1/sites', json={'id': identifier, 'nome': 'Smoke site'})
        response.raise_for_status()
        response = registry.post(f'/api/v1/sites/{identifier}/areas', json={'id': 'area', 'nome': 'Smoke area'})
        response.raise_for_status()
        response = registry.post('/api/v1/dispositivos', json={'id': identifier, 'nome': 'Smoke device',
                                 'site': identifier, 'area': 'area', 'perfil': 'semaforo-v1'})
        response.raise_for_status()
        device = response.json()
    identity = {'inquilino': admin['inquilino'], 'site': identifier, 'dominio': 'mobilidade', 'dispositivo': identifier}
    message = envelope(identity, 'telemetria', {'pedestres_na_area': {'valor': 8, 'unidade': '1'}})
    with httpx.Client(base_url=os.environ.get('DATA_URL', 'http://127.0.0.1:8003'), headers=headers) as data:
        response = data.post('/api/v1/regras', json={'id': identifier, 'dispositivo': identifier, 'tipo': 'limite',
                                                   'grandeza': 'pedestres_na_area', 'limite': 5})
        response.raise_for_status()
        with httpx.Client(base_url=os.environ.get('INGESTION_URL', 'http://127.0.0.1:8002'),
                          headers={'Authorization': 'Bearer ' + device['credencial']['token']}) as ingest:
            response = ingest.post('/api/v1/ingestao', json=message)
            assert response.status_code == 202, response.text
            assert ingest.post('/api/v1/ingestao', json=message).json()['status'] == 'duplicada'
        history = wait_for(lambda: data.get('/api/v1/telemetria', params={'dispositivo': identifier}).json()['items'])
        assert len(history) == 1 and history[0]['valor'] == 8
        alarms = wait_for(lambda: [item for item in data.get('/api/v1/alarmes').json()['items']
                                  if item['device'] == identifier])
        assert alarms[0]['status'] == 'ativo'
        state = data.get(f'/api/v1/dispositivos/{identifier}/ultimo-estado').json()
        assert state[0]['dados']['pedestres_na_area']['valor'] == 8
    print('HTTP -> durable outbox -> JetStream -> TimescaleDB -> rule alarm: OK; replay produced one reading.')


if __name__ == '__main__':
    main()
