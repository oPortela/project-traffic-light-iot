"""Tenant-scoped data queries. Authentication shares the registry's bootstrap mapping."""
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials
from psycopg.types.json import Jsonb

from registry_service.models import Identifier
from registry_service.security import bearer
from registry_service.oidc import configured_auth, authorize
from iot_shared.observability import instrument
from iot_shared.contracts import publish_contracts

from .storage import Storage
from .rules import Rule
from .pagination import listing
from .realtime import attach


def create_app(storage=None, administrators=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.storage = storage or Storage(os.environ.get('REGISTRY_DATABASE_URL', ''))
        app.state.storage.initialize_storage()
        app.state.administrators = administrators or configured_auth()
        app.state.geometry = None
        if os.environ.get('GEO_ENABLED') == 'true':
            from .geometry import GeometryStore
            app.state.geometry = GeometryStore()
            app.state.geometry.initialize()
        yield

    app = FastAPI(title='Plataforma IoT — Dados', version='1.0.0', lifespan=lifespan)
    instrument(app, 'data-api')
    publish_contracts(app)
    attach(app)

    def tenant(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        return authorize(app.state.administrators, credentials, request)

    Tenant = Annotated[str, Depends(tenant)]

    @app.put('/api/v1/sites/{site}/areas/{area}/geometria')
    def put_geometry(site: Identifier, area: Identifier, body: dict, tenant: Tenant):
        if app.state.geometry is None:
            raise HTTPException(503, 'Modulo PostGIS nao habilitado')
        with app.state.storage.connect() as conn:
            if not conn.execute('SELECT 1 FROM registry_areas WHERE tenant=%s AND site=%s AND id=%s',
                                (tenant, site, area)).fetchone():
                raise HTTPException(404, 'Area nao encontrada')
        try:
            return app.state.geometry.put(tenant, site, area, body)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get('/api/v1/geometrias')
    def geometries(tenant: Tenant, page: int = Query(1, ge=1), size: int = Query(100, ge=1, le=200)):
        if app.state.geometry is None:
            raise HTTPException(503, 'Modulo PostGIS nao habilitado')
        return app.state.geometry.collection(tenant, page, size)

    @app.get('/health', include_in_schema=False)
    def health():
        with app.state.storage.connect() as conn:
            conn.execute('SELECT 1')
        return {'status': 'ok'}

    @app.get('/api/v1/dispositivos/{device_id}/ultimo-estado')
    def last_state(device_id: Identifier, tenant: Tenant):
        if app.state.storage.get_device(tenant, device_id) is None:
            raise HTTPException(404, 'Dispositivo não encontrado')
        with app.state.storage.connect() as conn:
            return conn.execute('SELECT tipo,timestamp,dados FROM ultimo_estado WHERE inquilino=%s AND dispositivo=%s '
                                'ORDER BY tipo', (tenant, device_id)).fetchall()

    @app.put('/api/v1/dispositivos/{device_id}/gemeo/desejado')
    def desired_state(device_id: Identifier, body: dict, tenant: Tenant):
        from .twins import set_desired
        try:
            return set_desired(app.state.storage, tenant, device_id, body)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get('/api/v1/dispositivos/{device_id}/gemeo')
    def twin(device_id: Identifier, tenant: Tenant):
        from .twins import get_twin
        try:
            return get_twin(app.state.storage, tenant, device_id)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get('/api/v1/telemetria')
    def telemetry(tenant: Tenant, dispositivo: Identifier | None = None, grandeza: Identifier | None = None,
                  inicio: datetime | None = None, fim: datetime | None = None,
                  page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200),
                  sort: Literal['time', '-time', 'valor', '-valor'] = '-time',
                  filter: str = Query('', max_length=160)):
        where, params = ['inquilino=%s'], [tenant]
        if filter:
            where.append('(position(lower(%s) in lower(dispositivo))>0 OR position(lower(%s) in lower(grandeza))>0)')
            params.extend([filter, filter])
        for column, value, operator in [('dispositivo', dispositivo, '='), ('grandeza', grandeza, '='),
                                        ('time', inicio, '>='), ('time', fim, '<=')]:
            if value is not None:
                if isinstance(value, datetime) and value.tzinfo is None:
                    raise HTTPException(422, 'Use timestamps com timezone')
                where.append(column + operator + '%s')
                params.append(value)
        if inicio and fim and inicio > fim:
            raise HTTPException(422, 'Intervalo inválido')
        with app.state.storage.connect() as conn:
            condition = ' AND '.join(where)
            total = conn.execute('SELECT count(*) AS n FROM telemetria WHERE ' + condition, params).fetchone()['n']
            rows = conn.execute('SELECT time,id_mensagem,dispositivo,grandeza,valor,unidade,site,area,dominio,flags '
                                'FROM telemetria WHERE ' + condition + ' ORDER BY ' + sort.lstrip('-')
                                + (' DESC' if sort.startswith('-') else ' ASC') + ',id_mensagem,grandeza '
                                'LIMIT %s OFFSET %s', [*params, size, (page - 1) * size]).fetchall()
        return {'page': page, 'size': size, 'total': total, 'items': rows}

    @app.get('/api/v1/ingestao/rejeitadas')
    def rejected(tenant: Tenant, page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200),
                 sort: str = '-id', filter: str = Query('', max_length=160)):
        with app.state.storage.connect() as conn:
            return listing(conn, source='ingest_dead_letters', projection='id,device,received_at,errors',
                           tenant_column='tenant', tenant=tenant, columns={'id': 'id', 'device': 'device'},
                           sort=sort, filter_value=filter, page=page, size=size)

    @app.post('/api/v1/regras', status_code=201)
    def create_rule(body: Rule, tenant: Tenant):
        from psycopg.errors import UniqueViolation
        from .actions import validate_action
        try:
            for action in body.acoes:
                validate_action(action.model_dump(), tenant, body.dispositivo)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        with app.state.storage.connect() as conn:
            device = conn.execute('SELECT p.grandezas FROM registry_devices d JOIN registry_profiles p '
                                  'ON p.tenant=d.tenant AND p.id=d.perfil WHERE d.tenant=%s AND d.id=%s',
                                  (tenant, body.dispositivo)).fetchone()
            if device is None:
                raise HTTPException(404, 'Dispositivo não encontrado')
            if body.tipo != 'ausencia' and body.grandeza not in device['grandezas']:
                raise HTTPException(422, 'Grandeza não cadastrada')
            try:
                conn.execute('INSERT INTO processing_rules (tenant,id,device,definition,created_at) VALUES (%s,%s,%s,%s,%s)',
                             (tenant, body.id, body.dispositivo, Jsonb(body.model_dump()), app.state.storage.clock()))
            except UniqueViolation as exc:
                raise HTTPException(409, 'Regra já cadastrada') from exc
        return body

    @app.get('/api/v1/regras')
    def rules(tenant: Tenant, page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200),
              sort: str = 'id', filter: str = Query('', max_length=160)):
        with app.state.storage.connect() as conn:
            result = listing(conn, source='processing_rules', projection='definition', tenant_column='tenant',
                             tenant=tenant, columns={'id': 'id', 'device': 'device'}, sort=sort,
                             filter_value=filter, page=page, size=size)
        result['items'] = [row['definition'] for row in result['items']]
        return result

    @app.get('/api/v1/alarmes')
    def alarms(tenant: Tenant, page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200),
               sort: str = '-occurred_at', filter: str = Query('', max_length=160)):
        with app.state.storage.connect() as conn:
            return listing(conn, source='processing_alarms',
                           projection='id,rule_id,device,status,severity,occurred_at,updated_at,details',
                           tenant_column='tenant', tenant=tenant,
                           columns={key: key for key in ('id', 'device', 'status', 'severity', 'occurred_at')},
                           sort=sort, filter_value=filter, page=page, size=size)

    @app.post('/api/v1/alarmes/{alarm_id}/reconhecer')
    def acknowledge(alarm_id: str, tenant: Tenant):
        from uuid import UUID
        try:
            identifier = UUID(alarm_id)
        except ValueError as exc:
            raise HTTPException(422, 'ID inválido') from exc
        with app.state.storage.connect() as conn:
            changed = conn.execute("UPDATE processing_alarms SET status='reconhecido',updated_at=%s "
                                   "WHERE tenant=%s AND id=%s AND status='ativo' RETURNING id,status",
                                   (app.state.storage.clock(), tenant, identifier)).fetchone()
            if changed is None:
                raise HTTPException(409, 'Alarme inexistente ou não está ativo')
        return changed

    @app.get('/api/v1/acoes')
    def actions(tenant: Tenant, page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200),
                sort: str = '-id', filter: str = Query('', max_length=160)):
        with app.state.storage.connect() as conn:
            return listing(conn, source='processing_actions j JOIN processing_alarms a ON a.id=j.alarm_id',
                           projection='j.id,j.alarm_id,j.attempts,j.next_attempt,j.delivered_at,j.last_error',
                           tenant_column='a.tenant', tenant=tenant,
                           columns={'id': 'j.id', 'attempts': 'j.attempts', 'device': 'a.device'},
                           sort=sort, filter_value=filter, page=page, size=size)

    return app


app = create_app()
