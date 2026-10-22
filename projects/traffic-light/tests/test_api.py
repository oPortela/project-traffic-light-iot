import time
import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture(autouse=True)
def standalone(monkeypatch):
    monkeypatch.delenv('MQTT_HOST', raising=False)


class TestApi:
    def setup_method(self):
        self.client = TestClient(app)
        self.client.post('/api/control', json={'action': 'reset'})

    def test_page_and_assets(self):
        for path in ['/', '/static/app.js', '/static/style.css']:
            assert self.client.get(path).status_code == 200

    def test_controls_and_configuration(self):
        config = {'wait': 2, 'crossing': 3, 'roi': [0, 0, 1, 1]}
        assert self.client.post('/api/config', json=config).status_code == 200
        assert self.client.post('/api/control', json={'action':'start'}).json()['running']
        assert self.client.post('/api/config', json=config).status_code == 409
        assert self.client.post('/api/control', json={'action':'presence','presence':True}).json()['presence']
        assert not self.client.post('/api/control', json={'action':'stop'}).json()['running']
        config['roi'] = [0.8, 0, 0.2, 1]
        assert self.client.post('/api/config', json=config).status_code == 422

    def test_invalid_actions(self):
        assert self.client.post('/api/control', json={'action':'oops'}).status_code == 400
        assert self.client.post('/api/control', json={'action':'start','mode':'oops'}).status_code == 400

    def test_websocket(self):
        with self.client.websocket_connect('/ws') as ws:
            assert ws.receive_json()['phase'] == 'idle'

    def test_demo_advances_without_websocket_or_camera(self):
        with TestClient(app) as client:
            client.post('/api/config', json={'wait':1, 'crossing':2, 'roi':[0,0,1,1]})
            client.post('/api/control', json={'action':'start'})
            client.post('/api/control', json={'action':'presence','presence':True})
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                result = client.get('/api/state').json()
                if result['phase'] == 'yellow':
                    break
                time.sleep(.1)
            assert result['phase'] == 'yellow'
            result = client.post('/api/control', json={'action':'stop'}).json()
            assert result['waited'] == 0
            assert not result['presence']

    def test_remote_configuration_merges_only_desired_difference(self, monkeypatch):
        from unittest.mock import Mock
        callbacks = {}

        def publisher(identity, on_command, on_reconnect):
            callbacks['command'] = on_command
            return Mock()

        monkeypatch.setenv('MQTT_HOST', 'unused-test-broker')
        monkeypatch.setattr('app.integration.MqttPublisher', publisher)
        with TestClient(app) as client:
            client.post('/api/control', json={'action': 'stop'})
            client.post('/api/config', json={'wait': 10, 'crossing': 12, 'roi': [.1, .2, .8, .9]})
            callbacks['command']({'acao': 'config', 'parametros': {'wait': 15}})
            from app.main import controller, state
            assert controller.settings.wait == 15
            assert controller.settings.crossing == 12
            assert state['roi'] == [.1, .2, .8, .9]
