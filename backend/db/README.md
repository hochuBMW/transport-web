# Database Design (PostgreSQL + PostGIS)

This folder contains the initial SQL schema for transport telemetry ingestion.

## Files

- `schema_v1.sql` - baseline schema and partition helper.

## Main entities

- `transport.route_catalog` - route metadata keyed by provider `rid`.
- `transport.vehicle_catalog` - vehicle metadata keyed by provider `vehicle_id`.
- `transport.telemetry_snapshot` - append-only telemetry points (partitioned by month).
- `transport.vehicle_latest_state` - one latest row per vehicle for fast UI reads.
- `transport.ingestion_run` - ingestion health/monitoring records.

## Why this shape

- Keep high-volume points in `telemetry_snapshot` for analytics/history.
- Keep current map state in `vehicle_latest_state` for low-latency queries.
- Keep provider dimensions (`route_catalog`, `vehicle_catalog`) to normalize repeated data.
- Keep `ingestion_run` to debug empty snapshots, stale cookies, and ingestion errors.

## Apply schema

From `backend`:

```bash
psql "$IRKBUS_DB_DSN" -f db/schema_v1.sql
```

If you previously ran an older draft of the schema and got:
`ERROR: generated expression is not immutable (SQLSTATE 42P17)`,
run the updated `schema_v1.sql` from this folder again.

## Next implementation step

`ingest/irkbus/storage.py` is wired to:

- insert telemetry into `transport.telemetry_snapshot`,
- upsert current points into `transport.vehicle_latest_state`,
- upsert dimensions into `transport.route_catalog` and `transport.vehicle_catalog`.
