from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None


def _to_bool(value: str, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _to_int(value: str, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _to_float(value: str, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class IrkBusConfig:
    base_url: str
    endpoint: str
    routes: str
    city: str
    poll_interval_sec: float
    request_timeout_sec: float
    empty_streak_refresh: int
    data_dir: Path
    timezone_name: str
    use_database: bool
    postgres_dsn: Optional[str]
    user_agent: str
    referer: str
    cookie_header: Optional[str]


def _default_data_dir() -> Path:
    # backend/ingest/irkbus/config.py -> backend/ -> project root
    project_root = Path(__file__).resolve().parents[3]
    return project_root / "data" / "irkbus"


def load_config() -> IrkBusConfig:
    if load_dotenv is not None:
        backend_dir = Path(__file__).resolve().parents[2]
        load_dotenv(backend_dir / ".env", override=False)

    base_url = os.getenv("IRKBUS_BASE_URL", "http://irkbus.ru")
    endpoint = os.getenv("IRKBUS_ENDPOINT", "/php/getVehiclesMarkers.php")
    routes = os.getenv("IRKBUS_ROUTES", "37-0,36-0")
    city = os.getenv("IRKBUS_CITY", "irkutsk")
    poll_interval_sec = _to_float(os.getenv("IRKBUS_POLL_INTERVAL_SEC"), 10.0)
    request_timeout_sec = _to_float(os.getenv("IRKBUS_TIMEOUT_SEC"), 20.0)
    empty_streak_refresh = _to_int(os.getenv("IRKBUS_EMPTY_STREAK_REFRESH"), 6)
    data_dir = Path(os.getenv("IRKBUS_DATA_DIR") or _default_data_dir())
    timezone_name = os.getenv("IRKBUS_TIMEZONE", "Asia/Irkutsk")
    postgres_dsn = os.getenv("IRKBUS_DB_DSN")
    use_database = _to_bool(os.getenv("IRKBUS_USE_DB"), True)
    user_agent = os.getenv(
        "IRKBUS_USER_AGENT",
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/135.0.0.0 Safari/537.36"
        ),
    )
    referer = os.getenv("IRKBUS_REFERER", f"{base_url}/")
    cookie_header = os.getenv("IRKBUS_COOKIE")

    return IrkBusConfig(
        base_url=base_url.rstrip("/"),
        endpoint=endpoint,
        routes=routes,
        city=city,
        poll_interval_sec=max(1.0, poll_interval_sec),
        request_timeout_sec=max(3.0, request_timeout_sec),
        empty_streak_refresh=max(1, empty_streak_refresh),
        data_dir=data_dir,
        timezone_name=timezone_name,
        use_database=use_database,
        postgres_dsn=postgres_dsn,
        user_agent=user_agent,
        referer=referer,
        cookie_header=cookie_header,
    )
