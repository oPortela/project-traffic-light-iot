import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from registry_service.api import create_app
from registry_service.repository import Registry
from registry_service.security import Administrators


@pytest.fixture
def registry():
    dsn = os.environ.get('TEST_REGISTRY_DATABASE_URL')
    if not dsn:
        pytest.skip('Set TEST_REGISTRY_DATABASE_URL to a disposable PostgreSQL database')
    now = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    repo = Registry(dsn, clock=lambda: now[0])
    repo.test_now = now
    return repo


@pytest.fixture
def setup(registry):
    tenant = 'test_' + uuid4().hex
    other = 'test_' + uuid4().hex
    tokens = ['a' * 40, 'b' * 40]
    admins = Administrators([{'inquilino': tenant, 'token': tokens[0]}, {'inquilino': other, 'token': tokens[1]}])
    with TestClient(create_app(registry, admins)) as client:
        client.headers['Authorization'] = 'Bearer ' + tokens[0]
        yield client, registry, tenant, other, {'Authorization': 'Bearer ' + tokens[1]}
    # Remove only the two random tenants created by this test, never truncate a shared DB.
    with registry.connect() as conn:
        for table in ('registry_devices', 'registry_areas', 'registry_sites', 'registry_profiles',
                      'registry_domains', 'registry_tenants'):
            from psycopg import sql
            column = 'id' if table == 'registry_tenants' else 'tenant'
            conn.execute(sql.SQL('DELETE FROM {} WHERE {}=ANY(%s)').format(sql.Identifier(table),
                         sql.Identifier(column)), ([tenant, other],))
