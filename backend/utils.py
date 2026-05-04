# backend/utils.py
import logging
from math import radians, cos, sin, asin, sqrt, atan2, degrees
from datetime import datetime, timezone
from functools import lru_cache
from dateutil import parser
from typing import Any, Callable, Dict, Optional

from shapely.geometry import Point, shape
from shapely.prepared import prep

logger = logging.getLogger(__name__)

def bearing_deg(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """
    Начальный азимут от точки 1 к точке 2, градусы [0, 360), по часовой от севера.
    """
    φ1, φ2 = radians(lat1), radians(lat2)
    dλ = radians(lon2 - lon1)
    x = sin(dλ) * cos(φ2)
    y = cos(φ1) * sin(φ2) - sin(φ1) * cos(φ2) * cos(dλ)
    θ = atan2(x, y)
    return (degrees(θ) + 360) % 360


def circular_mean_bearing_deg(bearings: list) -> float:
    """Круговое среднее набора азимутов, градусы [0, 360)."""
    if not bearings:
        return 0.0
    xr = sum(cos(radians(b)) for b in bearings)
    yr = sum(sin(radians(b)) for b in bearings)
    return degrees(atan2(yr, xr)) % 360


def direction_bin_from_ref(bearing: float, ref: float) -> int:
    """
    Деление пополам относительно ref: 0 — тот же полукруг, что и ref; 1 — противоположный.
    """
    d = radians(bearing - ref)
    return 0 if cos(d) >= 0 else 1


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """
    Calculate distance between two points using Haversine formula.
    Returns distance in meters.
    """
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    R = 6371000  # Earth radius in meters
    return R * c

def point_in_analysis_geometry(lon: float, lat: float, geom: Optional[Dict[str, Any]]) -> bool:
    """
    True if (lon, lat) lies inside or on the boundary of the given GeoJSON geometry.
    Supports Polygon and MultiPolygon in WGS84 (same as incoming points).
    """
    if not geom:
        return True
    gtype = geom.get("type")
    if gtype not in ("Polygon", "MultiPolygon"):
        return False
    try:
        g = shape(geom)
        if not g.is_valid:
            g = g.buffer(0)
        return bool(g.covers(Point(lon, lat)))
    except Exception:
        return False


def build_analysis_geometry_checker(geom: Optional[Dict[str, Any]]) -> Callable[[float, float], bool]:
    """
    Build a reusable point-in-geometry predicate to avoid rebuilding geometry
    for every telemetry point during analysis.
    """
    if not geom:
        return lambda _lon, _lat: True

    gtype = geom.get("type")
    if gtype not in ("Polygon", "MultiPolygon"):
        return lambda _lon, _lat: False

    try:
        g = shape(geom)
        if not g.is_valid:
            g = g.buffer(0)
        prepared = prep(g)
        return lambda lon, lat: bool(prepared.covers(Point(lon, lat)))
    except Exception:
        return lambda _lon, _lat: False


@lru_cache(maxsize=200000)
def _parse_time_cached(value: str) -> Optional[datetime]:
    text = value.strip()
    if not text:
        return None

    # Fast path for ISO-like timestamps from API/DB.
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        dt = datetime.fromisoformat(normalized)
        return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt
    except ValueError:
        pass

    # Common explicit formats used in this project.
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y %H:%M",
    ):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt
        except ValueError:
            continue

    try:
        dt = parser.parse(text, dayfirst=True)
        return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt
    except Exception as e:
        logger.warning(f"Failed to parse time '{text}': {e}")
        return None


def parse_time(s: str) -> Optional[datetime]:
    """
    Parse datetime string with flexible format support.
    Prefers day-first format.
    """
    if not s:
        return None
    return _parse_time_cached(str(s))
