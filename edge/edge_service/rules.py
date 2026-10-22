"""Offline threshold/hysteresis rules with transactional event and command outboxes."""
import json
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from iot_shared.canonical import envelope


class LocalRule(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,64}$')
    grandeza: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,64}$')
    ligar_abaixo: float
    desligar_acima: float
    acao: str = Field(default='irrigar', pattern=r'^[a-zA-Z0-9_-]{1,64}$')
    max_age_s: int = Field(default=10800, ge=1, le=259200)

    @model_validator(mode='after')
    def hysteresis(self):
        if self.ligar_abaixo >= self.desligar_acima:
            raise ValueError('Histerese exige limiar de ligar menor que desligar')
        return self


class Rules:
    def __init__(self, queue):
        self.queue = queue
        with queue.connect() as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS local_rules_state ('
                         'route TEXT NOT NULL,rule TEXT NOT NULL,active INTEGER NOT NULL,measured REAL NOT NULL,'
                         'PRIMARY KEY(route,rule))')
            conn.execute('CREATE TABLE IF NOT EXISTS local_commands ('
                         'id TEXT PRIMARY KEY,route TEXT NOT NULL,payload BLOB NOT NULL)')
            conn.execute('CREATE TABLE IF NOT EXISTS local_configuration ('
                         'route TEXT PRIMARY KEY,revision INTEGER NOT NULL,payload BLOB NOT NULL)')

    def configure(self, route, revision, rules):
        validated = [LocalRule.model_validate(rule).model_dump() for rule in rules]
        if len({rule['id'] for rule in validated}) != len(validated):
            raise ValueError('Identificadores de regras duplicados')
        with self.queue.connect() as conn:
            conn.execute('INSERT INTO local_configuration VALUES(?,?,?) ON CONFLICT(route) DO UPDATE SET '
                         'revision=excluded.revision,payload=excluded.payload '
                         'WHERE local_configuration.revision<excluded.revision',
                         (route, revision, self.queue.cipher.encrypt(json.dumps(validated).encode())))

    def receive(self, route, message):
        with self.queue.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            if not self.queue.put(route, message, priority=int(message['tipo'] == 'evento'), transaction=conn):
                return
            config = conn.execute('SELECT payload FROM local_configuration WHERE route=?', (route,)).fetchone()
            if message['tipo'] != 'telemetria' or config is None:
                return
            rules = json.loads(self.queue.cipher.decrypt(config['payload']))
            measured = datetime.fromisoformat(message['timestamp'].replace('Z', '+00:00')).timestamp()
            for rule in rules:
                age = self.queue.clock() - measured
                if age > rule['max_age_s'] or age < -30:
                    continue
                value = message['dados'].get(rule['grandeza'], {}).get('valor')
                if value is None:
                    continue
                previous = conn.execute('SELECT active,measured FROM local_rules_state WHERE route=? AND rule=?',
                                        (route, rule['id'])).fetchone()
                if previous and measured <= previous['measured']:
                    continue
                was_active = bool(previous['active']) if previous else False
                active = value < rule['desligar_acima'] if was_active else value < rule['ligar_abaixo']
                conn.execute('INSERT INTO local_rules_state VALUES(?,?,?,?) ON CONFLICT(route,rule) '
                             'DO UPDATE SET active=excluded.active,measured=excluded.measured',
                             (route, rule['id'], int(active), measured))
                if active == was_active:
                    continue
                identity = {key: message[key] for key in ('inquilino', 'site', 'dominio', 'dispositivo')}
                event = envelope(identity, 'evento', {'evento': 'regra_local', 'ativo': active},
                                 occurred_at=message['timestamp'])
                self.queue.put(route, event, priority=10, transaction=conn)
                command = envelope(identity, 'comando', {'acao': rule['acao'], 'parametros': {'ativo': active}})
                conn.execute('INSERT INTO local_commands VALUES(?,?,?)',
                             (command['id_mensagem'], route, self.queue.cipher.encrypt(json.dumps(command).encode())))

    def commands(self):
        with self.queue.connect() as conn:
            rows = conn.execute('SELECT * FROM local_commands ORDER BY rowid LIMIT 100').fetchall()
        return [{**dict(row), 'message': json.loads(self.queue.cipher.decrypt(row['payload']))} for row in rows]

    def confirm_command(self, identifier):
        with self.queue.connect() as conn:
            conn.execute('DELETE FROM local_commands WHERE id=?', (identifier,))
