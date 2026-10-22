"""Outbound mapping and MQTT adapter, independent of camera and controller logic."""

import json
import logging
import os
import time
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Protocol

from iot_shared.canonical import envelope, timestamp, topic, validate

logger = logging.getLogger(__name__)


class EventPublisher(Protocol):
    def publish(self, message: dict) -> bool: ...


class TrafficIntegration:
    def __init__(self, publisher: EventPublisher, identity, *, monotonic=None, utc=None):
        self.publisher = publisher
        self.identity = identity
        self.reference_monotonic = time.monotonic() if monotonic is None else monotonic
        self.reference_utc = utc or datetime.now(timezone.utc)
        self.last_telemetry = None
        self.reported = None

    def send(self, kind, data, now):
        return self.publisher.publish(envelope(
            self.identity, kind, data,
            occurred_at=timestamp(now, reference_monotonic=self.reference_monotonic,
                                  reference_utc=self.reference_utc),
        ))

    def observe(self, controller, state, now, count, previous_phase):
        if previous_phase != controller.phase:
            self.send("evento", {"evento": "transicao_fase", "origem": previous_phase,
                                  "destino": controller.phase}, now)
        reported = {"wait": controller.settings.wait, "crossing": controller.settings.crossing,
                    "roi": list(state["roi"]), "modo": state["mode"], "running": state["running"]}
        if reported != self.reported:
            if self.send("estado", reported, now):
                self.reported = reported
        if self.last_telemetry is None or now - self.last_telemetry >= 5:
            if self.send("telemetria", {
                "pedestres_na_area": {"valor": count, "unidade": "1"},
                "tempo_espera_s": {"valor": controller.waited, "unidade": "s"},
                "ciclos": {"valor": controller.cycles, "unidade": "1"},
            }, now):
                self.last_telemetry = now


class MqttPublisher:
    """Bounded QoS 1 queue; MQTT failure never blocks the traffic safety loop."""

    def __init__(self, identity, on_command, on_reconnect, *, client=None):
        import paho.mqtt.client as mqtt

        self.identity = identity
        self.on_command = on_command
        self.on_reconnect = on_reconnect
        self.command_ids = OrderedDict()
        self.command_topic = "/".join(identity[k] for k in ("inquilino", "site", "dominio", "dispositivo")) + "/comando"
        self.client = client or mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                           client_id=os.environ.get("MQTT_CLIENT_ID", identity["dispositivo"]))
        self.client.max_queued_messages_set(1000)
        self.client.reconnect_delay_set(min_delay=1, max_delay=60)
        self.client.username_pw_set(os.environ["MQTT_USERNAME"], os.environ["MQTT_PASSWORD"])
        if os.environ.get("MQTT_CA_CERT"):
            self.client.tls_set(ca_certs=os.environ["MQTT_CA_CERT"])
        self.client.on_connect = self._connected
        self.client.on_message = self._message

    def _connected(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            client.subscribe(self.command_topic, qos=1)
            self.on_reconnect()
        else:
            logger.warning("MQTT connection refused: %s", reason_code)

    def _message(self, client, userdata, incoming):
        try:
            if incoming.topic != self.command_topic or incoming.retain or len(incoming.payload) > 16384:
                raise ValueError("Invalid command topic, retained command or oversized payload")
            message = validate(json.loads(incoming.payload))
            if message["tipo"] != "comando" or any(message[k] != v for k, v in self.identity.items()):
                raise ValueError("Command identity mismatch")
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(message["timestamp"].replace("Z", "+00:00"))).total_seconds()
            if not -30 <= age <= 300:
                raise ValueError("Expired command or clock skew")
            message_id = message["id_mensagem"]
            if message_id in self.command_ids:
                return
            self.on_command(message["dados"])
            self.command_ids[message_id] = None
            if len(self.command_ids) > 1024:
                self.command_ids.popitem(last=False)
        except Exception:
            logger.exception("MQTT command rejected")

    def publish(self, message):
        result = self.client.publish(topic(message), json.dumps(message, allow_nan=False), qos=1,
                                     retain=message["tipo"] == "estado")
        # NO_CONN QoS 1 messages remain queued by paho; QUEUE_SIZE means rejected.
        if result.rc not in (0, 4):
            logger.warning("MQTT queue rejected message %s: %s", message["id_mensagem"], result.rc)
            return False
        return True

    def start(self):
        self.client.connect_async(os.environ["MQTT_HOST"], int(os.environ.get("MQTT_PORT", "1883")))
        self.client.loop_start()

    def close(self):
        self.client.disconnect()
        self.client.loop_stop()


def identity_from_env():
    return {key: os.environ.get("IOT_" + key.upper(), default) for key, default in {
        "inquilino": "semob", "site": "centro", "dominio": "mobilidade",
        "dispositivo": "semaforo-travessia-01",
    }.items()}
