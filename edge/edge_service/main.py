"""Persistent MQTT session, manual QoS1 ACK and independent HTTP sync loop."""
import json
import logging
import os
import threading
import time
from pathlib import Path

import httpx
import paho.mqtt.client as mqtt

from iot_shared.canonical import topic
from iot_shared.observability import worker_metrics, EDGE_DEPTH, EDGE_AGE
from .queue import Queue
from .sync import synchronize
from .rules import Rules


def main():
    worker_metrics()
    config = json.loads(Path(os.environ['EDGE_CONFIG_FILE']).read_text(encoding='utf-8'))
    queue = Queue(os.environ.get('EDGE_DATABASE', '/data/queue.db'),
                  Path(os.environ['EDGE_KEY_FILE']).read_bytes().strip())
    routes = config['dispositivos']
    rules = Rules(queue)
    for route, settings in routes.items():
        if settings.get('regras'):
            rules.configure(route, settings.get('revisao', 1), settings['regras'])
    credentials = config['mqtt']
    stop = threading.Event()

    def sync_loop():
        with httpx.Client(base_url=config['central'], timeout=15, follow_redirects=False) as client:
            while not stop.is_set():
                try:
                    synchronize(queue, routes, client)
                    stats = queue.stats()
                    EDGE_DEPTH.set(stats['total'])
                    EDGE_AGE.set(stats['idade_mais_antiga_s'])
                except Exception:
                    logging.exception('Edge sync failed; queue retained')
                stop.wait(1)

    worker = threading.Thread(target=sync_loop, daemon=True)
    worker.start()
    try:
        while not stop.is_set():
            awaiting = {}
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=config['id'],
                                 clean_session=False, manual_ack=True)
            client.username_pw_set(credentials['usuario'], credentials['token'])

            def connected(client, userdata, flags, reason, properties):
                if not reason.is_failure:
                    for base in routes:
                        for kind in ('telemetria', 'evento', 'estado'):
                            client.subscribe(base + '/' + kind, qos=1)
                    publish_commands(client)

            def publish_commands(client):
                for command in rules.commands():
                    if command['id'] not in awaiting.values():
                        sent = client.publish(command['route'] + '/comando', json.dumps(command['message']), qos=1)
                        awaiting[sent.mid] = command['id']

            def published(client, userdata, mid, reason, properties):
                if mid in awaiting and not reason.is_failure:
                    rules.confirm_command(awaiting.pop(mid))

            def received(client, userdata, incoming):
                # Unexpected payloads stay at the broker for operator correction; never silently discard.
                message = json.loads(incoming.payload)
                base = incoming.topic.rsplit('/', 1)[0]
                if base not in routes or topic(message) != incoming.topic or message['tipo'] == 'comando':
                    raise ValueError('MQTT identity mismatch')
                rules.receive(base, message)
                publish_commands(client)
                # PUBACK from Mosquitto alone is not proof of SQLite commit.
                client.publish(base + '/confirmacao', json.dumps({'id_mensagem': message['id_mensagem'],
                                                                 'status': 'persistida'}), qos=1)
                client.ack(incoming.mid, incoming.qos)

            client.on_connect, client.on_message = connected, received
            client.on_publish = published
            try:
                client.connect(os.environ.get('MQTT_HOST', 'edge-mosquitto'),
                               int(os.environ.get('MQTT_PORT', '1883')), 30)
                client.loop_forever(retry_first_connection=True)
            except Exception:
                logging.exception('Edge receive failed before ACK; retrying persistent session')
            finally:
                client.disconnect()
            time.sleep(2)
    finally:
        stop.set()
        worker.join(timeout=20)


if __name__ == '__main__':
    main()
