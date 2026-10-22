CREATE UNIQUE INDEX IF NOT EXISTS registry_device_token_unique ON registry_devices(token_digest);
CREATE TABLE IF NOT EXISTS ingest_messages (
    tenant text NOT NULL REFERENCES registry_tenants(id),
    id uuid NOT NULL,
    device text NOT NULL,
    measured_at timestamptz NOT NULL,
    received_at timestamptz NOT NULL,
    fingerprint text NOT NULL,
    envelope jsonb NOT NULL,
    context jsonb NOT NULL,
    published_at timestamptz,
    PRIMARY KEY (tenant, id),
    FOREIGN KEY (tenant, device) REFERENCES registry_devices(tenant, id)
);
CREATE INDEX IF NOT EXISTS ingest_pending ON ingest_messages(received_at) WHERE published_at IS NULL;
CREATE INDEX IF NOT EXISTS ingest_device_time ON ingest_messages(tenant, device, measured_at DESC);
CREATE TABLE IF NOT EXISTS ingest_dead_letters (
    id bigserial PRIMARY KEY,
    tenant text NOT NULL REFERENCES registry_tenants(id),
    device text NOT NULL,
    received_at timestamptz NOT NULL,
    fingerprint text NOT NULL,
    errors jsonb NOT NULL
);
