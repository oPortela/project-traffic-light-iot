"""PostGIS area boundaries, isolated by tenant and explicit site/area keys."""
import json
import os

import psycopg
from psycopg.rows import dict_row


class GeometryStore:
    def connect(self):
        if os.environ.get('GEO_DATABASE_URL'):
            return psycopg.connect(os.environ['GEO_DATABASE_URL'], row_factory=dict_row, connect_timeout=5)
        return psycopg.connect(
                              host=os.environ.get('GEO_PGHOST', 'geo-db'),
                              dbname=os.environ.get('GEO_PGDATABASE', 'geometry'),
                              user=os.environ.get('GEO_PGUSER', 'iot'),
                              password=os.environ.get('GEO_PGPASSWORD'),
                              row_factory=dict_row, connect_timeout=5)

    def initialize(self):
        with self.connect() as conn:
            conn.execute('SELECT pg_advisory_xact_lock(74189324)')
            conn.execute('CREATE EXTENSION IF NOT EXISTS postgis')
            conn.execute('CREATE TABLE IF NOT EXISTS area_geometries ('
                         'tenant text NOT NULL,site text NOT NULL,area text NOT NULL,'
                         'boundary geometry(Geometry,4326) NOT NULL,PRIMARY KEY(tenant,site,area))')
            conn.execute('CREATE INDEX IF NOT EXISTS area_geometries_spatial ON area_geometries USING gist(boundary)')

    def put(self, tenant, site, area, geometry):
        if geometry.get('type') not in ('Polygon', 'MultiPolygon'):
            raise ValueError('Use Polygon ou MultiPolygon GeoJSON')
        if set(geometry) - {'type', 'coordinates'}:
            raise ValueError('Envie somente a geometria GeoJSON')
        raw = json.dumps(geometry, allow_nan=False)
        if len(raw) > 65536:
            raise ValueError('Geometria muito grande')
        try:
            with self.connect() as conn:
                valid = conn.execute('WITH shape AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(%s),4326) AS g) '
                                     'SELECT ST_IsValid(g) AND NOT ST_IsEmpty(g) AND ST_NDims(g)=2 '
                                     'AND ST_XMin(g)>=-180 AND ST_XMax(g)<=180 '
                                     'AND ST_YMin(g)>=-90 AND ST_YMax(g)<=90 AS valid FROM shape', (raw,)).fetchone()
                if not valid['valid']:
                    raise ValueError('Geometria invalida ou fora das coordenadas WGS84')
                conn.execute('INSERT INTO area_geometries(tenant,site,area,boundary) '
                             'VALUES(%s,%s,%s,ST_SetSRID(ST_GeomFromGeoJSON(%s),4326)) '
                             'ON CONFLICT(tenant,site,area) DO UPDATE SET boundary=EXCLUDED.boundary',
                             (tenant, site, area, raw))
        except (psycopg.DataError, psycopg.InternalError) as exc:
            raise ValueError('Geometria GeoJSON invalida') from exc
        return {'site': site, 'area': area, 'geometry': geometry}

    def collection(self, tenant, page, size):
        with self.connect() as conn:
            total = conn.execute('SELECT count(*) AS n FROM area_geometries WHERE tenant=%s', (tenant,)).fetchone()['n']
            rows = conn.execute('SELECT site,area,ST_AsGeoJSON(boundary)::json AS geometry FROM area_geometries '
                                'WHERE tenant=%s ORDER BY site,area LIMIT %s OFFSET %s',
                                (tenant, size, (page - 1) * size)).fetchall()
        return {'type': 'FeatureCollection', 'page': page, 'size': size, 'total': total,
                'features': [{'type': 'Feature', 'id': row['site'] + '/' + row['area'],
                              'properties': {'site': row['site'], 'area': row['area']}, 'geometry': row['geometry']}
                             for row in rows]}
