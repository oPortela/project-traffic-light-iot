"""Enable Timescale aggregates; raw retention is opt-in and preserves dedup fingerprints."""
import argparse
import os
import sys
from pathlib import Path
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / 'platform/registry'), str(ROOT / 'platform/ingestion')]
from ingestion_service.storage import Storage  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--retention-days', type=int, help='Schedule raw telemetry deletion after this many days (>=90)')
    parser.add_argument('--dry-run', action='store_true', help='Validate SQL and roll back all policies and jobs')
    args = parser.parse_args()
    if args.retention_days is not None and args.retention_days < 90:
        parser.error('Retention must be at least 90 days to preserve the aggregation refresh window')
    repo = Storage(os.environ.get('REGISTRY_DATABASE_URL', ''))
    repo.initialize_storage()
    with repo.connect() as conn:
        if not conn.execute("SELECT 1 FROM pg_extension WHERE extname='timescaledb'").fetchone():
            raise RuntimeError('TimescaleDB extension is required')
        conn.execute((ROOT / 'platform/ingestion/ingestion_service/aggregates.sql').read_text())
        if args.retention_days is not None:
            conn.execute("SELECT add_retention_policy('telemetria', drop_after => %s::interval, if_not_exists => TRUE)",
                         (str(args.retention_days) + ' days',))
            existing = conn.execute("SELECT job_id FROM timescaledb_information.jobs "
                                    "WHERE proc_name='purge_ingestion_payloads'").fetchone()
            if existing:
                conn.execute('SELECT alter_job(%s, config => %s)',
                             (existing['job_id'], Jsonb({'days': args.retention_days})))
            else:
                conn.execute("SELECT add_job('purge_ingestion_payloads', '1 day', config => %s)",
                             (Jsonb({'days': args.retention_days}),))
        if args.dry_run:
            conn.rollback()
    print('Configuration rolled back (dry run).' if args.dry_run else
          'Hourly aggregates configured. Raw retention enabled: ' + str(args.retention_days is not None))


if __name__ == '__main__':
    main()
