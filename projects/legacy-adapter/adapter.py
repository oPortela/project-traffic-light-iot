"""Map numeric legacy fields to canonical telemetry without forwarding arbitrary data."""
import json
import os
import sys
from pathlib import Path

import httpx

from iot_shared.canonical import envelope


def convert(source, config):
    measures = {}
    for name, mapping in config['campos'].items():
        value = source
        for segment in mapping['origem'].split('.'):
            value = value[segment]
        if type(value) not in (float, int):
            raise ValueError('Mapped values must be numeric')
        measures[name] = {'valor': value * mapping.get('escala', 1) + mapping.get('offset', 0),
                          'unidade': mapping['unidade']}
    return envelope(config['identidade'], 'telemetria', measures)


def main():
    config = json.loads(Path(os.environ['ADAPTER_CONFIG']).read_text(encoding='utf-8'))
    token = Path(os.environ['DEVICE_TOKEN_FILE']).read_text().strip()
    with httpx.Client(base_url=os.environ['INGESTION_URL'], timeout=10) as client:
        for line in sys.stdin:
            message = convert(json.loads(line), config)
            response = client.post('/api/v1/ingestao', json=message, headers={'Authorization': 'Bearer ' + token})
            response.raise_for_status()
            print(json.dumps(response.json()), flush=True)


if __name__ == '__main__':
    main()
