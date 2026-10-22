"""OIDC access-token verification; tenancy is a signed claim, never a query parameter."""
import os
import re

import jwt
from fastapi import HTTPException

from .security import Administrators

ROLES = {'administrador', 'gestor', 'operador', 'integrador', 'leitor'}


class Oidc:
    def __init__(self, issuer, audience, tenants, jwks_url=None, key_client=None):
        self.issuer, self.audience, self.tenants = issuer, audience, tenants
        self.keys = key_client or jwt.PyJWKClient(jwks_url or issuer + '/protocol/openid-connect/certs', timeout=5)

    def authenticate(self, credentials, method='GET', path=''):
        if credentials is None:
            raise HTTPException(401, 'Token OIDC necessario')
        try:
            key = self.keys.get_signing_key_from_jwt(credentials.credentials).key
            claims = jwt.decode(credentials.credentials, key, algorithms=['RS256'], audience=self.audience,
                                issuer=self.issuer, options={'require': ['exp', 'iat', 'sub', 'iss', 'aud']})
            tenant = claims['inquilino']
            roles = set(claims.get('realm_access', {}).get('roles', [])) & ROLES
            if not isinstance(tenant, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', tenant):
                raise ValueError('Invalid tenant claim')
        except (jwt.PyJWTError, KeyError, ValueError, TypeError):
            raise HTTPException(401, 'Token OIDC invalido') from None
        if tenant not in self.tenants or not roles:
            raise HTTPException(403, 'Inquilino ou papel nao autorizado')
        allowed = ROLES if method in ('GET', 'HEAD') else {'administrador', 'gestor', 'integrador'}
        if path.endswith('/reconhecer'):
            allowed = {'administrador', 'gestor', 'operador'}
        if method == 'DELETE':
            allowed = {'administrador', 'gestor'}
        if not roles & allowed:
            raise HTTPException(403, 'Papel sem permissao para esta operacao')
        return tenant


def configured_auth():
    issuer = os.environ.get('OIDC_ISSUER')
    if issuer:
        tenants = set(filter(None, os.environ.get('IOT_TENANTS', '').split(',')))
        if not tenants:
            raise ValueError('IOT_TENANTS is required in OIDC mode')
        return Oidc(issuer, os.environ.get('OIDC_AUDIENCE', 'iot-api'), tenants, os.environ.get('OIDC_JWKS_URL'))
    return Administrators.from_file(os.environ['REGISTRY_ADMINS_FILE'])


def authorize(auth, credentials, request):
    if isinstance(auth, Oidc):
        return auth.authenticate(credentials, request.method, request.url.path)
    return auth.authenticate(credentials)
