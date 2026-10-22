CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Estrutura inicial; o escritor central será entregue com a ingestão (fase 1).
CREATE TABLE IF NOT EXISTS mensagens_recebidas (
    inquilino text NOT NULL,
    id_mensagem uuid NOT NULL,
    recebido_em timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (inquilino, id_mensagem)
);
CREATE TABLE IF NOT EXISTS telemetria (
    time timestamptz NOT NULL,
    id_mensagem uuid NOT NULL,
    dispositivo text NOT NULL,
    grandeza text NOT NULL,
    valor double precision NOT NULL,
    unidade text NOT NULL,
    inquilino text NOT NULL,
    site text NOT NULL,
    area text,
    dominio text NOT NULL,
    flags jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (time, inquilino, id_mensagem, grandeza)
);
SELECT create_hypertable('telemetria', 'time', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS telemetria_dispositivo_time
    ON telemetria (inquilino, dispositivo, time DESC);
CREATE TABLE IF NOT EXISTS ultimo_estado (
    inquilino text NOT NULL,
    dispositivo text NOT NULL,
    tipo text NOT NULL,
    timestamp timestamptz NOT NULL,
    dados jsonb NOT NULL,
    PRIMARY KEY (inquilino, dispositivo, tipo)
);
