"""Generate local edge secrets using a saved registry device creation response."""
import argparse
import base64
import hashlib
import json
import secrets
from pathlib import Path

from cryptography.fernet import Fernet


def password(username, token):
    salt = secrets.token_bytes(12)
    hashed = hashlib.pbkdf2_hmac('sha512', token.encode(), salt, 100000, dklen=64)
    return username + ':$7$100000$' + base64.b64encode(salt).decode() + '$' + base64.b64encode(hashed).decode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device-file', required=True)
    parser.add_argument('--central', default='http://host.docker.internal:8002')
    parser.add_argument('--output', default='deploy/secrets')
    args = parser.parse_args()
    device = json.loads(Path(args.device_file).read_text(encoding='utf-8'))
    base, credential = device['topico_base'], device['credencial']
    tenant, site, domain, identifier = base.split('/')
    reader = secrets.token_urlsafe(32)
    config = {'id': 'edge-' + identifier, 'central': args.central,
              'mqtt': {'usuario': 'edge_reader', 'token': reader},
              'dispositivos': {base: {'token': credential['token']}}}
    soil = {**credential, 'identidade': {'inquilino': tenant, 'site': site,
                                       'dominio': domain, 'dispositivo': identifier}}
    acl = '\n'.join(['user edge_reader', 'topic read ' + base + '/#', 'topic write ' + base + '/confirmacao',
                     'topic write ' + base + '/comando', '', 'user ' + credential['usuario'],
                     'topic read ' + base + '/confirmacao', 'topic read ' + base + '/comando',
                     *['topic write ' + base + '/' + kind for kind in ('telemetria', 'evento', 'estado')]]) + '\n'
    files = {'edge-config.json': json.dumps(config, indent=2), 'soil-config.json': json.dumps(soil, indent=2),
             'edge.key': Fernet.generate_key().decode(), 'edge-acl': acl,
             'edge-passwords': password('edge_reader', reader) + '\n' +
             password(credential['usuario'], credential['token']) + '\n'}
    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=True)
    if any((root / name).exists() for name in files):
        raise FileExistsError('Edge secrets already exist; refusing to rotate queue key or credentials')
    for name, content in files.items():
        with (root / name).open('x', encoding='utf-8') as output:
            output.write(content)
    print('Edge secrets created. Preserve the encryption key with encrypted queue backups.')


if __name__ == '__main__':
    main()
