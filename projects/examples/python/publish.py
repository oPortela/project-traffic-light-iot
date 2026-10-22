"""Python standard-library HTTP integration, using a saved device credential."""
import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

device = json.loads(Path(os.environ['DEVICE_FILE']).read_text(encoding='utf-8'))
tenant, site, domain, identifier = device['topico_base'].split('/')
message = {'versao': '1.0', 'id_mensagem': str(uuid4()),
           'timestamp': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
           'inquilino': tenant, 'site': site, 'dominio': domain, 'dispositivo': identifier,
           'tipo': 'telemetria', 'dados': {'umidade_solo': {'valor': 45, 'unidade': '%'}}}
request = urllib.request.Request(os.environ.get('INGESTION_URL', 'http://127.0.0.1:8002') + '/api/v1/ingestao',
                                 data=json.dumps(message).encode(), headers={'Content-Type': 'application/json',
                                 'Authorization': 'Bearer ' + device['credencial']['token']})
with urllib.request.urlopen(request, timeout=10) as response:
    assert response.status == 202
    print(response.read().decode())
