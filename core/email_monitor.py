# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""core/email_monitor.py
EmailMonitor — polls Gmail inbox for unread mail, alerts on urgent messages.
Uses Gmail API (OAuth2) with auto-refreshing token stored at ~/.jarvis/.
Gracefully degrades if credentials are missing.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger("email_monitor")

URGENT_KEYWORDS = ["urgent", "important", "asap", "deadline", "critical"]

EMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
TOKEN_PATH = Path.home() / ".jarvis" / "gmail_token.json"
CREDS_PATH = Path.home() / ".jarvis" / "gmail_credentials.json"


class EmailMonitor:

    def __init__(self, check_interval: int = 120, alert_callback=None):
        self._interval = check_interval
        self._callback = alert_callback
        self._service = None
        self._task: asyncio.Task | None = None
        self._running = False
        self._last_check_id = None

    async def start(self):
        if not CREDS_PATH.exists() and not TOKEN_PATH.exists():
            logger.warning("[EMAIL] No gmail credentials at %s — email monitor disabled", CREDS_PATH)
            return
        self._service = await self._build_service()
        if self._service is None:
            logger.warning("[EMAIL] Failed to authenticate — email monitor disabled")
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("[EMAIL] EmailMonitor started (interval=%ds)", self._interval)

    async def stop(self):
        self._running = False
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _build_service(self):
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build

            creds = None
            if TOKEN_PATH.exists():
                creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), EMAIL_SCOPES)
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    if not CREDS_PATH.exists():
                        return None
                    flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_PATH), EMAIL_SCOPES)
                    creds = flow.run_local_server(port=0)
                TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
                TOKEN_PATH.write_text(creds.to_json())
            return build("gmail", "v1", credentials=creds)
        except ImportError:
            logger.warning("[EMAIL] google-api-python-client not installed")
            return None
        except Exception as e:
            logger.warning("[EMAIL] Auth failed: %s", e)
            return None

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

    async def _check_inbox(self):
        if self._service is None:
            return []
        try:
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None, lambda: self._service.users().messages().list(
                    userId="me", q="in:inbox is:unread", maxResults=10
                ).execute()
            )
        except Exception as e:
            logger.warning("[EMAIL] List error: %s", e)
            return []
        messages = results.get("messages", [])
        alerts = []
        for msg_data in messages:
            msg_id = msg_data["id"]
            if msg_id == self._last_check_id:
                continue
            try:
                loop = asyncio.get_event_loop()
                msg = await loop.run_in_executor(
                    None, lambda: self._service.users().messages().get(
                        userId="me", id=msg_id
                    ).execute()
                )
            except Exception as e:
                logger.exception("[EMAIL] Failed to fetch message: %s", e)
                continue
            headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
            subject = headers.get("Subject", "(no subject)")
            sender = headers.get("From", "unknown")
            snippet = msg.get("snippet", "")
            text = (subject + " " + snippet).lower()
            priority = "urgent" if any(kw in text for kw in URGENT_KEYWORDS) else "info"
            alerts.append({
                "from": sender,
                "subject": subject,
                "snippet": snippet,
                "message_id": msg_id,
                "priority": priority,
            })
        self._last_check_id = messages[0]["id"] if messages else self._last_check_id
        return alerts


email_monitor: EmailMonitor | None = None
