"""Validation filters and PostgreSQL outbox. No domain names are special-cased."""
import hashlib
import hmac
import json
import logging
import re
from datetime import datetime
from pathlib import Path

from jsonschema import ValidationError
from psycopg.types.json import Jsonb

from iot_shared.canonical import topic, validate
from iot_shared.observability import MESSAGES
from registry_service.repository import Registry
from registry_service.security import digest


class Rejected(Exception):
    def __init__(self, errors, status=400):
        self.errors = errors
        self.status = status


def reject(code, field='', status=400):
    raise Rejected([{'codigo': code, 'campo': field}], status)


def check_contract(message):
    try:
        validate(message)
    except ValidationError as exc:
        reject('schema_invalido', '.'.join(map(str, exc.absolute_path)))
    except (ValueError, TypeError, OverflowError):
        reject('json_invalido')
    if message['tipo'] == 'comando':
        reject('comando_nao_e_ingestao', 'tipo')


def check_profile(message, profile, fields=None):
    suspect = []
    if message['tipo'] == 'telemetria':
        for name, measure in message['dados'].items():
            specification = profile.get(name)
            if specification is None:
                reject('grandeza_nao_cadastrada', 'dados.' + name)
            if measure['unidade'] != specification['unidade']:
                reject('unidade_incompativel', 'dados.' + name + '.unidade')
            if not specification['minimo'] <= measure['valor'] <= specification['maximo']:
                suspect.append(name)
    else:
        allowed = (fields or {}).get(message['tipo'], {})
        for name, value in message['dados'].items():
            specification = allowed.get(name)
            if specification is None:
                reject('campo_nao_cadastrado', 'dados.' + name)
            kind = specification['tipo']
            valid = ((kind == 'numero' and type(value) in (int, float))
                     or (kind == 'booleano' and type(value) is bool)
                     or (kind == 'enum' and value in specification['valores'])
                     or (kind == 'vetor' and isinstance(value, list)
                         and len(value) == specification['tamanho']
                         and all(type(item) in (int, float) for item in value)))
            if not valid:
                reject('campo_invalido', 'dados.' + name)
            numbers = value if kind == 'vetor' else [value] if kind == 'numero' else []
            if any((specification.get('minimo') is not None and number < specification['minimo'])
                   or (specification.get('maximo') is not None and number > specification['maximo'])
                   for number in numbers):
                reject('campo_fora_da_faixa', 'dados.' + name)
            if specification.get('retangulo') and not (value[0] < value[2] and value[1] < value[3]):
                reject('retangulo_invalido', 'dados.' + name)
    return suspect


class Ingestion(Registry):
    def initialize_ingestion(self):
        with self.connect() as conn:
            conn.execute('SELECT pg_advisory_xact_lock(74189321)')
            conn.execute(Path(__file__).with_name('schema.sql').read_text(encoding='utf-8'))

    def receive(self, message, *, token=None, mqtt_topic=None):
        """mqtt_topic may ONLY be supplied by the trusted broker bridge, never HTTP."""
        serialized = json.dumps(message, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
        fingerprint = hashlib.sha256(serialized.encode()).hexdigest()
        error = None
        with self.connect() as conn:
            query = ('SELECT d.*, p.dominio, p.grandezas, p.campos, p.intervalo_esperado_s, p.tolerancia_intervalos '
                     'FROM registry_devices d JOIN registry_profiles p ON p.tenant=d.tenant AND p.id=d.perfil ')
            if mqtt_topic is not None:
                parts = mqtt_topic.split('/')
                if len(parts) != 5 or any(not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', part) for part in parts):
                    reject('topico_invalido', status=401)
                row = conn.execute(query + 'WHERE d.tenant=%s AND d.id=%s AND d.revoked_at IS NULL FOR UPDATE OF d',
                                   (parts[0], parts[3])).fetchone()
            else:
                if not token:
                    reject('credencial_invalida', status=401)
                row = conn.execute(query + 'WHERE d.token_digest=%s AND d.revoked_at IS NULL FOR UPDATE OF d',
                                   (digest(token),)).fetchone()
            if row is None:
                reject('credencial_invalida', status=401)
            now = self.clock()
            try:
                check_contract(message)
                expected = {'inquilino': row['tenant'], 'site': row['site'], 'dominio': row['dominio'],
                            'dispositivo': row['id']}
                if any(message[key] != value for key, value in expected.items()):
                    reject('identidade_incompativel', status=403)
                if mqtt_topic is not None and topic(message) != mqtt_topic:
                    reject('topico_incompativel', status=403)
                measured = datetime.fromisoformat(message['timestamp'].replace('Z', '+00:00'))
                if (measured - now).total_seconds() > 30:
                    reject('timestamp_futuro', 'timestamp')
                suspect = check_profile(message, row['grandezas'], row['campos'])
                previous = conn.execute('SELECT fingerprint, device FROM ingest_messages WHERE tenant=%s AND id=%s',
                                        (row['tenant'], message['id_mensagem'])).fetchone()
                if previous:
                    if previous['device'] != row['id'] or not hmac.compare_digest(previous['fingerprint'], fingerprint):
                        reject('id_mensagem_reutilizado', 'id_mensagem', status=409)
                    return {'id_mensagem': message['id_mensagem'], 'status': 'duplicada'}
                latest = conn.execute('SELECT max(measured_at) AS latest FROM ingest_messages WHERE tenant=%s AND device=%s',
                                      (row['tenant'], row['id'])).fetchone()['latest']
                late = (latest is not None and measured < latest) or (now - measured).total_seconds() > (
                    row['intervalo_esperado_s'] * row['tolerancia_intervalos'])
                context = {'area': row['area'], 'perfil': row['perfil'], 'atrasado': late, 'suspeitas': suspect,
                           'recebido_em': now.isoformat()}
                inserted = conn.execute('INSERT INTO ingest_messages '
                             '(tenant,id,device,measured_at,received_at,fingerprint,envelope,context) '
                             'VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING id',
                             (row['tenant'], message['id_mensagem'], row['id'], measured, now, fingerprint,
                              Jsonb(message), Jsonb(context))).fetchone()
                if inserted is None:
                    reject('id_mensagem_reutilizado', 'id_mensagem', status=409)
                conn.execute('UPDATE registry_devices SET last_seen=%s WHERE tenant=%s AND id=%s',
                             (now, row['tenant'], row['id']))
                result = {'id_mensagem': message['id_mensagem'], 'status': 'aceita', **context}
            except Rejected as exc:
                # Keep reasons and a fingerprint, never raw untrusted images or personal data.
                conn.execute('INSERT INTO ingest_dead_letters (tenant,device,received_at,fingerprint,errors) '
                             'VALUES (%s,%s,%s,%s,%s)', (row['tenant'], row['id'], now, fingerprint, Jsonb(exc.errors)))
                error = exc
        if error:
            MESSAGES.labels('rejected').inc()
            raise error
        MESSAGES.labels('accepted').inc()
        logging.getLogger('ingestion').info('message_committed', extra={'correlation_id': message['id_mensagem']})
        return result

    def reject_malformed_mqtt(self, mqtt_topic, payload):
        parts = mqtt_topic.split('/')
        if len(parts) != 5:
            return
        with self.connect() as conn:
            row = conn.execute('SELECT id FROM registry_devices WHERE tenant=%s AND id=%s',
                               (parts[0], parts[3])).fetchone()
            if row:
                conn.execute('INSERT INTO ingest_dead_letters (tenant,device,received_at,fingerprint,errors) '
                             'VALUES (%s,%s,%s,%s,%s)', (parts[0], parts[3], self.clock(),
                             hashlib.sha256(payload).hexdigest(), Jsonb([{'codigo': 'json_invalido', 'campo': ''}])))
