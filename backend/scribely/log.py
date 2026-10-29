"""structlog setup: the console, plus a rotating log file in the data folder.

The file stays on this computer (CLAUDE.md rule 4) and is what "Copy diagnostics" in
Settings reads. Never log API keys or transcript text.
"""

from __future__ import annotations

import importlib.util
import logging
import logging.handlers
import sys
from collections import deque
from pathlib import Path

import structlog

from scribely.config import LoggingConfig

LOG_FILENAME = "scribely.log"
MAX_LOG_BYTES = 1_000_000
LOG_BACKUPS = 3

_log_file: Path | None = None


def configure_logging(cfg: LoggingConfig, logs_dir: Path | None = None) -> Path | None:
    """Route structlog and stdlib logging (uvicorn) to stderr and, if ``logs_dir`` is given,
    to ``<logs_dir>/scribely.log``. Returns the log file's path, if one could be opened."""
    global _log_file
    level = logging.getLevelNamesMapping()[cfg.level]
    shared: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]
    console: structlog.typing.Processor = (
        structlog.processors.JSONRenderer()
        if cfg.format == "json"
        else structlog.dev.ConsoleRenderer(colors=_console_colors())
    )
    handlers: list[logging.Handler] = [_handler(logging.StreamHandler(), console, shared)]

    _log_file = None
    if logs_dir is not None:
        try:
            logs_dir.mkdir(parents=True, exist_ok=True)
            path = logs_dir / LOG_FILENAME
            file_handler = logging.handlers.RotatingFileHandler(
                path, maxBytes=MAX_LOG_BYTES, backupCount=LOG_BACKUPS, encoding="utf-8"
            )
        except OSError as err:
            print(f"Logging to the console only; couldn't open {logs_dir}: {err}", file=sys.stderr)
        else:
            plain = structlog.dev.ConsoleRenderer(colors=False)
            handlers.append(_handler(file_handler, plain, shared))
            _log_file = path

    root = logging.getLogger()
    for old in root.handlers[:]:
        root.removeHandler(old)
        old.close()
    for h in handlers:
        root.addHandler(h)
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).handlers.clear()
        logging.getLogger(name).propagate = True

    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )
    return _log_file


def log_file() -> Path | None:
    return _log_file


def tail(lines: int = 150) -> list[str]:
    """The last ``lines`` lines of the log file (empty if there is none)."""
    if _log_file is None:
        return []
    try:
        with _log_file.open(encoding="utf-8", errors="replace") as f:
            return [line.rstrip("\n") for line in deque(f, maxlen=lines)]
    except OSError:
        return []


def _console_colors() -> bool:
    # structlog needs colorama for colors on Windows (and raises without it).
    has_colorama = importlib.util.find_spec("colorama") is not None
    return sys.stderr.isatty() and (sys.platform != "win32" or has_colorama)


def _handler(
    handler: logging.Handler,
    renderer: structlog.typing.Processor,
    shared: list[structlog.typing.Processor],
) -> logging.Handler:
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
            foreign_pre_chain=shared,
        )
    )
    return handler
