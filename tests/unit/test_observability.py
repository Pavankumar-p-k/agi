from __future__ import annotations

import asyncio
import json

import pytest

from core.audit_log import AuditLog, EffectAuditMiddleware
from core.event_bus import Event, EventBus
from core.observability.metrics import collect_metrics
from core.routes.observability import health, metrics


def test_event_bus_health_reports_queue_and_websocket_state():
    bus = EventBus()
    queue = bus.subscribe_stream()
    queue.put_nowait({"event": "one"})
    health = bus.health()
    assert health["stream_queues"] == 1
    assert health["stream_queue_depth"] == 1
    assert health["websocket_connections"] == 0


@pytest.mark.asyncio
async def test_event_bus_health_counts_queue_drops():
    bus = EventBus()
    queue = bus.subscribe_stream()
    for _ in range(queue.maxsize):
        queue.put_nowait({})
    await bus.publish(Event(type="test", source="test", payload={}))
    assert bus.health()["queue_drops"] == 1


def test_metrics_shape_includes_operational_counters():
    metrics = collect_metrics()
    assert "requests_total" in metrics
    assert "event_bus" not in metrics


@pytest.mark.asyncio
async def test_observability_endpoints_expose_health_and_event_bus_metrics():
    assert (await health())["status"] == "ok"
    payload = await metrics()
    assert "requests_total" in payload
    assert "event_bus" in payload
    assert "websocket_connections" in payload["event_bus"]


@pytest.mark.asyncio
async def test_effect_audit_middleware_records_mutating_request(tmp_path):
    audit = AuditLog(tmp_path)

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 201, "headers": [(b"x-request-id", b"rid-1")]})
        await send({"type": "http.response.body", "body": b"{}"})

    middleware = EffectAuditMiddleware(app)
    original = __import__("core.audit_log", fromlist=["audit_log"]).audit_log
    module = __import__("core.audit_log", fromlist=["audit_log"])
    module.audit_log = audit
    try:
        await middleware(
            {"type": "http", "method": "POST", "path": "/api/action"},
            lambda: asyncio.sleep(0),
            lambda message: asyncio.sleep(0),
        )
    finally:
        module.audit_log = original
    audit.force_flush()
    entry = json.loads(next(tmp_path.glob("*.jsonl")).read_text())
    assert entry["event"] == "effectful_request"
    assert entry["status"] == 201
    assert entry["request_id"] == "rid-1"
