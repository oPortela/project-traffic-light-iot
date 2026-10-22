"""Configure the tenant attribute as administrator-only in the local Keycloak realm."""
import argparse
import ssl
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='https://auth.localhost:8443')
    parser.add_argument('--password-file', default='deploy/secrets/keycloak-admin-password')
    parser.add_argument('--ca-file', default='deploy/secrets/tls/ca.crt')
    parser.add_argument('--host-header', help='Local gateway hostname when connecting by loopback IP')
    args = parser.parse_args()
    context = ssl.create_default_context(cafile=args.ca_file)
    headers = {'Host': args.host_header} if args.host_header else {}
    with httpx.Client(base_url=args.url, verify=context, timeout=30, headers=headers) as client:
        response = client.post('/realms/master/protocol/openid-connect/token', data={
            'client_id': 'admin-cli', 'grant_type': 'password', 'username': 'bootstrap-admin',
            'password': Path(args.password_file).read_text().strip()})
        response.raise_for_status()
        client.headers['Authorization'] = 'Bearer ' + response.json()['access_token']
        response = client.get('/admin/realms/iot/users/profile')
        response.raise_for_status()
        profile = response.json()
        # Absent policy disables unmanaged attributes; DISABLED is not an API enum value.
        profile.pop('unmanagedAttributePolicy', None)
        profile['attributes'] = [item for item in profile['attributes'] if item['name'] != 'inquilino']
        profile['attributes'].append({'name': 'inquilino', 'displayName': 'Inquilino',
                                      'permissions': {'view': ['admin'], 'edit': ['admin']},
                                      'validations': {'pattern': {'pattern': '^[a-zA-Z0-9_-]{1,64}$'}}})
        response = client.put('/admin/realms/iot/users/profile', json=profile)
        if response.is_error:
            raise RuntimeError('Profile configuration rejected: ' + response.text)
        response.raise_for_status()
    print('Tenant attribute restricted to identity administrators. Assign tenant and role before issuing access.')


if __name__ == '__main__':
    main()
