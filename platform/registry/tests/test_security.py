import base64
import hashlib

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from registry_service.security import Administrators, digest, new_credential


def test_token_hash_is_mosquitto_compatible_and_salted():
    token, fingerprint, hashed = new_credential()
    _, algorithm, iterations, salt, expected = hashed.split('$')
    assert algorithm == '7'
    assert fingerprint == digest(token)
    calculated = hashlib.pbkdf2_hmac('sha512', token.encode(), base64.b64decode(salt), int(iterations), dklen=64)
    assert calculated == base64.b64decode(expected)
    assert new_credential()[2] != hashed


@pytest.mark.parametrize('entries', [[], [{'inquilino': 'semob', 'token': 'short'}],
                                   [{'inquilino': 'a', 'token': 'a'*40}, {'inquilino': 'b', 'token': 'a'*40}]])
def test_bad_admin_config_fails_closed(entries):
    with pytest.raises(ValueError):
        Administrators(entries)


def test_admin_credential_binds_one_tenant():
    admins = Administrators([{'inquilino': 'semob', 'token': 'a'*40}])
    assert admins.authenticate(HTTPAuthorizationCredentials(scheme='Bearer', credentials='a'*40)) == 'semob'
    with pytest.raises(HTTPException):
        admins.authenticate(None)
