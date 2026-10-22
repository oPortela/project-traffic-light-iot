"""Rural canonical telemetry through the local broker."""
import json
import os
import random
import time
import threading
from pathlib import Path

import paho.mqtt.client as mqtt

from iot_shared.canonical import envelope, topic


def main():
    config = json.loads(Path(os.environ['SOIL_CONFIG_FILE']).read_text(encoding='utf-8'))
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='soil-simulator')
    client.username_pw_set(config['usuario'], config['token'])
    ready, acknowledged = threading.Event(), threading.Event()
    pending = [None]
    base = '/'.join(config['identidade'][key] for key in ('inquilino', 'site', 'dominio', 'dispositivo'))

    def connected(client, userdata, flags, reason, properties):
        if not reason.is_failure:
            client.subscribe(base + '/confirmacao', qos=1)

    def confirmed(client, userdata, incoming):
        confirmation = json.loads(incoming.payload)
        if confirmation.get('id_mensagem') == pending[0] and confirmation.get('status') == 'persistida':
            acknowledged.set()

    client.on_connect = connected
    client.on_subscribe = lambda *args: ready.set()
    client.on_message = confirmed
    client.connect(os.environ.get('MQTT_HOST', 'edge-mosquitto'), int(os.environ.get('MQTT_PORT', '1883')))
    client.loop_start()
    try:
        if not ready.wait(30):
            raise TimeoutError('Local broker did not establish acknowledgment subscription')
        while True:
            message = envelope(config['identidade'], 'telemetria', {
                'umidade_solo': {'valor': round(random.uniform(20, 80), 2), 'unidade': '%'},
                'temperatura_solo': {'valor': round(random.uniform(18, 35), 2), 'unidade': 'Cel'}})
            pending[0] = message['id_mensagem']
            acknowledged.clear()
            while not acknowledged.is_set():
                client.publish(topic(message), json.dumps(message), qos=1)
                acknowledged.wait(10)
            time.sleep(float(os.environ.get('SOIL_INTERVAL_S', '3600')))
    finally:
        client.disconnect()
        client.loop_stop()


if __name__ == '__main__':
    main()
