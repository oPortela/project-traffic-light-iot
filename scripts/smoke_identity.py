"""Temporary service identity verifies signed OIDC tenancy and API RBAC through TLS."""
import argparse
import secrets
import ssl
from pathlib import Path
from uuid import uuid4

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--secrets', default='deploy/secrets')
    args = parser.parse_args()
    root = Path(args.secrets)
    context = ssl.create_default_context(cafile=str(root / 'tls/ca.crt'))
    name, secret = 'smoke-' + uuid4().hex, secrets.token_urlsafe(32)
    with httpx.Client(base_url='https://127.0.0.1:8443', verify=context, timeout=20,
                      headers={'Host': 'auth.localhost:8443'}) as client:
        response = client.post('/realms/master/protocol/openid-connect/token', data={
            'client_id': 'admin-cli', 'grant_type': 'password', 'username': 'bootstrap-admin',
            'password': (root / 'keycloak-admin-password').read_text().strip()})
        response.raise_for_status()
        client.headers['Authorization'] = 'Bearer ' + response.json()['access_token']
        realm = client.get('/admin/realms/iot').json()
        assert realm['browserFlow'] == 'iot-mfa'
        flow = client.get('/admin/realms/iot/authentication/flows/iot-mfa/executions').json()
        assert any(step.get('providerId') == 'auth-otp-form' and step['requirement'] == 'REQUIRED' for step in flow)
        profile = client.get('/admin/realms/iot/users/profile').json()
        tenant_attribute = next(item for item in profile['attributes'] if item['name'] == 'inquilino')
        assert tenant_attribute['permissions']['edit'] == ['admin']
        mappers = [
            {'name': 'tenant', 'protocol': 'openid-connect', 'protocolMapper': 'oidc-hardcoded-claim-mapper',
             'config': {'claim.name': 'inquilino', 'claim.value': 'semob', 'jsonType.label': 'String',
                        'access.token.claim': 'true'}},
            {'name': 'audience', 'protocol': 'openid-connect', 'protocolMapper': 'oidc-audience-mapper',
             'config': {'included.custom.audience': 'iot-api', 'access.token.claim': 'true'}},
            {'name': 'roles', 'protocol': 'openid-connect', 'protocolMapper': 'oidc-usermodel-realm-role-mapper',
             'config': {'claim.name': 'realm_access.roles', 'jsonType.label': 'String', 'multivalued': 'true',
                        'access.token.claim': 'true'}}]
        response = client.post('/admin/realms/iot/clients', json={'clientId': name, 'secret': secret,
            'enabled': True, 'publicClient': False, 'serviceAccountsEnabled': True, 'standardFlowEnabled': False,
            'directAccessGrantsEnabled': False, 'protocolMappers': mappers})
        response.raise_for_status()
        identifier = response.headers['Location'].rsplit('/', 1)[1]
        try:
            account = client.get(f'/admin/realms/iot/clients/{identifier}/service-account-user').json()
            role = client.get('/admin/realms/iot/roles/leitor').json()
            response = client.post(f"/admin/realms/iot/users/{account['id']}/role-mappings/realm", json=[role])
            response.raise_for_status()
            response = client.post('/realms/iot/protocol/openid-connect/token', data={
                'grant_type': 'client_credentials', 'client_id': name, 'client_secret': secret})
            response.raise_for_status()
            token = response.json()['access_token']
            headers = {'Host': 'registry.localhost:8443', 'Authorization': 'Bearer ' + token}
            response = client.get('/api/v1/sites', headers=headers)
            assert response.status_code == 200, response.text
            response = client.post('/api/v1/sites', headers=headers, json={'id': name, 'nome': 'Should be denied'})
            assert response.status_code == 403, response.text
            response = client.get('/metrics', headers=headers)
            assert response.status_code == 404, response.text
            print('TLS, Keycloak TOTP flow, protected tenant attribute and real OIDC read-only role: OK')
        finally:
            response = client.delete('/admin/realms/iot/clients/' + identifier)
            response.raise_for_status()


if __name__ == '__main__':
    main()
