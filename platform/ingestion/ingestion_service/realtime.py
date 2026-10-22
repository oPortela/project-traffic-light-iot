"""Authenticated tenant snapshots over WebSocket; tokens never appear in URLs."""
import asyncio
import os
from pathlib import Path

from fastapi import HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials


def attach(app):
    portal = Path(__file__).resolve().parents[2] / 'portal'

    @app.get('/', include_in_schema=False)
    @app.get('/callback', include_in_schema=False)
    def index():
        return FileResponse(portal / 'index.html', headers={'Cache-Control': 'no-store'})

    @app.get('/portal-config', include_in_schema=False)
    def configuration():
        return {'issuer': os.environ.get('OIDC_ISSUER'), 'client_id': 'iot-portal',
                'mapa': os.environ.get('GEO_ENABLED') == 'true'}

    def snapshot(tenant):
        with app.state.storage.connect() as conn:
            states = conn.execute('SELECT dispositivo,tipo,timestamp,dados FROM ultimo_estado WHERE inquilino=%s '
                                  'ORDER BY timestamp DESC,dispositivo LIMIT 100', (tenant,)).fetchall()
            alarms = conn.execute("SELECT id,device,status,severity,occurred_at FROM processing_alarms "
                                  "WHERE tenant=%s AND status!='resolvido' ORDER BY occurred_at DESC LIMIT 100",
                                  (tenant,)).fetchall()
        # Convert timestamps and UUIDs explicitly through FastAPI's canonical encoder.
        from fastapi.encoders import jsonable_encoder
        return jsonable_encoder({'tipo': 'snapshot', 'estados': states, 'alarmes': alarms})

    @app.websocket('/ws')
    async def websocket(websocket: WebSocket):
        allowed = set(os.environ.get('PORTAL_ORIGINS', 'https://portal.localhost:8443,http://127.0.0.1:8003').split(','))
        if websocket.headers.get('origin') and websocket.headers['origin'] not in allowed:
            await websocket.close(code=1008)
            return
        await websocket.accept()
        try:
            authentication = await asyncio.wait_for(websocket.receive_json(), timeout=5)
            credential = HTTPAuthorizationCredentials(scheme='Bearer', credentials=authentication['token'])
            while True:
                # Revalidate expiry on every snapshot; a socket cannot outlive token authorization.
                tenant = await asyncio.to_thread(app.state.administrators.authenticate, credential)
                await websocket.send_json(await asyncio.to_thread(snapshot, tenant))
                await asyncio.sleep(2)
        except (HTTPException, KeyError, ValueError, TypeError, asyncio.TimeoutError):
            await websocket.close(code=1008)
        except WebSocketDisconnect:
            pass
