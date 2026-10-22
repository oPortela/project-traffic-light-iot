"""Publish one canonical reading and verify its exact ID in central history."""
import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path

import httpx
import paho.mqtt.client as mqtt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from iot_shared.canonical import envelope, topic  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device-file', required=True)
    parser.add_argument('--mqtt-port', type=int, default=1885)
    parser.add_argument('--expect-edge', action='store_true')
    args = parser.parse_args()
    device = json.loads(Path(args.device_file).read_text(encoding='utf-8'))
    admin = json.loads(Path(os.environ['REGISTRY_ADMINS_FILE']).read_text(encoding='utf-8'))[0]
    tenant, site, domain, identifier = device['topico_base'].split('/')
    message = envelope({'inquilino': tenant, 'site': site, 'dominio': domain, 'dispositivo': identifier},
                       'telemetria', {'umidade_solo': {'valor': 42, 'unidade': '%'}})
    ready, ack = threading.Event(), threading.Event()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(device['credencial']['usuario'], device['credencial']['token'])

    def connected(client, userdata, flags, reason, properties):
        if reason.is_failure:
            return
        if args.expect_edge:
            client.subscribe(device['topico_base'] + '/confirmacao', qos=1)
        else:
            ready.set()

    def received(client, userdata, incoming):
        confirmation = json.loads(incoming.payload)
        if confirmation.get('id_mensagem') == message['id_mensagem']:
            ack.set()

    client.on_connect, client.on_message = connected, received
    client.on_subscribe = lambda *args: ready.set()
    client.connect('127.0.0.1', args.mqtt_port)
    client.loop_start()
    try:
        assert ready.wait(10), 'MQTT connection/subscription failed'
        for _ in range(2):
            published = client.publish(topic(message), json.dumps(message), qos=1)
            published.wait_for_publish(10)
            assert published.is_published()
        if args.expect_edge:
            assert ack.wait(15), 'Edge did not confirm SQLite commit'
    finally:
        client.disconnect()
        client.loop_stop()
    with httpx.Client(base_url=os.environ.get('DATA_URL', 'http://127.0.0.1:8003'),
                      headers={'Authorization': 'Bearer ' + admin['token']}) as data:
        end = time.monotonic() + 30
        while time.monotonic() < end:
            response = data.get('/api/v1/telemetria', params={'dispositivo': identifier, 'size': 200})
            response.raise_for_status()
            items = [item for item in response.json()['items'] if item['id_mensagem'] == message['id_mensagem']]
            if items:
                assert len(items) == 1 and items[0]['valor'] == 42
                print('MQTT delivery, central persistence and replay deduplication: OK')
                return
            time.sleep(.2)
    raise AssertionError('Reading did not reach the central history')


if __name__ == '__main__':
    main()
