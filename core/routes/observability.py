"""Observability routes — health probe and metrics snapshot.

``health()`` is a liveness probe; ``metrics()`` merges the process metrics with
the event-bus counters (stream queues, websocket connections, queue drops) so a
single endpoint answers "is it alive and how busy is the bus?".
"""
from __future__ import annotations

from typing import Any

from core.audit_log import audit_log
from core.event_bus import global_event_bus
from core.observability.metrics import collect_metrics


async def health() -> dict:
    """Liveness probe."""
    return {"status": "ok"}


async def metrics() -> dict:
    """Process metrics plus live event-bus/websocket state."""
    payload: dict[str, Any] = collect_metrics()
    payload["event_bus"] = global_event_bus.health()
    return payload


async def audit_tail(limit: int = 50) -> dict:
    """Best-effort view of the audit buffer size (never raises)."""
    try:
        buffered = len(getattr(audit_log, "_buffer", []) or [])
    except Exception:  # noqa: BLE001
        buffered = 0
    return {"buffered": buffered, "limit": int(limit)}


def register_routes(app: Any) -> None:
    """Attach the observability endpoints to a FastAPI-style app (best-effort)."""
    try:
        app.add_api_route("/api/observability/health", health, methods=["GET"])
        app.add_api_route("/api/observability/metrics", metrics, methods=["GET"])
    except Exception:  # noqa: BLE001 — registration is optional
        pass


__all__ = ["health", "metrics", "audit_tail", "register_routes"]
