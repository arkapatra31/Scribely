"""Entry point: ``uv run scribely-backend``."""

from __future__ import annotations

import sys

import structlog
import uvicorn

from scribely.api import create_app
from scribely.config import ConfigError, load_settings
from scribely.log import configure_logging
from scribely.session import LiveSessionManager
from scribely.session.store import SessionStore, StorageError


def main() -> None:
    try:
        settings = load_settings()
    except ConfigError as err:
        print(err, file=sys.stderr)
        raise SystemExit(2) from None

    configure_logging(settings.logging)
    db_path = settings.paths.resolved_data_dir() / "scribely.db"
    try:
        store = SessionStore.open(db_path)
    except StorageError as err:
        print(err, file=sys.stderr)
        raise SystemExit(2) from None
    structlog.get_logger().info(
        "backend.starting",
        host=settings.server.host,
        port=settings.server.port,
        llm_provider=settings.llm.provider,
        llm_model=settings.llm.model,
        database=str(db_path),
    )
    try:
        uvicorn.run(
            create_app(settings, LiveSessionManager(settings, store=store)),
            host=settings.server.host,
            port=settings.server.port,
            log_config=None,
        )
    finally:
        store.close()


if __name__ == "__main__":
    main()
