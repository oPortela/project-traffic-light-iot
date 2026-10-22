"""Durable action strategies with bounded retries and webhook idempotency keys."""
import json
import logging
import os
import re
import time
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse
from uuid import NAMESPACE_URL, uuid5

import httpx
from paho.mqtt import publish

from iot_shared.canonical import envelope, topic
from iot_shared.observability import worker_metrics, ALARMS, STATE_AGE

from .rules import evaluate_absence
from .storage import Storage


def validate_action(action, tenant, device):
    if action['tipo'] == 'webhook':
        parsed = urlparse(action['destino'])
        allowed = set(filter(None, os.environ.get('WEBHOOK_ALLOWED_HOSTS', '').split(',')))
        if parsed.scheme not in ('http', 'https') or parsed.hostname not in allowed or parsed.username or parsed.password:
            raise ValueError('Webhook fora da lista de hosts autorizados')
    if action['tipo'] == 'topico':
        base = 'acoes/' + tenant + '/' + device + '/'
        if not action['destino'].startswith(base) or not re.fullmatch(r'[A-Za-z0-9_/-]{1,300}', action['destino']):
            raise ValueError('Tópico de ação fora do dispositivo autorizado')


class Webhook:
    def __call__(self, job, body):
        response = httpx.post(job['action']['destino'], json=body, timeout=5, follow_redirects=False,
                              headers={'Idempotency-Key': str(job['id'])})
        response.raise_for_status()


class MqttAction:
    def __call__(self, job, body):
        credentials = json.loads(Path(os.environ['MQTT_ACTION_CREDENTIALS']).read_text(encoding='utf-8'))
        action = job['action']
        if action['tipo'] == 'comando':
            payload = envelope({'inquilino': job['tenant'], 'site': job['site'], 'dominio': job['dominio'],
                                'dispositivo': job['device']}, 'comando', action['dados'])
            payload['id_mensagem'] = str(uuid5(NAMESPACE_URL, 'iot-action:' + str(job['id'])))
            destination = topic(payload)
        else:
            destination, payload = action['destino'], body
        publish.single(destination, json.dumps(payload), qos=1, retain=False,
                       hostname=os.environ.get('MQTT_HOST', 'registry-mosquitto'),
                       port=int(os.environ.get('MQTT_PORT', '1883')),
                       auth={'username': credentials['usuario'], 'password': credentials['token']},
                       tls={'ca_certs': os.environ['MQTT_CA_CERT']} if os.environ.get('MQTT_CA_CERT') else None)


def dispatch_once(repo, strategies=None):
    strategies = strategies or {'webhook': Webhook(), 'topico': MqttAction(), 'comando': MqttAction()}
    now = repo.clock()
    with repo.connect() as conn:
        jobs = conn.execute('SELECT j.*,a.tenant,a.device,a.rule_id,a.severity,a.occurred_at,a.details,d.site,p.dominio '
                            'FROM processing_actions j JOIN processing_alarms a ON a.id=j.alarm_id '
                            'JOIN registry_devices d ON d.tenant=a.tenant AND d.id=a.device '
                            'JOIN registry_profiles p ON p.tenant=d.tenant AND p.id=d.perfil '
                            'WHERE j.delivered_at IS NULL AND j.attempts<15 AND j.next_attempt<=%s '
                            'AND d.revoked_at IS NULL '
                            'ORDER BY j.id LIMIT 10 FOR UPDATE OF j SKIP LOCKED', (now,)).fetchall()
        for job in jobs:
            try:
                validate_action(job['action'], job['tenant'], job['device'])
                body = {'id_alarme': str(job['alarm_id']), 'inquilino': job['tenant'], 'dispositivo': job['device'],
                        'severidade': job['severity'], 'timestamp': job['occurred_at'].isoformat(), 'dados': job['details']}
                strategies[job['action']['tipo']](job, body)
                conn.execute('UPDATE processing_actions SET delivered_at=%s,attempts=attempts+1,last_error=NULL WHERE id=%s',
                             (now, job['id']))
            except Exception as exc:
                conn.execute('UPDATE processing_actions SET attempts=attempts+1,next_attempt=%s,last_error=%s WHERE id=%s',
                             (now + timedelta(seconds=min(300, 2 ** min(job['attempts'] + 1, 9))),
                              type(exc).__name__, job['id']))
        return len(jobs)


def main():
    worker_metrics()
    repo = Storage(os.environ.get('REGISTRY_DATABASE_URL', ''))
    repo.initialize_storage()
    while True:
        try:
            evaluate_absence(repo)
            dispatch_once(repo)
            from .twins import dispatch_twins
            dispatch_twins(repo, MqttAction())
            with repo.connect() as conn:
                ALARMS.set(conn.execute("SELECT count(*) AS n FROM processing_alarms WHERE status!='resolvido'").fetchone()['n'])
                latest = conn.execute('SELECT max(timestamp) AS latest FROM ultimo_estado').fetchone()['latest']
                if latest:
                    STATE_AGE.set(max(0, (repo.clock() - latest).total_seconds()))
        except Exception:
            logging.exception('Rule/action worker failed; retrying')
        time.sleep(1)


if __name__ == '__main__':
    main()
