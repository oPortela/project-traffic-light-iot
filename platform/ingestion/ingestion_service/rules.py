"""Rule evaluation by measurement time; delayed/suspect readings do not create current alarms."""
import operator
from datetime import timedelta
from typing import Literal
from uuid import uuid4

from psycopg.types.json import Jsonb
from pydantic import Field, model_validator

from registry_service.models import Identifier, Model

OPERATORS = {'gt': operator.gt, 'ge': operator.ge, 'lt': operator.lt, 'le': operator.le}


class Action(Model):
    tipo: Literal['alarme', 'webhook', 'topico', 'comando'] = 'alarme'
    destino: str | None = Field(default=None, max_length=500)
    dados: dict = Field(default_factory=dict)

    @model_validator(mode='after')
    def requires_destination(self):
        if self.tipo in ('webhook', 'topico') and not self.destino:
            raise ValueError('Ação exige destino')
        if self.tipo == 'comando' and self.dados.get('acao') not in ('start', 'stop', 'reset', 'config'):
            raise ValueError('Comando inválido')
        return self


class Rule(Model):
    id: Identifier
    dispositivo: Identifier
    tipo: Literal['limite', 'ausencia', 'janela']
    grandeza: Identifier | None = None
    operador: Literal['gt', 'ge', 'lt', 'le'] = 'gt'
    limite: float = 0
    janela_s: int = Field(default=60, ge=1, le=2592000)
    severidade: Literal['info', 'aviso', 'critico'] = 'aviso'
    acoes: list[Action] = Field(default_factory=lambda: [Action()], min_length=1, max_length=10)

    @model_validator(mode='after')
    def requires_measurement(self):
        if self.tipo != 'ausencia' and not self.grandeza:
            raise ValueError('Regra exige grandeza')
        return self


def change_alarm(conn, tenant, rule, breach, when, now, details):
    if not breach:
        conn.execute("UPDATE processing_alarms SET status='resolvido',updated_at=%s "
                     "WHERE tenant=%s AND rule_id=%s AND status IN ('ativo','reconhecido')", (now, tenant, rule['id']))
        return
    alarm_id = str(uuid4())
    created = conn.execute('INSERT INTO processing_alarms '
                          '(id,tenant,rule_id,device,status,severity,occurred_at,updated_at,details) '
                          "VALUES (%s,%s,%s,%s,'ativo',%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING id",
                          (alarm_id, tenant, rule['id'], rule['dispositivo'], rule['severidade'], when, now,
                           Jsonb(details))).fetchone()
    if created:
        for action in rule['acoes']:
            if action['tipo'] != 'alarme':
                conn.execute('INSERT INTO processing_actions (alarm_id,action,next_attempt) VALUES (%s,%s,%s)',
                             (alarm_id, Jsonb(action), now))


def evaluate_message(conn, tenant, device, message, context, when, now):
    if message['tipo'] != 'telemetria' or context['atrasado']:
        return
    rules = conn.execute('SELECT definition,evaluated_at FROM processing_rules WHERE tenant=%s AND device=%s '
                         'ORDER BY id FOR UPDATE',
                         (tenant, device)).fetchall()
    for row in rules:
        rule = row['definition']
        field = rule['grandeza']
        if (rule['tipo'] == 'ausencia' or field not in message['dados'] or field in context['suspeitas']
                or (row['evaluated_at'] is not None and when < row['evaluated_at'])):
            continue
        value = message['dados'][field]['valor']
        if rule['tipo'] == 'janela':
            value = conn.execute('SELECT avg(valor) AS value FROM telemetria WHERE inquilino=%s AND dispositivo=%s '
                                 "AND grandeza=%s AND time BETWEEN %s AND %s AND flags->>'atrasado'='false' "
                                 "AND flags->>'suspeita'='false'",
                                 (tenant, device, field, when - timedelta(seconds=rule['janela_s']), when)).fetchone()['value']
        if value is not None:
            conn.execute('UPDATE processing_rules SET evaluated_at=%s WHERE tenant=%s AND id=%s',
                         (when, tenant, rule['id']))
            change_alarm(conn, tenant, rule, OPERATORS[rule['operador']](value, rule['limite']), when, now,
                         {'grandeza': field, 'valor': value, 'limite': rule['limite']})


def evaluate_absence(repo):
    now = repo.clock()
    with repo.connect() as conn:
        rows = conn.execute("SELECT r.tenant,r.definition,r.created_at,d.last_seen FROM processing_rules r "
                            "JOIN registry_devices d ON d.tenant=r.tenant AND d.id=r.device "
                            "WHERE r.definition->>'tipo'='ausencia' AND d.revoked_at IS NULL").fetchall()
        for row in rows:
            rule = row['definition']
            last = row['last_seen'] or row['created_at']
            occurred = last + timedelta(seconds=rule['janela_s'])
            change_alarm(conn, row['tenant'], rule, now > occurred, occurred, now, {'ultimo_contato': last.isoformat()})
