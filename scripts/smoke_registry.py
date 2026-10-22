"""Exercise the running registry and exported Mosquitto credentials (isolated test stack)."""
import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

import httpx
import paho.mqtt.client as mqtt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'platform/registry'))
from registry_service.broker import export  # noqa: E402
from registry_service.repository import Registry  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['provision', 'check', 'revoke', 'rejected'])
    parser.add_argument('--state', default='.runtime/registry-smoke.json')
    parser.add_argument('--broker-output', default='.runtime/registry-broker')
    args = parser.parse_args()
    path = Path(args.state)
    if args.action in ('provision', 'revoke'):
        administrator = json.loads(Path(os.environ['REGISTRY_ADMINS_FILE']).read_text(encoding='utf-8'))[0]
        with httpx.Client(base_url=os.environ.get('REGISTRY_HTTP_URL', 'http://127.0.0.1:8001'),
                          headers={'Authorization': 'Bearer ' + administrator['token']}, timeout=10) as client:
            if args.action == 'provision':
                suffix = uuid4().hex[:12]
                for route, body in [('sites', {'id': 'site-' + suffix, 'nome': 'Smoke site'}),
                                    ('sites/site-' + suffix + '/areas', {'id': 'area', 'nome': 'Area'})]:
                    response = client.post('/api/v1/' + route, json=body)
                    response.raise_for_status()
                response = client.post('/api/v1/dispositivos', json={
                    'id': 'device-' + suffix, 'nome': 'Smoke', 'site': 'site-' + suffix,
                    'area': 'area', 'perfil': 'semaforo-v1'})
                response.raise_for_status()
                data = response.json()
                data['inquilino'] = administrator['inquilino']
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(data), encoding='utf-8')
            else:
                data = json.loads(path.read_text(encoding='utf-8'))
                client.delete(f'/api/v1/dispositivos/{data["id"]}/credenciais').raise_for_status()
        export(Registry(os.environ.get('REGISTRY_DATABASE_URL', '')), args.broker_output)
        print('Provisioned and exported' if args.action == 'provision' else 'Revoked and exported; restart broker')
        return

    data = json.loads(path.read_text(encoding='utf-8'))
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)
    client.username_pw_set(data['credencial']['usuario'], data['credencial']['token'])
    connected = threading.Event()
    codes = []
    published = {}

    def on_connect(client, userdata, flags, code, properties):
        codes.append(code.value)
        connected.set()

    def on_publish(client, userdata, mid, code, properties):
        published[mid] = code.value

    client.on_connect = on_connect
    client.on_publish = on_publish
    client.connect(os.environ.get('REGISTRY_MQTT_HOST', '127.0.0.1'), int(os.environ.get('REGISTRY_MQTT_PORT', '1884')))
    client.loop_start()
    try:
        assert connected.wait(10), 'Connection timeout'
        if args.action == 'rejected':
            assert codes[0] != 0, 'Revoked token still accepted'
            print('Revoked credential rejected by real broker')
            return
        assert codes[0] == 0, codes
        own = client.publish(data['topico_base'] + '/telemetria', '{}', qos=1).mid
        foreign = client.publish('other/site/domain/device/telemetria', '{}', qos=1).mid
        command = client.publish(data['topico_base'] + '/comando', '{}', qos=1).mid
        deadline = time.monotonic() + 10
        while not {own, foreign, command} <= published.keys() and time.monotonic() < deadline:
            time.sleep(.05)
        assert published.get(own) in (0, 16), published
        assert published.get(foreign) == 135, published  # MQTT v5 Not authorized
        assert published.get(command) == 135, published
        print('Registry token accepted; foreign topics and command publication denied by real broker')
    finally:
        client.disconnect()
        client.loop_stop()


if __name__ == '__main__':
    main()
