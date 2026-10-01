"""Structured logging helpers — JSON formatting + a request-scoped context.

``LogContext`` carries correlation fields (request id, tenant, workflow) on a
``contextvars.ContextVar`` so every log line emitted while handling a request
can include them without threading arguments through call sites.
``JsonFormatter`` renders records as single-line JSON objects.
"""
from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from typing import Any, Optional

_context: ContextVar[dict] = ContextVar("jarvis_log_context", default={})

# Standard LogRecord attributes — anything else is treated as an "extra".
_RESERVED = frozenset({
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "taskName", "message", "asctime",
})


class LogContext:
    """Context-local key/value store merged into every emitted log record."""

    @staticmethod
    def set(**fields: Any) -> None:
        merged = dict(_context.get({}))
        merged.update(fields)
        _context.set(merged)

    @staticmethod
    def get() -> dict:
        return dict(_context.get({}))

    @staticmethod
    def clear() -> None:
        _context.set({})

    @staticmethod
    def bind(**fields: Any) -> Any:
        """Return a token for later ``reset(token)`` (context manager friendly)."""
        merged = dict(_context.get({}))
        merged.update(fields)
        return _context.set(merged)

    @staticmethod
    def reset(token: Any) -> None:
        try:
            _context.reset(token)
        except Exception:  # noqa: BLE001 — best-effort context restoration
            pass

    def __enter__(self) -> "LogContext":
        return self

    def __exit__(self, *exc: Any) -> None:
        LogContext.clear()


class JsonFormatter(logging.Formatter):
    """Render log records as JSON, including context fields and extras."""

    def __init__(self, include_context: bool = True, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.include_context = include_context

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if self.include_context:
            payload.update(LogContext.get())
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload.setdefault(key, value)
        return json.dumps(payload, default=str)


def configure_json_logging(level: int = logging.INFO,
                           logger: Optional[logging.Logger] = None) -> logging.Logger:
    """Attach a ``JsonFormatter`` stream handler to *logger* (root by default)."""
    target = logger or logging.getLogger()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    target.handlers = [handler]
    target.setLevel(level)
    return target


__all__ = ["JsonFormatter", "LogContext", "configure_json_logging"]
