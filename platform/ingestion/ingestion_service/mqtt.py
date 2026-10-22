"""Trusted Mosquitto bridge: QoS 1 ACK only after durable accept or durable rejection."""
import json
import logging
import os
import time
from pathlib import Path

import paho.mqtt.client as mqtt

from .pipeline import Ingestion, Rejected
from iot_shared.observability import worker_metrics


def main():
    worker_metrics()
    repo = Ingestion(os.environ.get('REGISTRY_DATABASE_URL', ''))
    repo.initialize_ingestion()
    credentials = json.loads(Path(os.environ['MQTT_BRIDGE_CREDENTIALS']).read_text(encoding='utf-8'))
    while True:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='iot-ingestion-bridge',
                             clean_session=False, manual_ack=True)
        client.username_pw_set(credentials['usuario'], credentials['token'])
        if os.environ.get('MQTT_CA_CERT'):
            client.tls_set(ca_certs=os.environ['MQTT_CA_CERT'])

        def connected(client, userdata, flags, reason, properties):
            if reason != 0:
                raise RuntimeError('Broker authentication rejected')
            for kind in ('telemetria', 'evento', 'estado'):
                client.subscribe('+/+/+/+/' + kind, qos=1)

        def received(client, userdata, incoming):
            try:
                try:
                    message = json.loads(incoming.payload)
                except (ValueError, UnicodeError):
                    repo.reject_malformed_mqtt(incoming.topic, incoming.payload)
                else:
                    try:
                        repo.receive(message, mqtt_topic=incoming.topic)
                    except Rejected:
                        pass  # Authenticated invalid data has a durable DLQ reason.
                client.ack(incoming.mid, incoming.qos)
            except Exception:
                # Propagate to reconnect; unacknowledged QoS 1 is redelivered by the broker.
                logging.exception('Ingestion unavailable; MQTT message not acknowledged')
                raise

        client.on_connect = connected
        client.on_message = received
        try:
            client.connect(os.environ.get('MQTT_HOST', 'registry-mosquitto'), int(os.environ.get('MQTT_PORT', '1883')))
            client.loop_forever()
        except Exception:
            logging.exception('Bridge reconnecting')
        finally:
            client.disconnect()
        time.sleep(2)


if __name__ == '__main__':
    main()
