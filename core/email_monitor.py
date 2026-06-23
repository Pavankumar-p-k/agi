"""core/email_monitor.py
EmailMonitor — polls Gmail inbox for unread mail, alerts on urgent messages.
Uses the production GmailClient from integrations/gmail/.
Gracefully degrades if credentials are missing.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("email_monitor")

URGENT_KEYWORDS = ["urgent", "important", "asap", "deadline", "critical"]


class EmailMonitor:

    def __init__(self, check_interval: int = 120, alert_callback=None):
        self._interval = check_interval
        self._callback = alert_callback
        self._client = None
        self._task: asyncio.Task | None = None
        self._running = False
        self._last_check_id = None

    async def start(self):
        try:
            from integrations.gmail import GmailClient
            self._client = GmailClient()
        except ImportError:
            logger.warning("[EMAIL] integrations.gmail not available")
            return
        except Exception as e:
            logger.warning("[EMAIL] Gmail client init failed: %s", e)
            return

        if not self._client._auth.has_credentials_file() and not self._client._auth.has_token():
            logger.warning("[EMAIL] No Gmail credentials — email monitor disabled")
            self._client = None
            return

        ok = await asyncio.to_thread(self._client.authenticate, headless=True)
        if not ok:
            logger.warning("[EMAIL] Failed to authenticate — email monitor disabled")
            self._client = None
            return

        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("[EMAIL] EmailMonitor started (interval=%ds)", self._interval)

    async def stop(self):
        self._running = False
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def health_check(self) -> bool:
        if self._client is None:
            return False
        try:
            result = await asyncio.to_thread(self._client.health_check)
            return result.get("healthy", False)
        except Exception as e:
            logger.warning("[EMAIL] Health check failed: %s", e)
            return False

    async def _poll_loop(self):
        while self._running:
            try:
                alerts = await self._check_inbox()
                for alert in alerts:
                    if self._callback:
                        await self._callback(alert)
            except Exception as e:
                logger.warning("[EMAIL] Poll error: %s", e)
            await asyncio.sleep(self._interval)

    async def _check_inbox(self) -> list[dict[str, Any]]:
        if self._client is None:
            return []
        try:
            msgs = await asyncio.to_thread(
                self._client.list_messages,
                query="in:inbox is:unread",
                max_results=10,
            )
        except Exception as e:
            logger.warning("[EMAIL] List error: %s", e)
            return []

        alerts = []
        for msg in msgs:
            if msg.id == self._last_check_id:
                continue
            text = (msg.subject + " " + msg.snippet).lower()
            priority = "urgent" if any(kw in text for kw in URGENT_KEYWORDS) else "info"
            alerts.append({
                "from": msg.sender,
                "subject": msg.subject,
                "snippet": msg.snippet,
                "message_id": msg.id,
                "priority": priority,
            })
        if msgs:
            self._last_check_id = msgs[0].id
        return alerts


email_monitor: EmailMonitor | None = None
