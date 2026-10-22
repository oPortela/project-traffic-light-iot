import time
from types import SimpleNamespace
from unittest.mock import Mock

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from registry_service.oidc import Oidc


@pytest.fixture
def identity():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    client = Mock()
    client.get_signing_key_from_jwt.return_value = SimpleNamespace(key=key.public_key())
    auth = Oidc('https://id.test/realms/iot', 'iot-api', {'tenant'}, key_client=client)

    def token(role='leitor', **overrides):
        claims = {'iss': auth.issuer, 'aud': 'iot-api', 'iat': int(time.time()), 'exp': int(time.time()) + 60,
                  'sub': 'user', 'inquilino': 'tenant', 'realm_access': {'roles': [role]}, **overrides}
        return HTTPAuthorizationCredentials(scheme='Bearer', credentials=jwt.encode(claims, key, algorithm='RS256'))
    return auth, token


def test_read_write_roles_and_signed_tenant(identity):
    auth, token = identity
    assert auth.authenticate(token()) == 'tenant'
    for role in ('administrador', 'gestor', 'integrador'):
        assert auth.authenticate(token(role), 'POST', '/api/v1/regras') == 'tenant'
    assert auth.authenticate(token('operador'), 'POST', '/api/v1/alarmes/a/reconhecer') == 'tenant'
    for credential, method in [(token(), 'POST'), (token('operador'), 'DELETE'),
                               (token(inquilino='other'), 'GET'), (token('unknown'), 'GET')]:
        with pytest.raises(HTTPException) as error:
            auth.authenticate(credential, method)
        assert error.value.status_code == 403


def test_invalid_issuer_audience_expiry_and_missing_tenant(identity):
    auth, token = identity
    for credentials in [None, token(iss='https://evil'), token(aud='another'),
                        token(exp=int(time.time()) - 60), token(inquilino=None)]:
        with pytest.raises(HTTPException) as error:
            auth.authenticate(credentials)
        assert error.value.status_code == 401
