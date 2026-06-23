"""core/webhook_manager.py
Webhook dispatch engine for JARVIS.
Supports event-based webhook triggers with validation, dispatch, and retry.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

VALID_EVENTS = {
    "chat.completed",
    "chat.started",
    "agent.completed",
    "agent.started",
    "tool.executed",
    "build.completed",
    "build.failed",
    "error.occurred",
    "skill.created",
    "plugin.installed",
    "integration.connected",
    "integration.disconnected",
}


def validate_webhook_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Invalid webhook URL scheme: {parsed.scheme}. Must be http or https.")
    if not parsed.netloc:
        raise ValueError("Invalid webhook URL: no host specified.")
    return url


def validate_events(events: str) -> list[str]:
    parts = [e.strip() for e in events.replace(",", " ").split()]
    for event in parts:
        if event not in VALID_EVENTS:
            raise ValueError(f"Invalid event: {event}. Valid events: {', '.join(sorted(VALID_EVENTS))}")
    return parts


@dataclass
class WebhookEvent:
    event: str
    payload: dict[str, Any]
    timestamp: str = ""
    signature: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class WebhookDelivery:
    url: str
    event: str
    status_code: int = 0
    error: str = ""
    duration_ms: float = 0.0
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    @property
    def success(self) -> bool:
        return 200 <= self.status_code < 300


class WebhookDispatcher:
    def __init__(self):
        self._client: httpx.AsyncClient | None = None
        self._queue: asyncio.Queue[WebhookEvent] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None
        self._running = False
        self._delivery_history: list[WebhookDelivery] = []
        self._max_history = 1000
        self._secret = ""
        self._max_retries = 3
        self._timeout = 10.0

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(self._timeout))
        return self._client

    def start(self):
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info("Webhook dispatcher started")

    async def stop(self):
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None
        if self._client:
            await self._client.aclose()
            self._client = None
        logger.info("Webhook dispatcher stopped")

    def set_secret(self, secret: str):
        self._secret = secret

    async def dispatch(self, event: str, payload: dict[str, Any]):
        webhook_event = WebhookEvent(event=event, payload=payload)
        if self._secret:
            raw = f"{webhook_event.timestamp}.{json.dumps(payload, sort_keys=True)}"
            webhook_event.signature = hmac.new(
                self._secret.encode(), raw.encode(), hashlib.sha256
            ).hexdigest()
        await self._queue.put(webhook_event)

    def _sign_payload(self, payload: bytes, timestamp: str) -> str:
        raw = f"{timestamp}.{payload.decode()}"
        return hmac.new(self._secret.encode(), raw.encode(), hashlib.sha256).hexdigest()

    async def _worker_loop(self):
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            try:
                await self._process_event(event)
            except Exception as e:
                logger.error(f"Webhook dispatch failed for {event.event}: {e}")

    async def _process_event(self, event: WebhookEvent):
        from core.database_models import SessionLocal, Webhook
        db = SessionLocal()
        try:
            hooks = db.query(Webhook).filter(Webhook.is_active == True).all()
        finally:
            db.close()

        tasks = []
        for hook in hooks:
            if event.event in hook.events.split(",") if isinstance(hook.events, str) else event.event in hook.events:
                tasks.append(self._deliver_with_retry(hook.url, event))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _deliver_with_retry(self, url: str, event: WebhookEvent):
        last_error = ""
        for attempt in range(self._max_retries):
            start = time.time()
            try:
                body = {
                    "event": event.event,
                    "timestamp": event.timestamp,
                    "payload": event.payload,
                    "signature": event.signature,
                }
                headers = {"Content-Type": "application/json"}
                if self._secret:
                    body_str = json.dumps(body, sort_keys=True)
                    headers["X-Jarvis-Signature"] = self._sign_payload(
                        body_str.encode(), event.timestamp
                    )
                    headers["X-Jarvis-Timestamp"] = event.timestamp

                resp = await self.client.post(url, json=body, headers=headers)
                duration = (time.time() - start) * 1000
                delivery = WebhookDelivery(
                    url=url, event=event.event,
                    status_code=resp.status_code, duration_ms=duration,
                )
                self._record_delivery(delivery)
                if delivery.success:
                    return delivery
                last_error = f"HTTP {resp.status_code}"
            except httpx.TimeoutException:
                last_error = "timeout"
            except httpx.RequestError as e:
                last_error = str(e)
            except Exception as e:
                last_error = str(e)
                logger.exception(f"Webhook delivery exception to {url}")

            if attempt < self._max_retries - 1:
                await asyncio.sleep(2 ** attempt)

        delivery = WebhookDelivery(
            url=url, event=event.event,
            status_code=0, error=last_error,
        )
        self._record_delivery(delivery)
        logger.warning(f"Webhook delivery failed to {url} after {self._max_retries} attempts: {last_error}")
        return delivery

    def _record_delivery(self, delivery: WebhookDelivery):
        self._delivery_history.append(delivery)
        if len(self._delivery_history) > self._max_history:
            self._delivery_history = self._delivery_history[-self._max_history:]

    def get_delivery_history(self, n: int = 50) -> list[dict[str, Any]]:
        return [
            {"url": d.url, "event": d.event, "status_code": d.status_code,
             "error": d.error, "duration_ms": round(d.duration_ms, 1),
             "timestamp": d.timestamp, "success": d.success}
            for d in self._delivery_history[-n:]
        ]

    def get_stats(self) -> dict[str, Any]:
        total = len(self._delivery_history)
        successes = sum(1 for d in self._delivery_history if d.success)
        failures = total - successes
        return {
            "total_deliveries": total,
            "successful": successes,
            "failed": failures,
            "success_rate": round(successes / total * 100, 1) if total else 0.0,
            "queue_size": self._queue.qsize(),
            "running": self._running,
        }


_dispatcher: WebhookDispatcher | None = None


def get_dispatcher() -> WebhookDispatcher:
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = WebhookDispatcher()
    return _dispatcher


async def fire(event: str, payload: dict[str, Any]):
    dispatcher = get_dispatcher()
    await dispatcher.dispatch(event, payload)
