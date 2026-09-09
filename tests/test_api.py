import unittest
import time
from fastapi.testclient import TestClient
from app.main import app


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.client.post('/api/control', json={'action': 'reset'})

    def test_page_and_assets(self):
        for path in ['/', '/static/app.js', '/static/style.css']:
            self.assertEqual(self.client.get(path).status_code, 200)

    def test_controls_and_configuration(self):
        config = {'wait': 2, 'crossing': 3, 'roi': [0, 0, 1, 1]}
        self.assertEqual(self.client.post('/api/config', json=config).status_code, 200)
        self.assertTrue(self.client.post('/api/control', json={'action':'start'}).json()['running'])
        self.assertEqual(self.client.post('/api/config', json=config).status_code, 409)
        self.assertTrue(self.client.post('/api/control', json={'action':'presence','presence':True}).json()['presence'])
        self.assertFalse(self.client.post('/api/control', json={'action':'stop'}).json()['running'])
        config['roi'] = [0.8, 0, 0.2, 1]
        self.assertEqual(self.client.post('/api/config', json=config).status_code, 422)

    def test_invalid_actions(self):
        self.assertEqual(self.client.post('/api/control', json={'action':'oops'}).status_code, 400)
        self.assertEqual(self.client.post('/api/control', json={'action':'start','mode':'oops'}).status_code, 400)

    def test_websocket(self):
        with self.client.websocket_connect('/ws') as ws:
            self.assertEqual(ws.receive_json()['phase'], 'idle')

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
            self.assertEqual(result['phase'], 'yellow')
            result = client.post('/api/control', json={'action':'stop'}).json()
            self.assertEqual(result['waited'], 0)
            self.assertFalse(result['presence'])
