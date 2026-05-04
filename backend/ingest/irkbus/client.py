from __future__ import annotations

import logging
import random
import time
from typing import Any, Dict, Optional

import requests
from requests.utils import add_dict_to_cookiejar

from .config import IrkBusConfig

logger = logging.getLogger(__name__)


class IrkBusClient:
    def __init__(self, config: IrkBusConfig):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "*/*",
                "Accept-Language": "ru,en;q=0.9",
                "Connection": "keep-alive",
                "User-Agent": config.user_agent,
                "Referer": config.referer,
            }
        )
        self.empty_streak = 0
        self.seed_cookie_mode = False
        self._warned_seed_stale = False
        if config.cookie_header:
            self._apply_cookie_header(config.cookie_header)
        if self.session.cookies.get("PHPSESSID"):
            self.seed_cookie_mode = True
            logger.info("Seed PHPSESSID detected in session cookies.")
        else:
            logger.warning(
                "No seed PHPSESSID in session. Collector will rely on auto-refresh and may receive empty snapshots."
            )

    def _apply_cookie_header(self, cookie_header: str) -> None:
        cleaned = cookie_header.strip()
        if cleaned.lower().startswith("cookie:"):
            cleaned = cleaned.split(":", 1)[1].strip()

        parsed = {}
        for chunk in cleaned.split(";"):
            part = chunk.strip()
            if not part or "=" not in part:
                continue
            key, value = part.split("=", 1)
            k = key.strip()
            v = value.strip()
            if not k:
                continue
            parsed[k] = v
        if parsed:
            add_dict_to_cookiejar(self.session.cookies, parsed)
            logger.info("Applied %s cookies from IRKBUS_COOKIE.", len(parsed))

    @property
    def endpoint_url(self) -> str:
        return f"{self.config.base_url}{self.config.endpoint}"

    def refresh_session(self) -> None:
        landing_url = f"{self.config.base_url}/"
        response = self.session.get(
            landing_url,
            timeout=self.config.request_timeout_sec,
            allow_redirects=True,
        )
        response.raise_for_status()
        session_id = self.session.cookies.get("PHPSESSID")
        if session_id:
            logger.info("Session refreshed: PHPSESSID=%s...", session_id[:8])
        else:
            logger.warning("Session refresh completed but PHPSESSID not found.")

    def fetch_snapshot(self) -> Dict[str, Any]:
        params = {
            "rids": self.config.routes,
            "lat0": 0,
            "lng0": 0,
            "lat1": 90,
            "lng1": 180,
            "curk": 0,
            "city": self.config.city,
            "info": random.randint(10000, 99999),
            "_": int(time.time() * 1000),
        }
        response = self.session.get(
            self.endpoint_url,
            params=params,
            timeout=self.config.request_timeout_sec,
        )
        response.raise_for_status()
        payload = response.json()

        anims = payload.get("anims")
        if isinstance(anims, list) and len(anims) > 0:
            self.empty_streak = 0
        else:
            self.empty_streak += 1

        return payload

    def should_refresh_after_empty(self) -> bool:
        return self.empty_streak >= self.config.empty_streak_refresh

    def ensure_session(self) -> None:
        if not self.session.cookies.get("PHPSESSID"):
            self.refresh_session()

    def recover_after_error(self, exc: Exception) -> None:
        logger.warning("Collector request failed: %s", exc)
        if self.seed_cookie_mode:
            logger.warning(
                "Seed-cookie mode: skip auto session refresh after error. "
                "If persistent failures continue, restart parser with fresh cookie from DevTools."
            )
            return
        try:
            self.refresh_session()
            self.empty_streak = 0
        except Exception as refresh_exc:
            logger.error("Session refresh after error failed: %s", refresh_exc)

    def maybe_refresh_after_empty(self) -> Optional[str]:
        if not self.should_refresh_after_empty():
            return None
        if self.seed_cookie_mode:
            if not self._warned_seed_stale:
                logger.warning(
                    "Seed-cookie mode: reached %s empty snapshots. "
                    "Cookie likely stale; paste fresh cookie in UI and press Start to restart parser.",
                    self.config.empty_streak_refresh,
                )
                self._warned_seed_stale = True
            return "seed_cookie_stale"
        try:
            self.refresh_session()
            self.empty_streak = 0
            self._warned_seed_stale = False
            return "refreshed"
        except Exception as exc:
            logger.error("Session refresh after empty streak failed: %s", exc)
            return "failed"
