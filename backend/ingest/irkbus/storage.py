from __future__ import annotations

import hashlib
import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

try:
    import psycopg
except Exception:  # pragma: no cover
    psycopg = None


def append_jsonl(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(data, ensure_ascii=False) + "\n")


@dataclass
class DailyPaths:
    raw_jsonl: Path
    features_jsonl: Path
    latest_geojson: Path


def daily_paths(base_dir: Path, ts: datetime, timezone_name: str) -> DailyPaths:
    tz = ZoneInfo(timezone_name)
    local_day = ts.astimezone(tz).strftime("%Y-%m-%d")
    raw_jsonl = base_dir / "raw" / f"raw_{local_day}.jsonl"
    features_jsonl = base_dir / "features" / f"features_{local_day}.jsonl"
    latest_geojson = base_dir / "latest.geojson"
    return DailyPaths(raw_jsonl=raw_jsonl, features_jsonl=features_jsonl, latest_geojson=latest_geojson)


def persist_files(
    base_dir: Path,
    fetched_at: datetime,
    timezone_name: str,
    raw_payload: Dict[str, Any],
    features: List[Dict[str, Any]],
) -> DailyPaths:
    paths = daily_paths(base_dir=base_dir, ts=fetched_at, timezone_name=timezone_name)

    append_jsonl(
        paths.raw_jsonl,
        {
            "fetched_at": fetched_at.isoformat(),
            "payload": raw_payload,
        },
    )

    for feature in features:
        append_jsonl(paths.features_jsonl, feature)

    paths.latest_geojson.parent.mkdir(parents=True, exist_ok=True)
    latest_feature_collection = {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "fetched_at": fetched_at.isoformat(),
            "count": len(features),
        },
    }
    paths.latest_geojson.write_text(
        json.dumps(latest_feature_collection, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return paths


class PostgresWriter:
    def __init__(self, dsn: str):
        if psycopg is None:
            raise RuntimeError(
                "psycopg is not installed for interpreter "
                f"{sys.executable}. Install dependency 'psycopg[binary]' in this Python."
            )
        self.dsn = dsn
        self.conn = psycopg.connect(dsn, autocommit=True)
        self.ensure_schema()

    def ensure_schema(self) -> None:
        with self.conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
            cur.execute("CREATE SCHEMA IF NOT EXISTS transport;")

    def write_features(self, fetched_at: datetime, features: Iterable[Dict[str, Any]]) -> int:
        snapshot_rows = []
        latest_rows = []
        route_rows = []
        vehicle_rows = []
        month_partition_dates = set()

        for feature in features:
            geometry = feature.get("geometry") or {}
            coordinates = geometry.get("coordinates") or []
            if len(coordinates) < 2:
                continue

            lon = float(coordinates[0])
            lat = float(coordinates[1])
            props = feature.get("properties") or {}
            vehicle_id = _as_text(props.get("id"))
            rid = _as_optional_int(props.get("route_id"))
            route_num = _as_text(props.get("route_num"))
            route_type = _as_text(props.get("rtype"))
            speed = _as_optional_float(props.get("speed"))
            direction = _as_optional_float(props.get("dir") or props.get("direction"))
            low_floor = _as_optional_bool(props.get("low_floor"))
            wifi = _as_optional_bool(props.get("wifi"))
            gos_num = _as_text(props.get("gos_num"))
            event_time = _parse_iso_datetime(props.get("event_time")) or fetched_at
            props_json = json.dumps(props, ensure_ascii=False)
            dedupe_hash = _build_dedupe_hash(
                vehicle_id=vehicle_id,
                route_num=route_num,
                event_time=event_time,
                speed=speed,
                direction=direction,
                lon=lon,
                lat=lat,
            )
            month_partition_dates.add(event_time.date().replace(day=1))

            snapshot_rows.append(
                (
                    event_time,
                    fetched_at,
                    vehicle_id,
                    rid,
                    route_num,
                    route_type,
                    speed,
                    direction,
                    low_floor,
                    wifi,
                    gos_num,
                    lon,
                    lat,
                    props_json,
                    dedupe_hash,
                )
            )
            if vehicle_id:
                latest_rows.append(
                    (
                        vehicle_id,
                        event_time,
                        fetched_at,
                        rid,
                        route_num,
                        route_type,
                        speed,
                        direction,
                        low_floor,
                        wifi,
                        gos_num,
                        lon,
                        lat,
                        props_json,
                    )
                )
                vehicle_rows.append(
                    (
                        vehicle_id,
                        gos_num,
                        route_type,
                        low_floor,
                        wifi,
                        props_json,
                    )
                )
            if rid is not None and route_num:
                route_rows.append((rid, route_num, route_type, props_json))

        if not snapshot_rows:
            return 0

        with self.conn.cursor() as cur:
            for month_start in sorted(month_partition_dates):
                try:
                    cur.execute("SELECT transport.ensure_month_partition(%s::date);", (month_start,))
                except Exception:
                    # Function may not exist if schema SQL was not applied yet.
                    pass

            if route_rows:
                cur.executemany(
                    """
                    INSERT INTO transport.route_catalog (
                        rid, route_num, route_type, source_payload, first_seen_at, last_seen_at
                    )
                    VALUES (%s, %s, %s, %s::jsonb, now(), now())
                    ON CONFLICT (rid)
                    DO UPDATE SET
                        route_num = EXCLUDED.route_num,
                        route_type = EXCLUDED.route_type,
                        source_payload = EXCLUDED.source_payload,
                        last_seen_at = now(),
                        is_active = TRUE;
                    """,
                    route_rows,
                )

            if vehicle_rows:
                cur.executemany(
                    """
                    INSERT INTO transport.vehicle_catalog (
                        vehicle_id, gos_num, vehicle_type, low_floor, wifi, source_payload, first_seen_at, last_seen_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb, now(), now())
                    ON CONFLICT (vehicle_id)
                    DO UPDATE SET
                        gos_num = EXCLUDED.gos_num,
                        vehicle_type = EXCLUDED.vehicle_type,
                        low_floor = EXCLUDED.low_floor,
                        wifi = EXCLUDED.wifi,
                        source_payload = EXCLUDED.source_payload,
                        last_seen_at = now();
                    """,
                    vehicle_rows,
                )

            cur.executemany(
                """
                INSERT INTO transport.telemetry_snapshot (
                    event_time, fetched_at, vehicle_id, rid, route_num, route_type,
                    speed_kmh, dir_deg, low_floor, wifi, gos_num, geom, raw_props, dedupe_hash
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326),
                    %s::jsonb,
                    %s
                )
                ON CONFLICT DO NOTHING;
                """,
                snapshot_rows,
            )

            if latest_rows:
                cur.executemany(
                    """
                    INSERT INTO transport.vehicle_latest_state (
                        vehicle_id, event_time, fetched_at, rid, route_num, route_type,
                        speed_kmh, dir_deg, low_floor, wifi, gos_num, geom, raw_props, updated_at
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326),
                        %s::jsonb,
                        now()
                    )
                    ON CONFLICT (vehicle_id)
                    DO UPDATE SET
                        event_time = EXCLUDED.event_time,
                        fetched_at = EXCLUDED.fetched_at,
                        rid = EXCLUDED.rid,
                        route_num = EXCLUDED.route_num,
                        route_type = EXCLUDED.route_type,
                        speed_kmh = EXCLUDED.speed_kmh,
                        dir_deg = EXCLUDED.dir_deg,
                        low_floor = EXCLUDED.low_floor,
                        wifi = EXCLUDED.wifi,
                        gos_num = EXCLUDED.gos_num,
                        geom = EXCLUDED.geom,
                        raw_props = EXCLUDED.raw_props,
                        updated_at = now();
                    """,
                    latest_rows,
                )

        return len(snapshot_rows)

    def close(self) -> None:
        self.conn.close()


def _as_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _as_optional_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_optional_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_optional_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return None


def _parse_iso_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        logger.debug("Failed to parse ISO datetime: %s", value)
        return None


def _build_dedupe_hash(
    vehicle_id: Optional[str],
    route_num: Optional[str],
    event_time: datetime,
    speed: Optional[float],
    direction: Optional[float],
    lon: float,
    lat: float,
) -> bytes:
    payload = "|".join(
        [
            vehicle_id or "",
            route_num or "",
            event_time.isoformat(),
            "" if speed is None else f"{speed:.4f}",
            "" if direction is None else f"{direction:.4f}",
            f"{lon:.6f}",
            f"{lat:.6f}",
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).digest()
