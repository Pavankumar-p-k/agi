"""Headless observability surface — health and metrics endpoints."""
from __future__ import annotations

from typing import Any

from core.observability.metrics import collect_metrics
from core.event_bus import global_event_bus

__all__ = ["health", "metrics"]


async def health() -> dict[str, Any]:
    """Operational health snapshot: ok + stream/websocket counters."""
    bus = global_event_bus
    return {
        "status": "ok",
        "event_bus": {
            "stream_queues": bus.health().get("stream_queues", 0),
            "stream_queue_depth": bus.health().get("stream_queue_depth", 0),
            "websocket_connections": bus.health().get("websocket_connections", 0),
            "queue_drops": bus.health().get("queue_drops", 0),
            "failed_deliveries": bus.health().get("failed_deliveries", 0),
        },
    }


async def metrics() -> dict[str, Any]:
    """Full metrics payload: operational counters + event bus + websocket."""
    bus = global_event_bus
    bus_health = bus.health()
    return {
        "requests_total": int(collect_metrics().get("requests_total", 0)),
        "requests_by_status": collect_metrics().get("requests_by_status", {}),
        "errors_total": int(collect_metrics().get("errors_total", 0)),
        "active_sessions": int(collect_metrics().get("active_sessions", 0)),
        "sandbox_containers": int(collect_metrics().get("sandbox_containers", 0)),
        "event_bus": {
            "stream_queues": bus_health.get("stream_queues", 0),
            "stream_queue_depth": bus_health.get("stream_queue_depth", 0),
            "websocket_connections": bus_health.get("websocket_connections", 0),
            "queue_drops": bus_health.get("queue_drops", 0),
            "failed_deliveries": bus_health.get("failed_deliveries", 0),
        },
    }
