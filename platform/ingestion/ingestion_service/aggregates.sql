CREATE MATERIALIZED VIEW IF NOT EXISTS telemetria_horaria
WITH (timescaledb.continuous, timescaledb.materialized_only=false) AS
SELECT time_bucket(INTERVAL '1 hour', time) AS hora,inquilino,dispositivo,grandeza,unidade,
       avg(valor) AS media,min(valor) AS minimo,max(valor) AS maximo,count(*) AS amostras
FROM telemetria
GROUP BY hora,inquilino,dispositivo,grandeza,unidade
WITH NO DATA;
SELECT add_continuous_aggregate_policy('telemetria_horaria',
    start_offset => INTERVAL '90 days',end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',if_not_exists => TRUE);

CREATE OR REPLACE PROCEDURE purge_ingestion_payloads(job_id integer, config jsonb)
LANGUAGE plpgsql AS $$
BEGIN
    UPDATE ingest_messages i SET envelope='{}'::jsonb,context='{}'::jsonb
    WHERE measured_at < now() - make_interval(days => (config->>'days')::integer)
      AND published_at IS NOT NULL AND envelope <> '{}'::jsonb
      AND EXISTS (SELECT 1 FROM storage_processed p WHERE p.tenant=i.tenant AND p.id=i.id);
END;
$$;
