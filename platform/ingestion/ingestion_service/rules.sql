CREATE TABLE IF NOT EXISTS processing_rules (
    tenant text NOT NULL, id text NOT NULL, device text NOT NULL,
    definition jsonb NOT NULL, created_at timestamptz NOT NULL,
    PRIMARY KEY (tenant,id),
    FOREIGN KEY (tenant,device) REFERENCES registry_devices(tenant,id)
);
CREATE TABLE IF NOT EXISTS processing_alarms (
    id uuid PRIMARY KEY, tenant text NOT NULL, rule_id text NOT NULL, device text NOT NULL,
    status text NOT NULL CHECK(status IN ('ativo','reconhecido','resolvido')),
    severity text NOT NULL, occurred_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
    details jsonb NOT NULL,
    FOREIGN KEY (tenant,rule_id) REFERENCES processing_rules(tenant,id)
);
ALTER TABLE processing_rules ADD COLUMN IF NOT EXISTS evaluated_at timestamptz;
CREATE UNIQUE INDEX IF NOT EXISTS one_active_alarm ON processing_alarms(tenant,rule_id)
    WHERE status IN ('ativo','reconhecido');
CREATE TABLE IF NOT EXISTS processing_actions (
    id bigserial PRIMARY KEY, alarm_id uuid NOT NULL REFERENCES processing_alarms(id),
    action jsonb NOT NULL, attempts integer NOT NULL DEFAULT 0,
    next_attempt timestamptz NOT NULL, delivered_at timestamptz, last_error text
);
