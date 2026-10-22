"""Privileged export of registry credentials to versioned Mosquitto configuration."""
import argparse
import os
import json
from pathlib import Path
from uuid import uuid4

from .repository import Registry


def export(registry, output, service_credentials=None, action_credentials=None):
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    generation = 'generation-' + uuid4().hex
    target = root / generation
    target.mkdir()
    entries = registry.broker_entries()
    passwords, acl = [], ['# Generated from registry; do not edit.']
    if service_credentials:
        service = json.loads(Path(service_credentials).read_text(encoding='utf-8'))
        # A dedicated bridge identity can read but cannot impersonate devices by publishing.
        if service['usuario'] != 'service_ingestion_bridge':
            raise ValueError('Unexpected bridge username')
        import base64
        import hashlib
        import secrets
        salt = secrets.token_bytes(12)
        hashed = hashlib.pbkdf2_hmac('sha512', service['token'].encode(), salt, 100000, dklen=64)
        passwords.append('service_ingestion_bridge:$7$100000$' + base64.b64encode(salt).decode()
                         + '$' + base64.b64encode(hashed).decode())
        acl.extend(['', 'user service_ingestion_bridge'])
        acl.extend('topic read +/+/+/+/' + kind for kind in ('telemetria', 'evento', 'estado'))
    if action_credentials:
        import base64
        import hashlib
        import secrets
        service = json.loads(Path(action_credentials).read_text(encoding='utf-8'))
        if service['usuario'] != 'service_actions' or len(service['token']) < 32:
            raise ValueError('Invalid action service credential')
        salt = secrets.token_bytes(12)
        hashed = hashlib.pbkdf2_hmac('sha512', service['token'].encode(), salt, 100000, dklen=64)
        passwords.append('service_actions:$7$100000$' + base64.b64encode(salt).decode()
                         + '$' + base64.b64encode(hashed).decode())
        acl.extend(['', 'user service_actions', 'topic write +/+/+/+/comando', 'topic write acoes/+/+/#'])
    for entry in entries:
        username = entry['mqtt_username']
        acl.extend(['', 'user ' + username])
        if entry['revoked_at'] is not None:
            acl.append('topic deny #')
            continue
        passwords.append(username + ':' + entry['mqtt_hash'])
        base = '/'.join(entry[key] for key in ('tenant', 'site', 'dominio', 'id'))
        acl.extend('topic write ' + base + '/' + kind for kind in ('telemetria', 'evento', 'estado'))
        acl.append('topic read ' + base + '/comando')
    (target / 'passwords').write_text('\n'.join(passwords) + '\n', encoding='utf-8')
    (target / 'acl').write_text('\n'.join(acl) + '\n', encoding='utf-8')
    # Both files are completed before the single active configuration pointer changes.
    # Mount the directory, not individual files, so atomic replace is visible in Docker.
    config = ('listener 1883\nallow_anonymous false\n'
              f'password_file /mosquitto/registry/{generation}/passwords\n'
              f'acl_file /mosquitto/registry/{generation}/acl\n'
              'persistence true\npersistence_location /mosquitto/data/\n'
              'log_dest stdout\nmessage_size_limit 65536\n')
    pending = root / (generation + '.conf.tmp')
    pending.write_text(config, encoding='utf-8')
    os.replace(pending, root / 'active.conf')
    return generation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--service-credentials', default=os.environ.get('MQTT_BRIDGE_CREDENTIALS'))
    parser.add_argument('--action-credentials', default=os.environ.get('MQTT_ACTION_CREDENTIALS'))
    args = parser.parse_args()
    generation = export(Registry(os.environ.get('REGISTRY_DATABASE_URL', '')), args.output,
                        args.service_credentials, args.action_credentials)
    print(f'Exported {generation}. Restart registry-mosquitto to apply credentials and terminate old sessions.')


if __name__ == '__main__':
    main()
