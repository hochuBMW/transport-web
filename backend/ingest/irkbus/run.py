from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from .client import IrkBusClient
from .config import IrkBusConfig, load_config
from .normalize import normalize_snapshot
from .storage import PostgresWriter, persist_files


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="IrkBus collector with daily rotation.")
    parser.add_argument("--once", action="store_true", help="Collect only one snapshot and exit.")
    parser.add_argument("--no-db", action="store_true", help="Disable Postgres/PostGIS writing.")
    return parser.parse_args()


def setup_logging(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = data_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        logs_dir / "collector.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=[logging.StreamHandler(), file_handler],
    )


def open_postgres_writer(config: IrkBusConfig, disable_db: bool) -> Optional[PostgresWriter]:
    if disable_db or not config.use_database:
        logging.info("Database writing disabled by config/flag.")
        return None

    if not config.postgres_dsn:
        logging.warning("IRKBUS_DB_DSN is not set. Continuing with file-only storage.")
        return None

    try:
        writer = PostgresWriter(config.postgres_dsn)
        logging.info("Postgres writer initialized.")
        return writer
    except Exception as exc:
        logging.exception("Failed to initialize Postgres writer: %s", exc)
        raise RuntimeError("Postgres writer initialization failed.") from exc


def run_once(client: IrkBusClient, config: IrkBusConfig, pg_writer: Optional[PostgresWriter]) -> None:
    logger = logging.getLogger("ingest.irkbus.runner")
    fetched_at = datetime.now(timezone.utc)
    fetched_at_iso = fetched_at.isoformat()

    payload = client.fetch_snapshot()
    features = normalize_snapshot(payload=payload, fetched_at_iso=fetched_at_iso, source_tz=config.timezone_name)
    paths = persist_files(
        base_dir=config.data_dir,
        fetched_at=fetched_at,
        timezone_name=config.timezone_name,
        raw_payload=payload,
        features=features,
    )
    logger.info(
        "Saved snapshot: buses=%s raw=%s features=%s",
        len(features),
        paths.raw_jsonl.name,
        paths.features_jsonl.name,
    )

    if pg_writer is not None:
        try:
            inserted = pg_writer.write_features(fetched_at=fetched_at, features=features)
            logger.info("Inserted %s rows into Postgres.", inserted)
        except Exception as exc:
            logger.exception("Postgres write failed: %s", exc)

    refresh_status = client.maybe_refresh_after_empty()
    if refresh_status == "refreshed":
        logger.warning("Session refreshed after repeated empty snapshots.")
    elif refresh_status == "seed_cookie_stale":
        logger.warning("Waiting for manual cookie update from UI (seed-cookie mode).")


def main() -> None:
    args = parse_args()
    config = load_config()
    setup_logging(config.data_dir)
    logger = logging.getLogger("ingest.irkbus.main")
    logger.info("Collector python executable: %s", sys.executable)

    client = IrkBusClient(config)
    pg_writer = open_postgres_writer(config, disable_db=args.no_db)

    logger.info("Collector started with interval=%ss routes=%s", config.poll_interval_sec, config.routes)

    try:
        client.ensure_session()
    except Exception as exc:
        logger.exception("Initial session bootstrap failed: %s", exc)

    try:
        while True:
            start = time.monotonic()
            try:
                run_once(client=client, config=config, pg_writer=pg_writer)
            except Exception as exc:
                logger.exception("Snapshot cycle failed: %s", exc)
                client.recover_after_error(exc)

            if args.once:
                break

            elapsed = time.monotonic() - start
            sleep_for = max(0.0, config.poll_interval_sec - elapsed)
            time.sleep(sleep_for)
    except KeyboardInterrupt:
        logger.info("Collector stopped by user.")
    finally:
        if pg_writer is not None:
            pg_writer.close()


if __name__ == "__main__":
    main()
