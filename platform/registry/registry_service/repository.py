"""PostgreSQL adapter. All request-facing operations require an authenticated tenant."""
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .models import Named, Profile
from .security import digest, new_credential

TABLES = {'dominios': 'registry_domains', 'perfis': 'registry_profiles',
          'sites': 'registry_sites', 'areas': 'registry_areas', 'dispositivos': 'registry_devices'}


class Registry:
    def __init__(self, dsn, clock=None):
        self.dsn = dsn
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @contextmanager
    def connect(self):
        with psycopg.connect(self.dsn, row_factory=dict_row, connect_timeout=5) as conn:
            yield conn

    def initialize(self, tenants, seed_path=None):
        seed = json.loads(Path(seed_path).read_text(encoding='utf-8')) if seed_path else {}
        domains = [Named.model_validate(item) for item in seed.get('dominios', [])]
        profiles = [Profile.model_validate(item) for item in seed.get('perfis', [])]
        with self.connect() as conn:
            conn.execute('SELECT pg_advisory_xact_lock(74189320)')
            conn.execute(Path(__file__).with_name('schema.sql').read_text(encoding='utf-8'))
            for unit in seed.get('unidades_ucum', []):
                conn.execute('INSERT INTO registry_units (code) VALUES (%s) ON CONFLICT DO NOTHING', (unit,))
            for tenant in tenants:
                conn.execute('INSERT INTO registry_tenants (id) VALUES (%s) ON CONFLICT DO NOTHING', (tenant,))
                for model in domains:
                    self.insert(conn, 'dominios', {'tenant': tenant, **model.model_dump()}, ignore=True)
                for model in profiles:
                    self.validate_units(conn, model.model_dump())
                    self.insert(conn, 'perfis', {'tenant': tenant, **model.model_dump()}, ignore=True)

    @staticmethod
    def insert(conn, kind, values, ignore=False):
        query = sql.SQL('INSERT INTO {} ({}) VALUES ({}) {}').format(
            sql.Identifier(TABLES[kind]), sql.SQL(',').join(map(sql.Identifier, values)),
            sql.SQL(',').join(sql.Placeholder() for _ in values),
            sql.SQL('ON CONFLICT DO NOTHING' if ignore else ''),
        )
        conn.execute(query, [Jsonb(v) if isinstance(v, (dict, list)) else v for v in values.values()])

    def create(self, tenant, kind, model, site=None):
        values = {'tenant': tenant, **model.model_dump()}
        if site is not None:
            values['site'] = site
        with self.connect() as conn:
            if kind == 'perfis':
                self.validate_units(conn, values)
            self.insert(conn, kind, values)
        return {k: v for k, v in values.items() if k != 'tenant'}

    @staticmethod
    def validate_units(conn, values):
        units = {measure['unidade'] for measure in values['grandezas'].values()}
        allowed = {row['code'] for row in conn.execute('SELECT code FROM registry_units WHERE code=ANY(%s)',
                                                      (list(units),)).fetchall()}
        if units - allowed:
            raise ValueError('Unidade UCUM fora do catálogo configurado: ' + ', '.join(sorted(units - allowed)))

    def create_device(self, tenant, model):
        token, fingerprint, hashed = new_credential()
        values = {'tenant': tenant, **model.model_dump(), 'mqtt_username': 'device_' + uuid4().hex,
                  'token_digest': fingerprint, 'mqtt_hash': hashed}
        with self.connect() as conn:
            self.insert(conn, 'dispositivos', values)
        device = self.get_device(tenant, model.id)
        return {**device, 'credencial': {'usuario': values['mqtt_username'], 'token': token},
                'mqtt_aplicacao_pendente': True}

    def revoke(self, tenant, device_id):
        with self.connect() as conn:
            row = conn.execute('UPDATE registry_devices SET revoked_at=COALESCE(revoked_at,%s) '
                               'WHERE tenant=%s AND id=%s RETURNING id',
                               (self.clock(), tenant, device_id)).fetchone()
        return row is not None

    def heartbeat(self, tenant, device_id, token):
        with self.connect() as conn:
            return conn.execute('UPDATE registry_devices SET last_seen=%s WHERE tenant=%s AND id=%s '
                                'AND token_digest=%s AND revoked_at IS NULL RETURNING id',
                                (self.clock(), tenant, device_id, digest(token))).fetchone() is not None

    def device_view(self, row):
        now = self.clock()
        seen = row['last_seen']
        online = seen is not None and (now - seen).total_seconds() <= (
            row['intervalo_esperado_s'] * row['tolerancia_intervalos'])
        result = {key: row[key] for key in ('id', 'nome', 'site', 'area', 'perfil', 'dominio', 'mqtt_username')}
        result.update(ultimo_contato=seen, credencial_revogada=row['revoked_at'] is not None,
                      status='online' if online and row['revoked_at'] is None else 'offline',
                      intervalo_esperado_s=row['intervalo_esperado_s'],
                      tolerancia_intervalos=row['tolerancia_intervalos'])
        result['topico_base'] = '/'.join((row['tenant'], row['site'], row['dominio'], row['id']))
        return result

    @staticmethod
    def device_query():
        return ('SELECT d.*, p.dominio, p.intervalo_esperado_s, p.tolerancia_intervalos '
                'FROM registry_devices d JOIN registry_profiles p ON p.tenant=d.tenant AND p.id=d.perfil ')

    def get_device(self, tenant, device_id):
        with self.connect() as conn:
            row = conn.execute(self.device_query() + 'WHERE d.tenant=%s AND d.id=%s', (tenant, device_id)).fetchone()
        return self.device_view(row) if row else None

    def listing(self, tenant, kind, page, size, sort, filter_value, site=None):
        prefix = 'd.' if kind == 'dispositivos' else ''
        condition = sql.SQL('{}tenant=%s').format(sql.SQL(prefix))
        params = [tenant]
        if site is not None:
            condition += sql.SQL(' AND site=%s')
            params.append(site)
        if filter_value:
            condition += sql.SQL(' AND position(lower(%s) in lower({}nome))>0').format(sql.SQL(prefix))
            params.append(filter_value)
        table = sql.Identifier(TABLES[kind])
        select = sql.SQL(self.device_query()) if kind == 'dispositivos' else sql.SQL('SELECT * FROM {} ').format(table)
        order = sql.SQL('{}{} {}').format(sql.SQL(prefix), sql.Identifier(sort.lstrip('-')),
                                        sql.SQL('DESC' if sort.startswith('-') else 'ASC'))
        # A stable id tie-breaker prevents overlapping pages for equal names.
        order += sql.SQL(', {}id ASC').format(sql.SQL(prefix))
        with self.connect() as conn:
            count_prefix = 'd' if kind == 'dispositivos' else 't'
            total = conn.execute(sql.SQL('SELECT count(*) AS total FROM {} {} WHERE ').format(
                table, sql.Identifier(count_prefix)) + condition, params).fetchone()['total']
            rows = conn.execute(select + sql.SQL('WHERE ') + condition + sql.SQL(' ORDER BY ') + order
                                + sql.SQL(' LIMIT %s OFFSET %s'), [*params, size, (page - 1) * size]).fetchall()
        items = [self.device_view(row) if kind == 'dispositivos' else
                 {k: v for k, v in row.items() if k != 'tenant'} for row in rows]
        return {'page': page, 'size': size, 'total': total, 'items': items}

    def broker_entries(self):
        """Privileged maintenance CLI only; never exposed through the tenant API."""
        with self.connect() as conn:
            return conn.execute(self.device_query() + 'ORDER BY d.tenant, d.id').fetchall()
