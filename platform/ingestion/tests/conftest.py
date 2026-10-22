import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from psycopg import sql

from ingestion_service.pipeline import Ingestion
from registry_service.api import DEFAULT_SEED
from registry_service.models import Device, Named


@pytest.fixture
def ingested():
    dsn = os.environ.get('TEST_REGISTRY_DATABASE_URL')
    if not dsn:
        pytest.skip('TEST_REGISTRY_DATABASE_URL is required')
    clock = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    repo = Ingestion(dsn, clock=lambda: clock[0])
    tenant = 'ingest_' + uuid4().hex
    repo.initialize([tenant], DEFAULT_SEED)
    repo.initialize_ingestion()
    repo.create(tenant, 'sites', Named(id='site', nome='Site'))
    repo.create(tenant, 'areas', Named(id='area', nome='Area'), site='site')
    device = repo.create_device(tenant, Device(id='device', nome='Device', site='site', area='area', perfil='semaforo-v1'))
    yield repo, tenant, device['credencial']['token'], clock
    with repo.connect() as conn:
        if conn.execute("SELECT to_regclass('processing_alarms') AS name").fetchone()['name']:
            if conn.execute("SELECT to_regclass('device_twins') AS name").fetchone()['name']:
                conn.execute('DELETE FROM device_twins WHERE tenant=%s', (tenant,))
            conn.execute('DELETE FROM processing_actions WHERE alarm_id IN '
                         '(SELECT id FROM processing_alarms WHERE tenant=%s)', (tenant,))
            conn.execute('DELETE FROM processing_alarms WHERE tenant=%s', (tenant,))
            conn.execute('DELETE FROM processing_rules WHERE tenant=%s', (tenant,))
            conn.execute('DELETE FROM storage_processed WHERE tenant=%s', (tenant,))
            conn.execute('DELETE FROM telemetria WHERE inquilino=%s', (tenant,))
            conn.execute('DELETE FROM ultimo_estado WHERE inquilino=%s', (tenant,))
        for table in ('ingest_dead_letters', 'ingest_messages', 'registry_devices', 'registry_areas',
                      'registry_sites', 'registry_profiles', 'registry_domains', 'registry_tenants'):
            column = 'id' if table == 'registry_tenants' else 'tenant'
            conn.execute(sql.SQL('DELETE FROM {} WHERE {}=%s').format(sql.Identifier(table),
                         sql.Identifier(column)), (tenant,))
