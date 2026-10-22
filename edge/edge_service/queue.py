"""Encrypted SQLite WAL queue. Returning from put means the transaction committed."""
import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager, nullcontext

from cryptography.fernet import Fernet

from iot_shared.canonical import validate


class Queue:
    def __init__(self, path, key, *, clock=time.time, capacity=1000000):
        self.path, self.cipher, self.clock, self.capacity = str(path), Fernet(key), clock, capacity
        with self.connect() as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('CREATE TABLE IF NOT EXISTS queue ('
                         'route TEXT NOT NULL,id TEXT NOT NULL,fingerprint TEXT NOT NULL,payload BLOB NOT NULL,'
                         'created REAL NOT NULL,priority INTEGER NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,'
                         'retry_at REAL NOT NULL DEFAULT 0,error TEXT,quarantined INTEGER NOT NULL DEFAULT 0,'
                         'PRIMARY KEY(route,id))')
            conn.execute('CREATE INDEX IF NOT EXISTS queue_ready ON queue(quarantined,retry_at,priority,created)')

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA synchronous=FULL')
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def put(self, route, message, *, priority=0, transaction=None):
        validate(message)
        raw = json.dumps(message, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        fingerprint = hashlib.sha256(raw).hexdigest()
        with (nullcontext(transaction) if transaction is not None else self.connect()) as conn:
            if not conn.in_transaction:
                conn.execute('BEGIN IMMEDIATE')
            old = conn.execute('SELECT fingerprint FROM queue WHERE route=? AND id=?',
                               (route, message['id_mensagem'])).fetchone()
            if old:
                if old['fingerprint'] != fingerprint:
                    raise ValueError('Message identifier reused with different content')
                return False
            if conn.execute('SELECT count(*) FROM queue').fetchone()[0] >= self.capacity:
                raise BufferError('Queue capacity reached; MQTT message must remain unacknowledged')
            conn.execute('INSERT INTO queue(route,id,fingerprint,payload,created,priority) VALUES (?,?,?,?,?,?)',
                         (route, message['id_mensagem'], fingerprint, self.cipher.encrypt(raw), self.clock(), priority))
        return True

    def pending(self, limit=100):
        with self.connect() as conn:
            first = conn.execute('SELECT route FROM queue WHERE quarantined=0 AND retry_at<=? '
                                 'ORDER BY priority DESC,created,id LIMIT 1', (self.clock(),)).fetchone()
            if first is None:
                return []
            rows = conn.execute('SELECT * FROM queue WHERE route=? AND quarantined=0 AND retry_at<=? '
                                'ORDER BY priority DESC,created,id LIMIT ?',
                                (first['route'], self.clock(), min(limit, 5000))).fetchall()
        return [{**dict(row), 'message': json.loads(self.cipher.decrypt(row['payload']))} for row in rows]

    def confirmed(self, row):
        with self.connect() as conn:
            conn.execute('DELETE FROM queue WHERE route=? AND id=? AND fingerprint=?',
                         (row['route'], row['id'], row['fingerprint']))

    def failed(self, row, code, *, permanent=False):
        with self.connect() as conn:
            conn.execute('UPDATE queue SET attempts=attempts+1,retry_at=?,error=?,quarantined=? '
                         'WHERE route=? AND id=?',
                         (self.clock() + min(300, 2 ** min(row['attempts'] + 1, 9)), code,
                          int(permanent), row['route'], row['id']))

    def stats(self):
        with self.connect() as conn:
            row = conn.execute('SELECT count(*) AS total,coalesce(sum(quarantined),0) AS quarentena,'
                               'min(created) AS oldest FROM queue').fetchone()
        return {**dict(row), 'idade_mais_antiga_s': max(0, self.clock() - row['oldest']) if row['oldest'] else 0}
