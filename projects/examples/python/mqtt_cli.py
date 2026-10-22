"""Observe canonical messages or send fresh commands with a platform credential."""
import argparse
import json
import os
import sys
from pathlib import Path

import paho.mqtt.client as mqtt

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from iot_shared.canonical import envelope, topic, validate  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['listen', 'start', 'stop', 'reset', 'config'])
    parser.add_argument('--params', default='{}', help='JSON command parameters')
    args = parser.parse_args()
    identity = {key: os.environ.get('IOT_' + key.upper(), default) for key, default in {
        'inquilino': 'semob', 'site': 'centro', 'dominio': 'mobilidade',
        'dispositivo': 'semaforo-travessia-01',
    }.items()}
    base = '/'.join(identity[k] for k in ('inquilino', 'site', 'dominio', 'dispositivo'))
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(os.environ['MQTT_USERNAME'], os.environ['MQTT_PASSWORD'])
    if os.environ.get('MQTT_CA_CERT'):
        client.tls_set(ca_certs=os.environ['MQTT_CA_CERT'])

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code != 0:
            print(f'MQTT authentication failed: {reason_code}', file=sys.stderr)
            client.disconnect()
            return
        if args.action == 'listen':
            for kind in ('telemetria', 'evento', 'estado'):
                client.subscribe(base + '/' + kind, qos=1)
        else:
            message = envelope(identity, 'comando', {'acao': args.action, 'parametros': json.loads(args.params)})
            client.publish(topic(message), json.dumps(message), qos=1, retain=False)

    def on_message(client, userdata, message):
        print(json.dumps(validate(json.loads(message.payload)), ensure_ascii=False), flush=True)

    def on_publish(client, userdata, mid, reason_code, properties):
        print('Comando enviado ao broker; a execução ainda pode ser recusada pelo dispositivo.')
        client.disconnect()

    client.on_connect = on_connect
    client.on_message = on_message
    if args.action != 'listen':
        client.on_publish = on_publish
    client.connect(os.environ.get('MQTT_HOST', 'localhost'), int(os.environ.get('MQTT_PORT', '1883')))
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        client.disconnect()


if __name__ == '__main__':
    main()
