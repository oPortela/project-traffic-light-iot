from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
import pytest

from ingestion_service.query_api import create_app
from registry_service.security import Administrators
from test_storage import prepare, save


def test_websocket_snapshot_is_tenant_scoped_and_portal_has_no_secrets(ingested):
    store, tenant, token, clock = prepare(ingested)
    save(store, tenant, token, clock[0], 8)
    admins = Administrators([{'inquilino': tenant, 'token': 'a'*40}, {'inquilino': 'other', 'token': 'b'*40}])
    with TestClient(create_app(store, admins)) as client:
        assert client.get('/').status_code == 200
        assert 'a'*40 not in client.get('/').text
        with client.websocket_connect('/ws') as socket:
            socket.send_json({'token': 'a'*40})
            snapshot = socket.receive_json()
            assert len(snapshot['estados']) == 1
        with client.websocket_connect('/ws') as socket:
            socket.send_json({'token': 'b'*40})
            assert socket.receive_json()['estados'] == []
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect('/ws') as socket:
                socket.send_json({'token': 'wrong'})
                socket.receive_json()


def test_websocket_rejects_untrusted_browser_origin(ingested):
    store, tenant, token, clock = prepare(ingested)
    admins = Administrators([{'inquilino': tenant, 'token': 'a'*40}])
    with TestClient(create_app(store, admins)) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect('/ws', headers={'Origin': 'https://untrusted.invalid'}):
                pass
