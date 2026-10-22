CREATE TABLE IF NOT EXISTS registry_tenants (
    id text PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS registry_units (
    code text PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS registry_domains (
    tenant text NOT NULL REFERENCES registry_tenants(id),
    id text NOT NULL,
    nome text NOT NULL,
    PRIMARY KEY (tenant, id)
);
CREATE TABLE IF NOT EXISTS registry_profiles (
    tenant text NOT NULL,
    id text NOT NULL,
    nome text NOT NULL,
    dominio text NOT NULL,
    intervalo_esperado_s integer NOT NULL CHECK (intervalo_esperado_s > 0),
    tolerancia_intervalos integer NOT NULL CHECK (tolerancia_intervalos > 0),
    grandezas jsonb NOT NULL,
    PRIMARY KEY (tenant, id),
    FOREIGN KEY (tenant, dominio) REFERENCES registry_domains(tenant, id)
);
CREATE TABLE IF NOT EXISTS registry_sites (
    tenant text NOT NULL REFERENCES registry_tenants(id),
    id text NOT NULL,
    nome text NOT NULL,
    PRIMARY KEY (tenant, id)
);
ALTER TABLE registry_profiles ADD COLUMN IF NOT EXISTS campos jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE registry_profiles ADD COLUMN IF NOT EXISTS configuraveis jsonb NOT NULL DEFAULT '[]'::jsonb;
CREATE TABLE IF NOT EXISTS registry_areas (
    tenant text NOT NULL,
    site text NOT NULL,
    id text NOT NULL,
    nome text NOT NULL,
    PRIMARY KEY (tenant, site, id),
    FOREIGN KEY (tenant, site) REFERENCES registry_sites(tenant, id)
);
CREATE TABLE IF NOT EXISTS registry_devices (
    tenant text NOT NULL,
    id text NOT NULL,
    nome text NOT NULL,
    site text NOT NULL,
    area text NOT NULL,
    perfil text NOT NULL,
    mqtt_username text NOT NULL UNIQUE,
    token_digest text NOT NULL,
    mqtt_hash text NOT NULL,
    revoked_at timestamptz,
    last_seen timestamptz,
    PRIMARY KEY (tenant, id),
    FOREIGN KEY (tenant, site, area) REFERENCES registry_areas(tenant, site, id),
    FOREIGN KEY (tenant, perfil) REFERENCES registry_profiles(tenant, id)
);
CREATE INDEX IF NOT EXISTS registry_devices_profile ON registry_devices(tenant, perfil);
