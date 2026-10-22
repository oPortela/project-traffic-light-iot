"""Registry REST adapter. Tenant identity always comes from the bearer credential."""
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Query, Response, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials

from .models import Area, CreatedDevice, Device, DeviceView, Identifier, Named, Page, Profile, Revocation
from .repository import Registry
from .security import bearer
from .oidc import configured_auth, authorize
from iot_shared.observability import instrument
from iot_shared.contracts import publish_contracts

DEFAULT_SEED = Path(__file__).resolve().parent.parent / 'seed.json'


def create_app(registry=None, administrators=None, seed_path=DEFAULT_SEED):
    @asynccontextmanager
    async def lifespan(app):
        app.state.registry = registry or Registry(os.environ.get('REGISTRY_DATABASE_URL', ''))
        app.state.administrators = administrators or configured_auth()
        app.state.registry.initialize(app.state.administrators.tenants, os.environ.get('REGISTRY_SEED_FILE', seed_path))
        yield

    app = FastAPI(title='Plataforma IoT — Registry', version='1.0.0', lifespan=lifespan)
    instrument(app, 'registry')
    publish_contracts(app)

    @app.middleware('http')
    async def no_store(request, call_next):
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.exception_handler(psycopg.errors.UniqueViolation)
    async def duplicate(request, error):
        return JSONResponse(status_code=409, content={'detail': 'Identificador já cadastrado neste contexto'})

    @app.exception_handler(psycopg.errors.ForeignKeyViolation)
    async def invalid_reference(request, error):
        return JSONResponse(status_code=422, content={'detail': 'Referência não cadastrada neste inquilino/local'})

    def tenant(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        return authorize(app.state.administrators, credentials, request)

    Tenant = Annotated[str, Depends(tenant)]

    @app.get('/health', include_in_schema=False)
    def health():
        with app.state.registry.connect() as conn:
            conn.execute('SELECT 1')
        return {'status': 'ok'}

    @app.post('/api/v1/catalogo/dominios', status_code=201, response_model=Named)
    def create_domain(body: Named, tenant: Tenant):
        return app.state.registry.create(tenant, 'dominios', body)

    @app.post('/api/v1/perfis', status_code=201, response_model=Profile)
    def create_profile(body: Profile, tenant: Tenant):
        try:
            return app.state.registry.create(tenant, 'perfis', body)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post('/api/v1/sites', status_code=201, response_model=Named)
    def create_site(body: Named, tenant: Tenant):
        return app.state.registry.create(tenant, 'sites', body)

    @app.post('/api/v1/sites/{site_id}/areas', status_code=201, response_model=Area)
    def create_area(site_id: Identifier, body: Named, tenant: Tenant):
        return app.state.registry.create(tenant, 'areas', body, site=site_id)

    @app.post('/api/v1/dispositivos', status_code=201, response_model=CreatedDevice)
    def create_device(body: Device, tenant: Tenant):
        return app.state.registry.create_device(tenant, body)

    @app.get('/api/v1/dispositivos/{device_id}', response_model=DeviceView)
    def get_device(device_id: Identifier, tenant: Tenant):
        device = app.state.registry.get_device(tenant, device_id)
        if device is None:
            raise HTTPException(404, 'Dispositivo não encontrado')
        return device

    @app.delete('/api/v1/dispositivos/{device_id}/credenciais', response_model=Revocation)
    def revoke(device_id: Identifier, tenant: Tenant):
        if not app.state.registry.revoke(tenant, device_id):
            raise HTTPException(404, 'Dispositivo não encontrado')
        return {'revogado': True, 'mqtt_aplicacao_pendente': True}

    @app.post('/api/v1/dispositivos/{device_id}/heartbeat', status_code=204)
    def heartbeat(device_id: Identifier, inquilino: Identifier,
                  credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        # This endpoint authenticates a device, not an administrator. Tenant is bound
        # to its credential in the same conditional UPDATE, never trusted on its own.
        if (credentials is None or credentials.scheme.lower() != 'bearer'
                or not app.state.registry.heartbeat(inquilino, device_id, credentials.credentials)):
            raise HTTPException(401, 'Credencial de dispositivo inválida')
        return Response(status_code=204)

    def list_endpoint(kind):
        def listing(tenant: Tenant, page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200),
                    sort: Literal['id', '-id', 'nome', '-nome'] = 'id',
                    filter: str = Query('', max_length=160)):
            return app.state.registry.listing(tenant, kind, page, size, sort, filter)
        listing.__name__ = 'list_' + kind
        return listing

    for kind, path in [('dominios', 'catalogo/dominios'), ('perfis', 'perfis'),
                       ('sites', 'sites'), ('dispositivos', 'dispositivos')]:
        app.add_api_route('/api/v1/' + path, list_endpoint(kind), response_model=Page, methods=['GET'])

    @app.get('/api/v1/sites/{site_id}/areas', response_model=Page)
    def list_areas(site_id: Identifier, tenant: Tenant, page: int = Query(1, ge=1),
                   size: int = Query(50, ge=1, le=200),
                   sort: Literal['id', '-id', 'nome', '-nome'] = 'id', filter: str = Query('', max_length=160)):
        return app.state.registry.listing(tenant, 'areas', page, size, sort, filter, site=site_id)

    return app


app = create_app()
