"""Structured logging with secret redaction.

Usage::

    from wififortress.core.logging import get_logger, setup_logging

    log = get_logger(__name__)
    log.info("scan finished", extra={"event": "scan.finished", "count": 12})

Records are written to ``<data>/logs/wifi-fortress.log`` (rotating) and to
stderr.  Every message and every structured value is passed through the
redactor first, so a secret can never reach disk even by mistake.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Any

from wififortress.core.paths import log_dir
from wififortress.core.redaction import redact_text, redact_value, strip_control_chars

_LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s %(message)s"
_configured = False


class RedactingFormatter(logging.Formatter):
    """Format records as text plus an optional JSON ``extra`` payload."""

    def __init__(self, fmt: str = _LOG_FORMAT) -> None:
        super().__init__(fmt)

    def format(self, record: logging.LogRecord) -> str:
        record.msg = strip_control_chars(redact_text(str(record.msg)))
        if record.args:
            try:
                record.args = tuple(
                    redact_value(a) if isinstance(a, (str, dict, list, tuple)) else a
                    for a in record.args
                )
            except Exception:  # pragma: no cover - defensive
                record.args = ()
        base = super().format(record)
        payload = getattr(record, "event_data", None)
        if payload:
            try:
                base = f"{base} | {json.dumps(redact_value(payload), default=str)}"
            except Exception:  # pragma: no cover - defensive
                pass
        return base


def setup_logging(level: int = logging.INFO, log_file: Path | None = None) -> Path:
    """Configure root logging once. Returns the log file path."""
    global _configured
    target = log_file or (log_dir() / "wifi-fortress.log")
    root = logging.getLogger()
    if _configured:
        return target

    root.setLevel(level)
    formatter = RedactingFormatter()

    try:
        handler = logging.handlers.RotatingFileHandler(
            target, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(formatter)
        root.addHandler(handler)
    except OSError:  # pragma: no cover - read-only fs
        pass

    stream = logging.StreamHandler(sys.stderr)
    stream.setFormatter(formatter)
    root.addHandler(stream)

    # Qt and other chatty libraries stay at WARNING.
    for noisy in ("PySide6", "PIL", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _configured = True
    return target


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


class EventLogger:
    """Convenience wrapper that records structured events."""

    def __init__(self, name: str) -> None:
        self._log = get_logger(name)

    def _emit(self, level: int, message: str, **data: Any) -> None:
        self._log.log(level, message, extra={"event_data": data} if data else None)

    def info(self, message: str, **data: Any) -> None:
        self._emit(logging.INFO, message, **data)

    def warning(self, message: str, **data: Any) -> None:
        self._emit(logging.WARNING, message, **data)

    def error(self, message: str, **data: Any) -> None:
        self._emit(logging.ERROR, message, **data)

    def debug(self, message: str, **data: Any) -> None:
        self._emit(logging.DEBUG, message, **data)
