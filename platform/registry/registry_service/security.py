"""Local bootstrap administrator identities and device credentials."""
import base64
import hashlib
import hmac
import json
import secrets
from pathlib import Path

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import TypeAdapter

from .models import Identifier

bearer = HTTPBearer(auto_error=False)


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def new_credential():
    token = secrets.token_urlsafe(32)
    salt = secrets.token_bytes(12)
    iterations = 100000
    derived = hashlib.pbkdf2_hmac('sha512', token.encode(), salt, iterations, dklen=64)
    encoded = lambda value: base64.b64encode(value).decode()  # noqa: E731
    return token, digest(token), f'$7${iterations}${encoded(salt)}${encoded(derived)}'


class Administrators:
    """A local secret file maps an opaque bearer token to exactly one tenant."""

    def __init__(self, entries):
        self.tokens = {}
        self.tenants = set()
        for entry in entries:
            tenant = TypeAdapter(Identifier).validate_python(entry['inquilino'])
            token = entry['token']
            if not isinstance(token, str) or len(token) < 32:
                raise ValueError('Tokens administrativos devem conter pelo menos 32 caracteres')
            fingerprint = digest(token)
            if fingerprint in self.tokens:
                raise ValueError('Token administrativo repetido')
            self.tokens[fingerprint] = tenant
            self.tenants.add(tenant)
        if not self.tokens:
            raise ValueError('Configure pelo menos um administrador')

    @classmethod
    def from_file(cls, path):
        return cls(json.loads(Path(path).read_text(encoding='utf-8')))

    def authenticate(self, credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        if credentials and credentials.scheme.lower() == 'bearer':
            fingerprint = digest(credentials.credentials)
            for expected, tenant in self.tokens.items():
                if hmac.compare_digest(fingerprint, expected):
                    return tenant
        raise HTTPException(401, 'Credencial administrativa inválida', headers={'WWW-Authenticate': 'Bearer'})
