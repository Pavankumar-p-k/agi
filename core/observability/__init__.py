"""Observability — structured logging, metrics and health surfaces."""
from __future__ import annotations

from . import logging as logging_utils  # noqa: F401  (package submodule)
from .logging import JsonFormatter, LogContext, configure_json_logging
from .metrics import (
    MetricsMiddleware,
    collect_metrics,
    metrics,
    record_error,
    record_request,
    reset_metrics,
    set_active_sessions,
    set_sandbox_containers,
)

__all__ = [
    "JsonFormatter",
    "LogContext",
    "configure_json_logging",
    "MetricsMiddleware",
    "collect_metrics",
    "metrics",
    "record_error",
    "record_request",
    "reset_metrics",
    "set_active_sessions",
    "set_sandbox_containers",
]
