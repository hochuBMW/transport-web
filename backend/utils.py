# backend/utils.py
import logging
from math import radians, cos, sin, asin, sqrt
from datetime import datetime
from dateutil import parser
from typing import Optional

logger = logging.getLogger(__name__)

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

def parse_time(s: str) -> Optional[datetime]:
    """
    Parse datetime string with flexible format support.
    Prefers day-first format.
    """
    if not s:
        return None
    try:
        return parser.parse(str(s), dayfirst=True)
    except Exception as e:
        logger.warning(f"Failed to parse time '{s}': {e}")
        return None
