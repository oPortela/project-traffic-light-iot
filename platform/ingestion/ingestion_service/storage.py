"""Idempotent JetStream storage consumer; ACK follows the PostgreSQL transaction."""
import asyncio
import json
import logging
import os
from pathlib import Path

import nats
from nats.errors import TimeoutError as NatsTimeout
from psycopg.types.json import Jsonb

from .outbox import ensure_stream
from .pipeline import Ingestion
from iot_shared.observability import MESSAGES, PERSISTENCE, worker_metrics


class Storage(Ingestion):
    def initialize_storage(self):
        with self.connect() as conn:
            conn.execute('SELECT pg_advisory_xact_lock(74189322)')
            conn.execute(Path(__file__).with_name('storage.sql').read_text(encoding='utf-8'))
            conn.execute(Path(__file__).with_name('rules.sql').read_text(encoding='utf-8'))
            conn.execute(Path(__file__).with_name('twins.sql').read_text(encoding='utf-8'))
            if conn.execute("SELECT 1 FROM pg_extension WHERE extname='timescaledb'").fetchone():
                conn.execute("SELECT create_hypertable('telemetria', 'time', if_not_exists => TRUE, migrate_data => TRUE)")

    def persist(self, tenant, message_id):
        with self.connect() as conn:
            row = conn.execute('SELECT * FROM ingest_messages WHERE tenant=%s AND id=%s FOR UPDATE',
                               (tenant, message_id)).fetchone()
            if row is None:
                raise ValueError('Message is not in the authenticated inbox')
            inserted = conn.execute('INSERT INTO storage_processed (tenant,id,processed_at) VALUES (%s,%s,%s) '
                                    'ON CONFLICT DO NOTHING RETURNING id',
                                    (tenant, message_id, self.clock())).fetchone()
            if not inserted:
                return False
            message, context = row['envelope'], row['context']
            if message['tipo'] == 'telemetria':
                with conn.cursor() as cursor:
                    cursor.executemany('INSERT INTO telemetria (time,id_mensagem,dispositivo,grandeza,valor,unidade,'
                                       'inquilino,site,area,dominio,flags) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) '
                                       'ON CONFLICT DO NOTHING', [
                        (row['measured_at'], message_id, row['device'], name, measure['valor'], measure['unidade'],
                         tenant, message['site'], context['area'], message['dominio'],
                         Jsonb({'atrasado': context['atrasado'], 'suspeita': name in context['suspeitas']}))
                        for name, measure in message['dados'].items()
                    ])
            conn.execute('INSERT INTO ultimo_estado (inquilino,dispositivo,tipo,timestamp,dados) VALUES (%s,%s,%s,%s,%s) '
                         'ON CONFLICT(inquilino,dispositivo,tipo) DO UPDATE SET timestamp=EXCLUDED.timestamp,'
                         'dados=ultimo_estado.dados || EXCLUDED.dados WHERE ultimo_estado.timestamp<=EXCLUDED.timestamp',
                         (tenant, row['device'], message['tipo'], row['measured_at'], Jsonb(message['dados'])))
            from .rules import evaluate_message
            evaluate_message(conn, tenant, row['device'], message, context, row['measured_at'], self.clock())
        return True


async def main():
    worker_metrics()
    repo = Storage(os.environ.get('REGISTRY_DATABASE_URL', ''))
    repo.initialize_storage()
    nc = await nats.connect(os.environ.get('NATS_URL', 'nats://nats:4222'), max_reconnect_attempts=-1)
    js = nc.jetstream()
    await ensure_stream(js)
    subscription = await js.pull_subscribe('iot.ingested.>', durable='storage-writer')
    try:
        while True:
            try:
                messages = await subscription.fetch(100, timeout=1)
            except NatsTimeout:
                continue
            for incoming in messages:
                try:
                    message = json.loads(incoming.data)['mensagem']
                    await asyncio.to_thread(repo.persist, message['inquilino'], message['id_mensagem'])
                    MESSAGES.labels('stored').inc()
                    with repo.connect() as conn:
                        received = conn.execute('SELECT received_at FROM ingest_messages WHERE tenant=%s AND id=%s',
                                                (message['inquilino'], message['id_mensagem'])).fetchone()
                    PERSISTENCE.observe(max(0, (repo.clock() - received['received_at']).total_seconds()))
                    logging.getLogger('storage').info('message_stored', extra={'correlation_id': message['id_mensagem']})
                    await incoming.ack()
                except Exception:
                    logging.exception('Storage failure; message will be redelivered')
                    await incoming.nak(delay=2)
    finally:
        await nc.close()


if __name__ == '__main__':
    asyncio.run(main())
