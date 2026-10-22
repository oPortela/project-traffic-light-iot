import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.controller import Controller
from app.integration import MqttPublisher, TrafficIntegration, identity_from_env
from iot_shared.canonical import envelope, topic


class MemoryPublisher:
    def __init__(self):
        self.messages = []

    def publish(self, message):
        self.messages.append(message)
        return True


def test_mapping_interval_transition_utc_and_privacy():
    publisher = MemoryPublisher()
    integration = TrafficIntegration(publisher, identity_from_env(), monotonic=100,
                                     utc=datetime(2026, 1, 1, tzinfo=timezone.utc))
    controller = Controller()
    state = {"roi": [0, 0, 1, 1], "mode": "demo", "running": True,
             "ids": ["private-tracking-id"], "frame": b"private-image"}
    integration.observe(controller, state, 100, 1, "idle")
    assert [m['tipo'] for m in publisher.messages] == ['estado', 'telemetria']
    assert publisher.messages[0]['timestamp'] == '2026-01-01T00:00:00.000Z'
    integration.observe(controller, state, 104, 1, "idle")
    assert len(publisher.messages) == 2
    controller.transition('yellow', 105)
    integration.observe(controller, state, 105, 1, "idle")
    assert [m['tipo'] for m in publisher.messages] == ['estado', 'telemetria', 'evento', 'telemetria']
    assert publisher.messages[2]['dados'] == {'evento': 'transicao_fase', 'origem': 'idle', 'destino': 'yellow'}
    assert publisher.messages[2]['timestamp'] == '2026-01-01T00:00:05.000Z'
    serialized = json.dumps(publisher.messages)
    assert 'private' not in serialized
    assert 'frame' not in serialized
    assert 'ids' not in serialized
    state['mode'] = 'camera'
    integration.observe(controller, state, 106, 0, "yellow")
    assert publisher.messages[-1]['dados']['modo'] == 'camera'


@pytest.fixture
def mqtt(monkeypatch):
    monkeypatch.setenv('MQTT_USERNAME', 'device')
    monkeypatch.setenv('MQTT_PASSWORD', 'test-only')
    monkeypatch.setenv('MQTT_HOST', 'localhost')
    monkeypatch.delenv('MQTT_CA_CERT', raising=False)
    client = Mock()
    client.publish.return_value.rc = 0
    return MqttPublisher(identity_from_env(), Mock(), Mock(), client=client)


def command(mqtt):
    return envelope(mqtt.identity, 'comando', {'acao': 'start'})


def incoming(message, **changes):
    return SimpleNamespace(**({'payload': json.dumps(message).encode(), 'topic': topic(message),
                              'retain': False} | changes))


def test_command_deduplication(mqtt):
    message = incoming(command(mqtt))
    mqtt._message(None, None, message)
    mqtt._message(None, None, message)
    mqtt.on_command.assert_called_once_with({'acao': 'start'})


@pytest.mark.parametrize('invalid', ['tenant', 'retained', 'expired', 'invalid-json', 'oversize', 'topic'])
def test_reject_unsafe_commands(mqtt, invalid):
    message = command(mqtt)
    if invalid == 'tenant':
        message['inquilino'] = 'other'
    if invalid == 'expired':
        message['timestamp'] = '2020-01-01T00:00:00Z'
    data = incoming(message, topic=mqtt.command_topic)
    if invalid == 'retained':
        data.retain = True
    if invalid == 'invalid-json':
        data.payload = b'{'
    if invalid == 'oversize':
        data.payload = b'x' * 16385
    if invalid == 'topic':
        data.topic = 'other/topic'
    mqtt._message(None, None, data)
    mqtt.on_command.assert_not_called()


def test_connection_publish_and_close(mqtt):
    mqtt.start()
    mqtt.client.connect_async.assert_called_once_with('localhost', 1883)
    mqtt._connected(mqtt.client, None, None, 0, None)
    mqtt.client.subscribe.assert_called_once_with(mqtt.command_topic, qos=1)
    mqtt.on_reconnect.assert_called_once()
    message = envelope(mqtt.identity, 'estado', {'wait': 10})
    assert mqtt.publish(message)
    assert mqtt.client.publish.call_args.kwargs == {'qos': 1, 'retain': True}
    mqtt.client.publish.return_value.rc = 15
    assert not mqtt.publish(message)
    mqtt.close()
    mqtt.client.loop_stop.assert_called_once()


def test_rejected_publication_is_retried():
    publisher = Mock()
    publisher.publish.return_value = False
    integration = TrafficIntegration(publisher, identity_from_env())
    state = {'roi': [0, 0, 1, 1], 'mode': 'demo', 'running': False}
    integration.observe(Controller(), state, 100, 0, 'idle')
    assert integration.reported is None
    assert integration.last_telemetry is None
