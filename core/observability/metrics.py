"""Operational metrics — in-process counters for the observability surface.

Deliberately dependency-free: ``collect_metrics()`` snapshots a small set of
counters maintained by ``MetricsMiddleware`` and the monitors layer. Event-bus
and websocket counters live on the bus itself and are merged in by the
observability route.
"""
from __future__ import annotations

import threading
from typing import Any, Optional

_lock = threading.Lock()

_state: dict[str, Any] = {
    "requests_total": 0,
    "requests_by_status": {},
    "active_sessions": 0,
    "sandbox_containers": 0,
    "errors_total": 0,
}


def _bump(key: str, amount: int = 1) -> None:
    with _lock:
        _state[key] = int(_state.get(key, 0)) + amount


def record_request(status: Optional[int] = None) -> None:
    with _lock:
        _state["requests_total"] = int(_state.get("requests_total", 0)) + 1
        if status is not None:
            by_status = dict(_state.get("requests_by_status") or {})
            by_status[str(status)] = int(by_status.get(str(status), 0)) + 1
            _state["requests_by_status"] = by_status
        if status is not None and status >= 500:
            _state["errors_total"] = int(_state.get("errors_total", 0)) + 1


def record_error() -> None:
    _bump("errors_total")


def set_active_sessions(count: int) -> None:
    with _lock:
        _state["active_sessions"] = max(0, int(count))


def set_sandbox_containers(count: int) -> None:
    with _lock:
        _state["sandbox_containers"] = max(0, int(count))


def collect_metrics() -> dict:
    """Snapshot the process metrics (no external service data)."""
    with _lock:
        snapshot = dict(_state)
        snapshot["requests_by_status"] = dict(_state.get("requests_by_status") or {})
    return snapshot


def reset_metrics() -> None:
    with _lock:
        _state.update({
            "requests_total": 0,
            "requests_by_status": {},
            "active_sessions": 0,
            "sandbox_containers": 0,
            "errors_total": 0,
        })


class _MetricsRegistry:
    """Thin object facade over the module counters."""

    def collect(self) -> dict:
        return collect_metrics()

    def snapshot(self) -> dict:
        return collect_metrics()

    def __call__(self) -> dict:
        return collect_metrics()


metrics = _MetricsRegistry()


class MetricsMiddleware:
    """ASGI middleware counting requests and recording status codes."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        status: Optional[int] = None

        async def send_wrapper(message: dict) -> None:
            nonlocal status
            if message.get("type") == "http.response.start":
                status = message.get("status")
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            record_request(status)


__all__ = [
    "MetricsMiddleware",
    "collect_metrics",
    "metrics",
    "record_request",
    "record_error",
    "reset_metrics",
    "set_active_sessions",
    "set_sandbox_containers",
]
