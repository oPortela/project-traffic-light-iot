"""Provision a rural demo and save the one-time credential without printing it."""
import argparse
import json
import os
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--id', default='solo-01')
    parser.add_argument('--output', default='deploy/secrets/solo-device.json')
    args = parser.parse_args()
    destination = Path(args.output)
    if destination.exists():
        raise FileExistsError('Device credential file already exists')
    admin = json.loads(Path(os.environ['REGISTRY_ADMINS_FILE']).read_text(encoding='utf-8'))[0]
    with httpx.Client(base_url=os.environ.get('REGISTRY_URL', 'http://127.0.0.1:8001'),
                      headers={'Authorization': 'Bearer ' + admin['token']}) as client:
        for path, body in [('/api/v1/sites', {'id': 'fazenda', 'nome': 'Fazenda demonstracao'}),
                           ('/api/v1/sites/fazenda/areas', {'id': 'talhao', 'nome': 'Talhao demonstracao'})]:
            response = client.post(path, json=body)
            if response.status_code != 409:
                response.raise_for_status()
        response = client.post('/api/v1/dispositivos', json={'id': args.id, 'nome': 'Sensor de solo',
                               'site': 'fazenda', 'area': 'talhao', 'perfil': 'solo-horario-v1'})
        response.raise_for_status()
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('x', encoding='utf-8') as output:
            json.dump(response.json(), output, indent=2)
    print('Rural device provisioned; credential saved privately to ' + str(destination))


if __name__ == '__main__':
    main()
