"""Real broker + HTTP demo check. Requires the Compose demo to be running."""
import json
import os
import sys
import threading
import time
from pathlib import Path

import httpx
import paho.mqtt.client as mqtt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from iot_shared.canonical import envelope, topic, validate  # noqa: E402

IDENTITY = {'inquilino': 'semob', 'site': 'centro', 'dominio': 'mobilidade',
            'dispositivo': 'semaforo-travessia-01'}


def wait_until(predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.1)
    raise AssertionError('Timed out waiting for MQTT/HTTP state')


def main():
    received = []
    errors = []
    connected = threading.Event()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(os.environ['MQTT_USERNAME'], os.environ['MQTT_PASSWORD'])

    def on_connect(client, userdata, flags, code, properties):
        if code != 0:
            errors.append(str(code))
            return
        for kind in ('telemetria', 'estado', 'evento'):
            client.subscribe('/'.join(IDENTITY.values()) + '/' + kind, qos=1)

    def on_subscribe(client, userdata, mid, codes, properties):
        if any(code.is_failure for code in codes):
            errors.append('Subscription rejected')
        connected.set()

    def on_message(client, userdata, message):
        try:
            received.append(validate(json.loads(message.payload)))
        except Exception as exc:
            errors.append(str(exc))

    def send(action, params=None):
        message = envelope(IDENTITY, 'comando', {'acao': action, 'parametros': params or {}})
        result = client.publish(topic(message), json.dumps(message), qos=1)
        result.wait_for_publish(timeout=5)
        assert result.is_published()
        return message

    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message
    client.connect(os.environ.get('MQTT_HOST', 'localhost'), int(os.environ.get('MQTT_PORT', '1883')))
    client.loop_start()
    try:
        assert connected.wait(10), 'MQTT subscription failed'
        with httpx.Client(base_url=os.environ.get('HTTP_URL', 'http://127.0.0.1:8000'), timeout=5) as http:
            send('stop')
            wait_until(lambda: not http.get('/api/state').json()['running'])
            send('config', {'wait': 1, 'crossing': 2, 'roi': [0, 0, 1, 1]})
            wait_until(lambda: http.get('/api/state').json()['wait_target'] == 1)
            sent = send('start')
            wait_until(lambda: http.get('/api/state').json()['running'])
            http.post('/api/control', json={'action': 'presence', 'presence': True}).raise_for_status()
            wait_until(lambda: http.get('/api/state').json()['phase'] == 'yellow')
            # Redelivery must not reset the active simulation.
            client.publish(topic(sent), json.dumps(sent), qos=1).wait_for_publish(timeout=5)
            time.sleep(.2)
            assert http.get('/api/state').json()['phase'] == 'yellow'
            wait_until(lambda: {'telemetria', 'evento', 'estado'} <= {m['tipo'] for m in received})
            assert not errors, errors
            assert any(m['tipo'] == 'evento' and m['dados']['destino'] == 'yellow' for m in received)
            for message in received:
                assert not {'frame', 'ids', 'boxes', 'imagem'} & message['dados'].keys()
            send('stop')
            wait_until(lambda: not http.get('/api/state').json()['running'])
        print('MQTT smoke passed: telemetry, events, state, commands and duplicate rejection')
    finally:
        client.disconnect()
        client.loop_stop()


if __name__ == '__main__':
    main()
