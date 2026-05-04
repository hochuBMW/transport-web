from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo


def convert_coords(raw_lat: Any, raw_lon: Any) -> Tuple[Optional[float], Optional[float]]:
    try:
        lat = (float(raw_lat) / 1571673.0) - 0.002005
        lon = (float(raw_lon) / 1467000.0) - 0.002415
        return round(lat, 6), round(lon, 6)
    except (TypeError, ValueError):
        return None, None


def parse_source_time(value: Any, source_tz: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.strptime(str(value), "%d.%m.%Y %H:%M:%S")
        return dt.replace(tzinfo=ZoneInfo(source_tz))
    except ValueError:
        return None


def normalize_snapshot(
    payload: Dict[str, Any],
    fetched_at_iso: str,
    source_tz: str,
) -> List[Dict[str, Any]]:
    features: List[Dict[str, Any]] = []
    buses = payload.get("anims") or []
    if not isinstance(buses, list):
        return features

    for bus in buses:
        if not isinstance(bus, dict):
            continue
        lat, lon = convert_coords(bus.get("lat"), bus.get("lon"))
        if lat is None or lon is None:
            continue

        source_time = parse_source_time(bus.get("lasttime"), source_tz)
        event_time_iso = source_time.isoformat() if source_time else None

        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [lon, lat],
            },
            "properties": {
                # Compatible fields for existing analyze endpoint + map popup.
                "id": bus.get("id"),
                "dir": bus.get("dir"),
                "speed": _to_float(bus.get("speed"), 0.0),
                "time": bus.get("lasttime"),
                "event_time": event_time_iso,
                "route_id": bus.get("rid"),
                "route_num": str(bus.get("rnum")) if bus.get("rnum") is not None else None,
                "rtype": bus.get("rtype"),
                "low_floor": bus.get("low_floor"),
                "wifi": bus.get("wifi"),
                "gos_num": bus.get("gos_num"),
                "anim_key": bus.get("anim_key"),
                # Operational metadata.
                "fetched_at": fetched_at_iso,
            },
        }
        features.append(feature)

    return features


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
