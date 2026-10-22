"""Publish only committed messages; replays use stable NATS deduplication IDs."""
import asyncio
import json
import logging
import os
from datetime import datetime, timezone

import nats
from nats.js.errors import NotFoundError

from .pipeline import Ingestion
from iot_shared.observability import worker_metrics, MESSAGES


async def ensure_stream(js):
    try:
        await js.stream_info('IOT_INGESTED')
    except NotFoundError:
        await js.add_stream(name='IOT_INGESTED', subjects=['iot.ingested.>'], storage='file')


async def publish_pending(repo, js, limit=100):
    count = 0
    # Lock rows until broker PubAck; crash after PubAck may resend the same stable ID.
    with repo.connect() as conn:
        rows = conn.execute('SELECT tenant,id,envelope,context FROM ingest_messages WHERE published_at IS NULL '
                            'ORDER BY received_at LIMIT %s FOR UPDATE SKIP LOCKED', (limit,)).fetchall()
        for row in rows:
            message = row['envelope']
            await js.publish('iot.ingested.' + row['tenant'] + '.' + message['dispositivo'],
                             json.dumps({'mensagem': message, 'contexto': row['context']}).encode(),
                             headers={'Nats-Msg-Id': row['tenant'] + ':' + str(row['id'])})
            conn.execute('UPDATE ingest_messages SET published_at=%s WHERE tenant=%s AND id=%s',
                         (datetime.now(timezone.utc), row['tenant'], row['id']))
            count += 1
    return count


async def main():
    worker_metrics()
    repo = Ingestion(os.environ.get('REGISTRY_DATABASE_URL', ''))
    repo.initialize_ingestion()
    nc = await nats.connect(os.environ.get('NATS_URL', 'nats://nats:4222'), max_reconnect_attempts=-1)
    js = nc.jetstream()
    await ensure_stream(js)
    try:
        while True:
            try:
                count = await publish_pending(repo, js)
                MESSAGES.labels('published').inc(count)
                if not count:
                    await asyncio.sleep(.2)
            except Exception:
                logging.exception('Outbox publication failed; committed messages retained')
                await asyncio.sleep(2)
    finally:
        await nc.close()


if __name__ == '__main__':
    asyncio.run(main())
