"""Create local registry administrator secrets without printing bearer tokens."""
import argparse
import json
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'platform/registry'))
from registry_service.security import Administrators  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tenant', action='append', default=[])
    parser.add_argument('--services-only', action='store_true', help='Add missing service secrets without rotating admins')
    parser.add_argument('--output', default='deploy/secrets/registry-admins.json')
    args = parser.parse_args()
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    if args.services_only:
        Administrators.from_file(path)
    else:
        entries = [{'inquilino': tenant, 'token': secrets.token_urlsafe(32)} for tenant in sorted(set(args.tenant))]
        Administrators(entries)
        # Exclusive creation avoids silently rotating live administrator identities.
        with path.open('x', encoding='utf-8') as output:
            json.dump(entries, output, indent=2)
    # Precreate the bind mount as the local user, before Docker could create it as root.
    (path.parent / 'registry-broker').mkdir(exist_ok=True)
    bridge = path.parent / 'mqtt-bridge.json'
    if not bridge.exists():
        with bridge.open('x', encoding='utf-8') as output:
            json.dump({'usuario': 'service_ingestion_bridge', 'token': secrets.token_urlsafe(32)}, output)
    actions = path.parent / 'mqtt-actions.json'
    if not actions.exists():
        with actions.open('x', encoding='utf-8') as output:
            json.dump({'usuario': 'service_actions', 'token': secrets.token_urlsafe(32)}, output)
    print(f'Created {path}. Keep this file private and outside version control.')


if __name__ == '__main__':
    main()
