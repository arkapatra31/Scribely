"""structlog setup."""

from __future__ import annotations

import logging

import structlog

from scribely.config import LoggingConfig


def configure_logging(cfg: LoggingConfig) -> None:
    level = logging.getLevelNamesMapping()[cfg.level]
    logging.basicConfig(level=level, format="%(message)s")
    renderer: structlog.typing.Processor = (
        structlog.processors.JSONRenderer()
        if cfg.format == "json"
        else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )
