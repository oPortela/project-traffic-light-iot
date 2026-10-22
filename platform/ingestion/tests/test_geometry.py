import os
from uuid import uuid4

import pytest

from ingestion_service.geometry import GeometryStore


def test_postgis_validity_and_tenant_isolation(monkeypatch):
    dsn = os.environ.get('TEST_GEO_DATABASE_URL')
    if not dsn:
        pytest.skip('TEST_GEO_DATABASE_URL is required')
    monkeypatch.setenv('GEO_DATABASE_URL', dsn)
    store = GeometryStore()
    store.initialize()
    tenant = 'geo_' + uuid4().hex
    shape = {'type': 'Polygon', 'coordinates': [[[-49, -16], [-48, -16], [-48, -15], [-49, -16]]]}
    try:
        store.put(tenant, 'site', 'area', shape)
        result = store.collection(tenant, 1, 10)
        assert result['total'] == 1 and result['features'][0]['geometry'] == shape
        assert store.collection(tenant + '_other', 1, 10)['total'] == 0
        for invalid in [{'type': 'Point', 'coordinates': [0, 0]},
                        {'type': 'Polygon', 'coordinates': []},
                        {'type': 'Polygon', 'coordinates': [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]]},
                        {'type': 'Polygon', 'coordinates': [[[200, 0], [201, 0], [201, 1], [200, 0]]]}]:
            with pytest.raises(ValueError):
                store.put(tenant, 'site', 'area', invalid)
    finally:
        with store.connect() as conn:
            conn.execute('DELETE FROM area_geometries WHERE tenant=%s', (tenant,))
