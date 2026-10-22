import os
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from registry_service.security import bearer
from iot_shared.observability import instrument
from iot_shared.contracts import publish_contracts

from .pipeline import Ingestion, Rejected


class Batch(BaseModel):
    mensagens: Annotated[list[Any], Field(min_length=1, max_length=5000)]


def create_app(ingestion=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.ingestion = ingestion or Ingestion(os.environ.get('REGISTRY_DATABASE_URL', ''))
        app.state.ingestion.initialize_ingestion()
        yield

    app = FastAPI(title='Plataforma IoT — Ingestão', version='1.0.0', lifespan=lifespan)
    instrument(app, 'ingestion')
    publish_contracts(app)

    def device_token(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        if credentials is None:
            raise HTTPException(401, 'Token de dispositivo necessário')
        return credentials.credentials

    @app.exception_handler(Rejected)
    async def rejected(request, error):
        return JSONResponse(status_code=error.status, content={'erros': error.errors})

    @app.get('/health', include_in_schema=False)
    def health():
        with app.state.ingestion.connect() as conn:
            conn.execute('SELECT 1')
        return {'status': 'ok'}

    @app.post('/api/v1/ingestao', status_code=202)
    def receive(message: dict, token: str = Depends(device_token)):
        return app.state.ingestion.receive(message, token=token)

    @app.post('/api/v1/ingestao/lote', status_code=202)
    def batch(body: Batch, token: str = Depends(device_token)):
        results = []
        for index, message in enumerate(body.mensagens):
            try:
                result = app.state.ingestion.receive(message, token=token)
            except Rejected as exc:
                result = {'status': 'rejeitada', 'http_status': exc.status, 'erros': exc.errors}
            results.append({'indice': index, **result})
        return {'resultados': results}

    return app


app = create_app()
