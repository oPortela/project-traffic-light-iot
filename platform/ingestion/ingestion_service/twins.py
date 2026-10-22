"""Persist desired state and retry configuration until the device reports convergence."""
from datetime import timedelta
import json

from psycopg.types.json import Jsonb

from .pipeline import Rejected, check_profile


def set_desired(repo, tenant, device, desired):
    json.dumps(desired, allow_nan=False)
    if not desired or len(desired) > 100:
        raise ValueError('Estado desejado vazio ou muito grande')
    with repo.connect() as conn:
        profile = conn.execute('SELECT p.campos,p.configuraveis FROM registry_devices d JOIN registry_profiles p '
                               'ON p.tenant=d.tenant AND p.id=d.perfil WHERE d.tenant=%s AND d.id=%s '
                               'AND d.revoked_at IS NULL FOR UPDATE OF d', (tenant, device)).fetchone()
        if profile is None:
            raise LookupError('Dispositivo nao encontrado')
        if set(desired) - set(profile['configuraveis']):
            raise ValueError('Campo nao configuravel no perfil')
        try:
            check_profile({'tipo': 'estado', 'dados': desired}, {}, profile['campos'])
        except Rejected as exc:
            raise ValueError('Valor de configuracao invalido') from exc
        return conn.execute('INSERT INTO device_twins(tenant,device,desired,updated_at) VALUES (%s,%s,%s,%s) '
                            'ON CONFLICT(tenant,device) DO UPDATE SET desired=EXCLUDED.desired,'
                            'revision=device_twins.revision+1,updated_at=EXCLUDED.updated_at,last_sent=NULL,attempts=0 '
                            'RETURNING device,desired,revision,updated_at',
                            (tenant, device, Jsonb(desired), repo.clock())).fetchone()


def get_twin(repo, tenant, device):
    if repo.get_device(tenant, device) is None:
        raise LookupError('Dispositivo nao encontrado')
    with repo.connect() as conn:
        twin = conn.execute('SELECT desired,revision,updated_at,last_sent,attempts FROM device_twins '
                            'WHERE tenant=%s AND device=%s', (tenant, device)).fetchone()
        state = conn.execute("SELECT dados,timestamp FROM ultimo_estado WHERE inquilino=%s AND dispositivo=%s "
                             "AND tipo='estado'", (tenant, device)).fetchone()
    reported = state['dados'] if state else {}
    desired = twin['desired'] if twin else {}
    return {'dispositivo': device, 'desejado': desired, 'relatado': reported,
            'revisao': twin['revision'] if twin else 0,
            'pendente': any(reported.get(key) != value for key, value in desired.items()),
            'ultimo_relato': state['timestamp'] if state else None}


def dispatch_twins(repo, sender):
    now = repo.clock()
    with repo.connect() as conn:
        rows = conn.execute('SELECT t.*,d.site,d.last_seen,p.dominio,s.dados AS reported,s.timestamp AS reported_at '
                            'FROM device_twins t '
                            'JOIN registry_devices d ON d.tenant=t.tenant AND d.id=t.device '
                            'JOIN registry_profiles p ON p.tenant=d.tenant AND p.id=d.perfil '
                            "LEFT JOIN ultimo_estado s ON s.inquilino=t.tenant AND s.dispositivo=t.device AND s.tipo='estado' "
                            'WHERE d.revoked_at IS NULL AND (t.last_sent IS NULL OR t.last_sent<%s) '
                            'ORDER BY t.updated_at LIMIT 100 FOR UPDATE OF t SKIP LOCKED',
                            (now - timedelta(seconds=30),)).fetchall()
        sent = 0
        for row in rows:
            difference = {key: value for key, value in row['desired'].items()
                          if (row['reported'] or {}).get(key) != value}
            if not difference:
                continue
            job = {**row, 'id': f"twin:{row['tenant']}:{row['device']}:{row['revision']}:{row['reported_at']}",
                   'action': {'tipo': 'comando', 'dados': {'acao': 'config', 'parametros': difference}}}
            sender(job, {})
            conn.execute('UPDATE device_twins SET last_sent=%s,attempts=attempts+1 WHERE tenant=%s AND device=%s',
                         (now, row['tenant'], row['device']))
            sent += 1
    return sent
