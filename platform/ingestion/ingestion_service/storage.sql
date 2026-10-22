CREATE TABLE IF NOT EXISTS storage_processed (
    tenant text NOT NULL, id uuid NOT NULL, processed_at timestamptz NOT NULL,
    PRIMARY KEY (tenant,id)
);
CREATE TABLE IF NOT EXISTS telemetria (
    time timestamptz NOT NULL, id_mensagem uuid NOT NULL, dispositivo text NOT NULL,
    grandeza text NOT NULL, valor double precision NOT NULL, unidade text NOT NULL,
    inquilino text NOT NULL, site text NOT NULL, area text, dominio text NOT NULL,
    flags jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE(time,inquilino,id_mensagem,grandeza)
);
CREATE INDEX IF NOT EXISTS telemetria_dispositivo_time ON telemetria(inquilino,dispositivo,time DESC);
CREATE TABLE IF NOT EXISTS ultimo_estado (
    inquilino text NOT NULL, dispositivo text NOT NULL, tipo text NOT NULL,
    timestamp timestamptz NOT NULL, dados jsonb NOT NULL,
    PRIMARY KEY(inquilino,dispositivo,tipo)
);
