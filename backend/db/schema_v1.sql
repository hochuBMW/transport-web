-- Transport Web database schema (v1)
-- PostgreSQL + PostGIS

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SCHEMA IF NOT EXISTS transport;

-- Keep route metadata by provider route id (rid).
CREATE TABLE IF NOT EXISTS transport.route_catalog (
    rid INTEGER PRIMARY KEY,
    route_num TEXT NOT NULL,
    route_type TEXT NULL, -- A/T/Tr/...
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    source_payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_route_catalog_route_num
    ON transport.route_catalog(route_num);

-- Vehicle-level metadata (stable dimensions).
CREATE TABLE IF NOT EXISTS transport.vehicle_catalog (
    vehicle_id TEXT PRIMARY KEY, -- provider ID from payload ("id")
    gos_num TEXT NULL,
    vehicle_type TEXT NULL,
    low_floor BOOLEAN NULL,
    wifi BOOLEAN NULL,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_vehicle_catalog_gos_num
    ON transport.vehicle_catalog(gos_num);

-- Main append-only telemetry table.
-- Partitioned by event_time for long-term scalability.
CREATE TABLE IF NOT EXISTS transport.telemetry_snapshot (
    snapshot_id BIGSERIAL,
    event_time TIMESTAMPTZ NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL,
    vehicle_id TEXT NULL,
    rid INTEGER NULL,
    route_num TEXT NULL,
    route_type TEXT NULL,
    speed_kmh DOUBLE PRECISION NULL,
    dir_deg DOUBLE PRECISION NULL,
    low_floor BOOLEAN NULL,
    wifi BOOLEAN NULL,
    gos_num TEXT NULL,
    geom GEOMETRY(Point, 4326) NOT NULL,
    raw_props JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- Optional dedupe key (can be calculated by ingestion code).
    dedupe_hash BYTEA NULL,
    PRIMARY KEY (snapshot_id, event_time)
) PARTITION BY RANGE (event_time);

-- Useful baseline indexes on parent table.
CREATE INDEX IF NOT EXISTS idx_telemetry_snapshot_event_time
    ON transport.telemetry_snapshot(event_time DESC);

CREATE INDEX IF NOT EXISTS idx_telemetry_snapshot_route_time
    ON transport.telemetry_snapshot(route_num, event_time DESC);

CREATE INDEX IF NOT EXISTS idx_telemetry_snapshot_vehicle_time
    ON transport.telemetry_snapshot(vehicle_id, event_time DESC);

CREATE INDEX IF NOT EXISTS idx_telemetry_snapshot_geom
    ON transport.telemetry_snapshot USING GIST(geom);

-- Optional uniqueness guard for duplicate inserts from retries.
-- It works only for rows where dedupe_hash is explicitly set by ingestion.
CREATE UNIQUE INDEX IF NOT EXISTS uq_telemetry_snapshot_dedupe
    ON transport.telemetry_snapshot(event_time, dedupe_hash)
    WHERE dedupe_hash IS NOT NULL;

-- Latest state per vehicle for fast map rendering and monitoring.
CREATE TABLE IF NOT EXISTS transport.vehicle_latest_state (
    vehicle_id TEXT PRIMARY KEY,
    event_time TIMESTAMPTZ NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL,
    rid INTEGER NULL,
    route_num TEXT NULL,
    route_type TEXT NULL,
    speed_kmh DOUBLE PRECISION NULL,
    dir_deg DOUBLE PRECISION NULL,
    low_floor BOOLEAN NULL,
    wifi BOOLEAN NULL,
    gos_num TEXT NULL,
    geom GEOMETRY(Point, 4326) NOT NULL,
    raw_props JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_vehicle_latest_state_event_time
    ON transport.vehicle_latest_state(event_time DESC);

CREATE INDEX IF NOT EXISTS idx_vehicle_latest_state_route_num
    ON transport.vehicle_latest_state(route_num);

CREATE INDEX IF NOT EXISTS idx_vehicle_latest_state_geom
    ON transport.vehicle_latest_state USING GIST(geom);

-- Ingestion run monitoring for parser health and observability.
CREATE TABLE IF NOT EXISTS transport.ingestion_run (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'success', 'partial', 'failed')),
    source_name TEXT NOT NULL DEFAULT 'irkbus',
    routes_requested TEXT NOT NULL,
    records_received INTEGER NOT NULL DEFAULT 0,
    records_inserted INTEGER NOT NULL DEFAULT 0,
    empty_snapshots_streak INTEGER NOT NULL DEFAULT 0,
    error_message TEXT NULL,
    meta JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_ingestion_run_started_at
    ON transport.ingestion_run(started_at DESC);

-- Monthly partition helper.
CREATE OR REPLACE FUNCTION transport.ensure_month_partition(target_date DATE)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    month_start DATE := date_trunc('month', target_date)::date;
    next_month DATE := (month_start + INTERVAL '1 month')::date;
    partition_name TEXT := format(
        'telemetry_snapshot_%s',
        to_char(month_start, 'YYYYMM')
    );
    ddl TEXT;
BEGIN
    ddl := format(
        'CREATE TABLE IF NOT EXISTS transport.%I PARTITION OF transport.telemetry_snapshot
         FOR VALUES FROM (%L) TO (%L);',
        partition_name,
        month_start,
        next_month
    );
    EXECUTE ddl;
END;
$$;

-- Create current + next month partitions.
SELECT transport.ensure_month_partition(current_date);
SELECT transport.ensure_month_partition((current_date + INTERVAL '1 month')::date);
