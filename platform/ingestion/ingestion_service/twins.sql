CREATE TABLE IF NOT EXISTS device_twins (
    tenant text NOT NULL, device text NOT NULL, desired jsonb NOT NULL,
    revision integer NOT NULL DEFAULT 1, updated_at timestamptz NOT NULL,
    last_sent timestamptz, attempts integer NOT NULL DEFAULT 0,
    PRIMARY KEY(tenant,device),
    FOREIGN KEY(tenant,device) REFERENCES registry_devices(tenant,id)
);
