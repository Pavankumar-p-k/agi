from __future__ import annotations

import time
import logging
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from core.observability.logging import LogContext

logger = logging.getLogger("jarvis.observability.metrics")

_metrics_enabled = False
_metric_requests_total: dict[str, int] = {}
_metric_requests_duration: dict[str, list[float]] = {}
_metric_tool_calls_total: dict[str, int] = {}
_metric_llm_latency: list[float] = []
_metric_active_sessions: int = 0
_metric_sandbox_containers: int = 0
_metric_plugin_count: int = 0
_metric_queue_depth: int = 0


def _init_metrics():
    global _metrics_enabled
    _metrics_enabled = True
    logger.info("[Metrics] Prometheus-style metrics enabled (in-process)")


def inc_requests_total(method: str, path: str, status: int) -> None:
    if not _metrics_enabled:
        return
    key = f"{method}:{path}:{status}"
    _metric_requests_total[key] = _metric_requests_total.get(key, 0) + 1


def observe_request_duration(method: str, path: str, seconds: float) -> None:
    if not _metrics_enabled:
        return
    key = f"{method}:{path}"
    if key not in _metric_requests_duration:
        _metric_requests_duration[key] = []
    _metric_requests_duration[key].append(seconds)


def inc_tool_calls_total(tool_name: str) -> None:
    if not _metrics_enabled:
        return
    _metric_tool_calls_total[tool_name] = _metric_tool_calls_total.get(tool_name, 0) + 1


def observe_llm_latency(seconds: float) -> None:
    if not _metrics_enabled:
        return
    _metric_llm_latency.append(seconds)
    if len(_metric_llm_latency) > 1000:
        _metric_llm_latency = _metric_llm_latency[-500:]


def set_active_sessions(n: int) -> None:
    global _metric_active_sessions
    _metric_active_sessions = n


def set_sandbox_containers(n: int) -> None:
    global _metric_sandbox_containers
    _metric_sandbox_containers = n


def set_plugin_count(n: int) -> None:
    global _metric_plugin_count
    _metric_plugin_count = n


def set_queue_depth(n: int) -> None:
    global _metric_queue_depth
    _metric_queue_depth = n


def _quantile(data: list[float], q: float) -> float:
    if not data:
        return 0.0
    sorted_data = sorted(data)
    idx = int(len(sorted_data) * q)
    return sorted_data[min(idx, len(sorted_data) - 1)]


def collect_metrics() -> dict:
    """Return all metrics as a dict (for /metrics endpoint)."""
    requests_total = dict(_metric_requests_total)
    tool_calls_total = dict(_metric_tool_calls_total)

    request_duration = {}
    for key, vals in _metric_requests_duration.items():
        request_duration[key] = {
            "count": len(vals),
            "avg": round(sum(vals) / len(vals), 3) if vals else 0,
            "p50": round(_quantile(vals, 0.5), 3),
            "p95": round(_quantile(vals, 0.95), 3),
            "p99": round(_quantile(vals, 0.99), 3),
        }

    llm_latency = {}
    if _metric_llm_latency:
        llm_latency = {
            "count": len(_metric_llm_latency),
            "avg": round(sum(_metric_llm_latency) / len(_metric_llm_latency), 3),
            "p50": round(_quantile(_metric_llm_latency, 0.5), 3),
            "p95": round(_quantile(_metric_llm_latency, 0.95), 3),
            "p99": round(_quantile(_metric_llm_latency, 0.99), 3),
        }

    return {
        "requests_total": requests_total,
        "tool_calls_total": tool_calls_total,
        "request_duration_seconds": request_duration,
        "llm_latency_seconds": llm_latency,
        "active_sessions": _metric_active_sessions,
        "sandbox_containers": _metric_sandbox_containers,
        "plugin_count": _metric_plugin_count,
        "queue_depth": _metric_queue_depth,
    }


class MetricsMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that records request metrics."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start = time.monotonic()
        response = await call_next(request)
        duration = time.monotonic() - start

        path = request.url.path
        method = request.method
        status = response.status_code

        inc_requests_total(method, path, status)
        observe_request_duration(method, path, duration)

        return response


metrics = _init_metrics
