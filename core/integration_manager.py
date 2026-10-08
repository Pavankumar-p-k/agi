"""core/integration_manager — messaging integration hub.

Rebuilt from the committed contracts:

- tests/unit/test_integration_manager.py (491 lines, 6 classes + manager)
- tests/unit/test_gmail.py::TestGmailIntegration (GmailIntegration)
- tests/unit/test_whatsapp.py (WhatsAppIntegration)
- jarvis-export/cli/cli_commands.py doctor:
      from core.integration_manager import health_check_all   (async, module-level)
      health = asyncio.run(health_check_all()) -> {name: {"connected": bool,
                                                          "healthy": bool, ...}}
      (values consumed with .get(...) -> dicts, i.e. IntegrationStatus.to_dict())
      from core.integration_manager import get_integration_manager
      mgr.list_integrations() -> [{"name": ..., "connected": bool}]

Canonical import rule (tests/architecture/test_enforce_canonical.py) grandfathers
this module's dependency on channels/ — do not add api/routers/daemon/network
imports here.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class IntegrationStatus:
    """Health snapshot for one integration (doctor's table + CLI list)."""

    name: str
    connected: bool = False
    healthy: bool = False
    latency_ms: float = 0.0
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "connected": self.connected,
            "healthy": self.healthy,
            "latency_ms": round(self.latency_ms, 1),
            "error": self.error,
        }


class BaseIntegration:
    """Common contract for every integration.

    Subclasses set `name` + `env_keys` and override the async verbs.
    """

    name: str = "base"
    env_keys: dict[str, str] = {}

    def __init__(self) -> None:
        self._connected = False

    # -- credentials ------------------------------------------------------- #
    def _get_credential(self, key: str) -> Optional[str]:
        """Resolve a credential: integration env var first, then generic key."""
        env_name = self.env_keys.get(key, "")
        for candidate in (env_name, key.upper()):
            if candidate:
                value = os.getenv(candidate, "")
                if value:
                    return value
        return None

    # -- verbs (honest defaults) ------------------------------------------- #
    async def connect(self, **kwargs: Any) -> bool:
        return False

    async def disconnect(self) -> bool:
        self._connected = False
        return True

    async def health_check(self) -> IntegrationStatus:
        status = IntegrationStatus(name=self.name, connected=self._connected)
        if not self._connected:
            status.error = "Not connected"
        return status

    async def send(self, target: str, message: str, **kwargs: Any) -> bool:
        return False

    async def receive(self, target: str = "", **kwargs: Any) -> list[dict[str, Any]]:
        return []


# --------------------------------------------------------------------------- #
# Telegram                                                                    #
# --------------------------------------------------------------------------- #
class TelegramIntegration(BaseIntegration):
    name = "telegram"
    env_keys = {"bot_token": "TELEGRAM_BOT_TOKEN"}

    def __init__(self) -> None:
        super().__init__()
        self._token: str = ""
        self._update_offset: int = 0

    async def connect(self, bot_token: str = "", **kwargs: Any) -> bool:
        token = bot_token or self._get_credential("bot_token")
        if not token:
            return False
        self._token = token
        self._connected = True
        return True

    async def health_check(self) -> IntegrationStatus:
        status = IntegrationStatus(name=self.name, connected=self._connected)
        if not self._connected:
            status.error = "Not connected"
            return status
        token = self._token or self._get_credential("bot_token")
        if not token:
            status.error = "No bot token"
            return status
        started = time.perf_counter()
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://api.telegram.org/bot{token}/getMe"
                )
            status.latency_ms = max((time.perf_counter() - started) * 1000.0, 0.1)
            if response.status_code == 200:
                status.healthy = True
            else:
                status.error = f"HTTP {response.status_code}"
        except Exception as exc:  # noqa: BLE001 - health probes must not raise
            status.latency_ms = max((time.perf_counter() - started) * 1000.0, 0.1)
            status.error = str(exc)
        return status

    async def send(self, target: str, message: str, **kwargs: Any) -> bool:
        if not self._connected:
            return False
        try:
            from channels import channel_controller

            return bool(await channel_controller.send(self.name, target, message))
        except Exception as exc:  # noqa: BLE001
            logger.error("[telegram] send failed: %s", exc)
            return False

    async def receive(self, target: str = "", **kwargs: Any) -> list[dict[str, Any]]:
        if not self._connected:
            return []
        token = self._token or self._get_credential("bot_token")
        if not token:
            return []
        try:
            from telegram import Bot

            bot = Bot(token=token)
            updates = await bot.get_updates(offset=self._update_offset, timeout=1)
            messages: list[dict[str, Any]] = []
            for update in updates or []:
                message = getattr(update, "message", None)
                if message is None:
                    continue
                chat = getattr(update, "effective_chat", None)
                user = getattr(update, "effective_user", None)
                date = getattr(message, "date", None)
                messages.append(
                    {
                        "id": getattr(update, "update_id", 0),
                        "chat_id": getattr(chat, "id", None),
                        "user_id": getattr(user, "id", None),
                        "sender": getattr(user, "full_name", "") or "",
                        "text": getattr(message, "text", "") or "",
                        "timestamp": date.isoformat() if date is not None else "",
                    }
                )
                self._update_offset = max(
                    self._update_offset, getattr(update, "update_id", 0) + 1
                )
            return messages
        except Exception as exc:  # noqa: BLE001
            logger.error("[telegram] receive failed: %s", exc)
            return []


# --------------------------------------------------------------------------- #
# Discord                                                                     #
# --------------------------------------------------------------------------- #
class DiscordIntegration(BaseIntegration):
    name = "discord"
    env_keys = {"token": "DISCORD_TOKEN"}
    _API = "https://discord.com/api/v10"

    def __init__(self) -> None:
        super().__init__()
        self._token: str = ""

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bot {self._token}"}

    async def connect(self, token: str = "", **kwargs: Any) -> bool:
        token = token or self._get_credential("token")
        if not token:
            return False
        self._token = token
        self._connected = True
        return True

    async def health_check(self) -> IntegrationStatus:
        status = IntegrationStatus(name=self.name, connected=self._connected)
        if not self._connected:
            status.error = "Not connected"
            return status
        started = time.perf_counter()
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self._API}/users/@me", headers=self._headers()
                )
            status.latency_ms = max((time.perf_counter() - started) * 1000.0, 0.1)
            if response.status_code == 200:
                status.healthy = True
            else:
                status.error = f"HTTP {response.status_code}"
        except Exception as exc:  # noqa: BLE001
            status.latency_ms = max((time.perf_counter() - started) * 1000.0, 0.1)
            status.error = str(exc)
        return status

    async def send(self, target: str, message: str, **kwargs: Any) -> bool:
        if not self._connected or not target:
            return False
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self._API}/channels/{target}/messages",
                    headers=self._headers(),
                    json={"content": message},
                )
            return response.status_code in (200, 201, 204)
        except Exception as exc:  # noqa: BLE001
            logger.error("[discord] send failed: %s", exc)
            return False

    async def receive(self, target: str = "", **kwargs: Any) -> list[dict[str, Any]]:
        if not self._connected or not target:
            return []
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self._API}/channels/{target}/messages",
                    headers=self._headers(),
                )
                response.raise_for_status()
                payload = response.json()
            messages: list[dict[str, Any]] = []
            for item in payload if isinstance(payload, list) else []:
                author = item.get("author") or {}
                attachments = item.get("attachments") or []
                messages.append(
                    {
                        "id": item.get("id", ""),
                        "channel_id": item.get("channel_id", target),
                        "author_id": author.get("id", ""),
                        "author": author.get("username", ""),
                        "content": item.get("content", ""),
                        "timestamp": item.get("timestamp", ""),
                        "has_attachments": bool(attachments),
                    }
                )
            return messages
        except Exception as exc:  # noqa: BLE001
            logger.error("[discord] receive failed: %s", exc)
            return []


# --------------------------------------------------------------------------- #
# Slack                                                                       #
# --------------------------------------------------------------------------- #
class SlackIntegration(BaseIntegration):
    name = "slack"
    env_keys = {"bot_token": "SLACK_BOT_TOKEN"}

    def __init__(self) -> None:
        super().__init__()
        self._token: str = ""
        self._web_client: Any = None

    async def connect(self, bot_token: str = "", **kwargs: Any) -> bool:
        token = bot_token or self._get_credential("bot_token")
        if not token:
            return False
        try:
            from slack_sdk import WebClient

            self._web_client = WebClient(token=token)
            self._token = token
            self._connected = True
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("[slack] connect failed: %s", exc)
            return False

    async def health_check(self) -> IntegrationStatus:
        status = IntegrationStatus(name=self.name, connected=self._connected)
        if not self._connected:
            status.error = "Not connected"
            return status
        if self._web_client is None:
            status.error = "No web client"
            return status
        started = time.perf_counter()
        try:
            response = self._web_client.auth_test()
            status.latency_ms = max((time.perf_counter() - started) * 1000.0, 0.1)
            status.healthy = bool(response.get("ok")) if isinstance(response, dict) else bool(response)
            if not status.healthy:
                status.error = "auth_test returned not ok"
        except Exception as exc:  # noqa: BLE001
            status.latency_ms = max((time.perf_counter() - started) * 1000.0, 0.1)
            status.error = str(exc)
        return status

    async def send(self, target: str, message: str, **kwargs: Any) -> bool:
        if not self._connected or self._web_client is None:
            return False
        try:
            self._web_client.chat_postMessage(channel=target, text=message)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("[slack] send failed: %s", exc)
            return False

    async def receive(self, target: str = "", **kwargs: Any) -> list[dict[str, Any]]:
        if not self._connected or self._web_client is None or not target:
            return []
        try:
            response = self._web_client.conversations_history(channel=target)
            raw = response.get("messages", []) if isinstance(response, dict) else []
            return [
                {
                    "ts": item.get("ts", ""),
                    "user": item.get("user", ""),
                    "text": item.get("text", ""),
                    "type": item.get("type", "message"),
                }
                for item in raw
            ]
        except Exception as exc:  # noqa: BLE001
            logger.error("[slack] receive failed: %s", exc)
            return []


# --------------------------------------------------------------------------- #
# WhatsApp                                                                    #
# --------------------------------------------------------------------------- #
class WhatsAppIntegration(BaseIntegration):
    name = "whatsapp"
    env_keys = {
        "token": "META_WHATSAPP_TOKEN",
        "phone_id": "META_WHATSAPP_PHONE_ID",
    }

    def __init__(self) -> None:
        super().__init__()
        self._token: str = ""
        self._phone_id: str = ""
        self._provider: Any = None
        self._webhook_handler: Any = None
        self._history: Any = None
        self._phone_manager: Any = None

    def _wire_services(self) -> None:
        """Attach history + phone manager after a successful connect
        (real construction; failure to wire degrades honestly to None)."""
        if self._history is None:
            try:
                from integrations.whatsapp import WhatsAppHistory

                self._history = WhatsAppHistory()
            except Exception as exc:  # noqa: BLE001
                logger.warning("[whatsapp] history unavailable: %s", exc)
        if self._phone_manager is None:
            try:
                from integrations.whatsapp import WhatsAppPhoneManager

                self._phone_manager = WhatsAppPhoneManager()
            except Exception as exc:  # noqa: BLE001
                logger.warning("[whatsapp] phone manager unavailable: %s", exc)

    def _get_provider_class(self, provider: str) -> Any:
        """Resolve a provider name to its class; None for unknown names.

        Contract: _get_provider_class("cloud_api") -> WhatsAppCloudAPIProvider,
        _get_provider_class("twilio") -> TwilioWhatsAppProvider, unknown -> None.
        """
        if provider in ("cloud_api", "whatsapp_cloud_api", "meta"):
            from integrations.whatsapp import WhatsAppCloudAPIProvider

            return WhatsAppCloudAPIProvider
        if provider in ("twilio",):
            from integrations.whatsapp import TwilioWhatsAppProvider

            return TwilioWhatsAppProvider
        return None

    async def connect(self, token: str = "", phone_id: str = "",
                      provider: str = "", **kwargs: Any) -> bool:
        token = token or self._get_credential("token")
        phone_id = phone_id or self._get_credential("phone_id")
        if not token or not phone_id:
            return False
        self._token = token
        self._phone_id = phone_id
        provider_name = provider or str(kwargs.get("provider") or "")
        cls = self._get_provider_class(provider_name)
        if cls is None:
            # No provider selected (default): credentials are accepted now;
            # live verification happens on first health_check/send, which
            # report honest network results.
            self._connected = True
            self._wire_services()
            return True
        try:
            instance = cls()
            ok = await instance.connect(token=token, phone_id=phone_id)
        except Exception as exc:  # noqa: BLE001
            logger.error("[whatsapp] provider connect failed: %s", exc)
            return False
        if not ok:
            return False
        self._provider = instance
        self._connected = True
        self._wire_services()
        return True

    async def disconnect(self) -> bool:
        provider = self._provider
        ok = True
        if provider is not None:
            try:
                ok = bool(await provider.disconnect())
            except Exception as exc:  # noqa: BLE001
                logger.error("[whatsapp] provider disconnect failed: %s", exc)
                ok = False
        self._connected = False
        self._provider = None
        return ok

    async def _ensure_provider(self) -> Any:
        """Build + connect the Cloud API provider on first use (real network)."""
        if self._provider is not None:
            return self._provider
        if not (self._token and self._phone_id):
            return None
        try:
            from integrations.whatsapp import WhatsAppCloudAPIProvider

            provider = WhatsAppCloudAPIProvider()
            ok = await provider.connect(token=self._token, phone_id=self._phone_id)
            if ok:
                self._provider = provider
                return provider
            logger.warning("[whatsapp] provider health check failed on connect")
        except Exception as exc:  # noqa: BLE001
            logger.error("[whatsapp] provider init failed: %s", exc)
        return None

    async def health_check(self) -> IntegrationStatus:
        status = IntegrationStatus(name=self.name, connected=self._connected)
        if not self._connected:
            status.error = "Not connected"
            return status
        provider = await self._ensure_provider()
        if provider is None:
            status.error = "provider unavailable (no credentials or connect failed)"
            return status
        started = time.perf_counter()
        try:
            ok = await provider.health_check()
            status.latency_ms = max((time.perf_counter() - started) * 1000.0, 0.1)
            status.healthy = bool(ok)
            if not status.healthy:
                status.error = "provider health check failed"
        except Exception as exc:  # noqa: BLE001
            status.latency_ms = max((time.perf_counter() - started) * 1000.0, 0.1)
            status.error = str(exc)
        return status

    async def send(self, target: str, message: str, **kwargs: Any) -> bool:
        if not self._connected:
            return False
        provider = await self._ensure_provider()
        if provider is None:
            return False
        try:
            media_url = kwargs.get("media_url")
            media_type = str(kwargs.get("media_type") or "")
            if media_type in ("interactive_buttons", "interactive_list"):
                body = kwargs.get("interactive_body")
                if body is None:
                    logger.error("[whatsapp] %s send missing interactive_body", media_type)
                    return False
                if media_type == "interactive_buttons":
                    result = await provider.send_interactive_buttons(target, body)
                else:
                    result = await provider.send_interactive_list(target, body)
            elif media_url:
                result = await provider.send_image(
                    target,
                    media_url,
                    caption=kwargs.get("caption"),
                    media_type=media_type or "image",
                )
            else:
                extra = {
                    k: kwargs[k]
                    for k in ("preview_url", "context_message_id")
                    if k in kwargs
                }
                result = await provider.send_text(target, message, **extra)
            return bool(getattr(result, "success", False))
        except Exception as exc:  # noqa: BLE001
            logger.error("[whatsapp] send failed: %s", exc)
            return False

    async def receive(self, target: str = "", **kwargs: Any) -> list[dict[str, Any]]:
        """Drain messages buffered by the webhook handler (inbound is push)."""
        handler = self._webhook_handler
        if handler is None:
            return []
        try:
            messages = handler.get_buffered_messages()
            if hasattr(messages, "__await__"):
                messages = await messages
            out: list[dict[str, Any]] = []
            for msg in messages or []:
                ts = getattr(msg, "timestamp", None)
                out.append(
                    {
                        "id": getattr(msg, "id", ""),
                        "from": getattr(msg, "from_number", ""),
                        "to": getattr(msg, "to_number", ""),
                        "text": getattr(msg, "text", "") or "",
                        "type": str(getattr(msg, "type", "")),
                        "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts or ""),
                    }
                )
            return out
        except Exception as exc:  # noqa: BLE001
            logger.error("[whatsapp] receive failed: %s", exc)
            return []

    # -- history (WhatsAppHistory delegation) ------------------------------ #
    async def get_conversation(self, phone_a: str, phone_b: str,
                               **kwargs: Any) -> list[dict[str, Any]]:
        if self._history is None:
            return []
        try:
            return list(await self._history.get_conversation(phone_a, phone_b))
        except Exception as exc:  # noqa: BLE001
            logger.error("[whatsapp] get_conversation failed: %s", exc)
            return []

    async def search_conversations(self, query: str, **kwargs: Any) -> list[dict[str, Any]]:
        if self._history is None:
            return []
        try:
            return list(await self._history.search_messages(query))
        except Exception as exc:  # noqa: BLE001
            logger.error("[whatsapp] search_conversations failed: %s", exc)
            return []

    async def get_recent_conversations(self, **kwargs: Any) -> list[dict[str, Any]]:
        if self._history is None:
            return []
        try:
            return list(await self._history.get_recent_conversations())
        except Exception as exc:  # noqa: BLE001
            logger.error("[whatsapp] get_recent_conversations failed: %s", exc)
            return []

    # -- multi-phone (WhatsAppPhoneManager delegation) --------------------- #
    async def register_phone(self, phone_number: str, token: str = "",
                             phone_id: str = "", provider: str = "cloud_api",
                             **kwargs: Any) -> bool:
        """Connect a provider for `phone_number` and register it."""
        cls = self._get_provider_class(provider)
        if cls is None:
            return False
        try:
            instance = cls()
            ok = await instance.connect(token=token, phone_id=phone_id)
        except Exception as exc:  # noqa: BLE001
            logger.error("[whatsapp] register_phone connect failed: %s", exc)
            return False
        if not ok:
            return False
        if self._phone_manager is None:
            try:
                from integrations.whatsapp import WhatsAppPhoneManager

                self._phone_manager = WhatsAppPhoneManager()
            except Exception as exc:  # noqa: BLE001
                logger.warning("[whatsapp] phone manager unavailable: %s", exc)
                return False
        try:
            result = self._phone_manager.register_phone(phone_number, instance)
            if hasattr(result, "__await__"):
                await result
        except Exception as exc:  # noqa: BLE001
            logger.error("[whatsapp] register_phone failed: %s", exc)
            return False
        return True

    async def unregister_phone(self, phone_number: str, **kwargs: Any) -> bool:
        if self._phone_manager is None:
            return False
        try:
            result = self._phone_manager.unregister_phone(phone_number)
            if hasattr(result, "__await__"):
                result = await result
            return bool(result)
        except Exception as exc:  # noqa: BLE001
            logger.error("[whatsapp] unregister_phone failed: %s", exc)
            return False


# --------------------------------------------------------------------------- #
# GitHub                                                                      #
# --------------------------------------------------------------------------- #
class GitHubIntegration(BaseIntegration):
    name = "github"
    env_keys = {"token": "GITHUB_TOKEN"}
    _API = "https://api.github.com"

    def __init__(self) -> None:
        super().__init__()
        self._token: str = ""

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
        }

    async def connect(self, token: str = "", **kwargs: Any) -> bool:
        token = token or self._get_credential("token")
        if not token:
            return False
        self._token = token
        self._connected = True
        return True

    async def health_check(self) -> IntegrationStatus:
        status = IntegrationStatus(name=self.name, connected=self._connected)
        if not self._connected:
            status.error = "Not connected"
            return status
        started = time.perf_counter()
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self._API}/user", headers=self._headers()
                )
            status.latency_ms = max((time.perf_counter() - started) * 1000.0, 0.1)
            if response.status_code == 200:
                status.healthy = True
            else:
                status.error = f"HTTP {response.status_code}"
        except Exception as exc:  # noqa: BLE001
            status.latency_ms = max((time.perf_counter() - started) * 1000.0, 0.1)
            status.error = str(exc)
        return status

    async def send(self, target: str, message: str, **kwargs: Any) -> bool:
        """Create an issue in `target` ("owner/repo")."""
        if not self._connected or not target:
            return False
        title = str(kwargs.get("title") or "Issue from JARVIS")
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self._API}/repos/{target}/issues",
                    headers=self._headers(),
                    json={"title": title, "body": message},
                )
            return response.status_code == 201
        except Exception as exc:  # noqa: BLE001
            logger.error("[github] send failed: %s", exc)
            return False

    async def receive(self, target: str = "", **kwargs: Any) -> list[dict[str, Any]]:
        if not self._connected:
            return []
        repo = str(kwargs.get("repo") or target or "")
        if not repo:
            return []
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self._API}/repos/{repo}/issues", headers=self._headers()
                )
                response.raise_for_status()
                payload = response.json()
            issues: list[dict[str, Any]] = []
            for item in payload if isinstance(payload, list) else []:
                issues.append(
                    {
                        "type": "issue",
                        "id": item.get("id"),
                        "number": item.get("number"),
                        "title": item.get("title", ""),
                        "state": item.get("state", ""),
                        "body": item.get("body") or "",
                        "url": item.get("html_url", ""),
                        "author": (item.get("user") or {}).get("login", ""),
                        "labels": [lbl.get("name", "") for lbl in item.get("labels") or []],
                        "created_at": item.get("created_at", ""),
                        "updated_at": item.get("updated_at", ""),
                    }
                )
            return issues
        except Exception as exc:  # noqa: BLE001
            logger.error("[github] receive failed: %s", exc)
            return []


# --------------------------------------------------------------------------- #
# Google Drive                                                                #
# --------------------------------------------------------------------------- #
class GoogleDriveIntegration(BaseIntegration):
    name = "google_drive"
    env_keys = {"api_key": "GOOGLE_API_KEY"}
    _API = "https://www.googleapis.com/drive/v3"

    async def connect(self, **kwargs: Any) -> bool:
        self._connected = True
        return True

    async def health_check(self) -> IntegrationStatus:
        status = IntegrationStatus(name=self.name, connected=self._connected)
        if not self._connected:
            status.error = "Not connected"
            return status
        api_key = self._get_credential("api_key")
        if not api_key:
            status.error = "No API key configured"
            return status
        started = time.perf_counter()
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self._API}/about",
                    params={"fields": "user", "key": api_key},
                )
            status.latency_ms = max((time.perf_counter() - started) * 1000.0, 0.1)
            if response.status_code == 200:
                status.healthy = True
            else:
                status.error = f"HTTP {response.status_code}"
        except Exception as exc:  # noqa: BLE001
            status.latency_ms = max((time.perf_counter() - started) * 1000.0, 0.1)
            status.error = str(exc)
        return status

    async def send(self, target: str, message: str, **kwargs: Any) -> bool:
        # Drive has no chat-send primitive; upload flows live in core/tools.
        return False

    async def receive(self, target: str = "", **kwargs: Any) -> list[dict[str, Any]]:
        return []


# --------------------------------------------------------------------------- #
# Gmail                                                                       #
# --------------------------------------------------------------------------- #
class GmailIntegration(BaseIntegration):
    name = "gmail"
    env_keys = {}

    def __init__(self) -> None:
        super().__init__()
        self._gmail_client: Any = None

    async def connect(self, **kwargs: Any) -> bool:
        try:
            from integrations.gmail import GmailClient

            client = GmailClient()
            if not client.authenticate():
                return False
            self._gmail_client = client
            self._connected = True
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("[gmail] connect failed: %s", exc)
            return False

    async def health_check(self) -> IntegrationStatus:
        status = IntegrationStatus(name=self.name, connected=self._connected)
        if not self._connected:
            status.error = "Not connected"
            return status
        client = self._gmail_client
        if client is None:
            status.error = "No Gmail client"
            return status
        started = time.perf_counter()
        try:
            status.healthy = bool(client.is_authenticated())
            status.latency_ms = max((time.perf_counter() - started) * 1000.0, 0.1)
            if not status.healthy:
                status.error = "not authenticated"
        except Exception as exc:  # noqa: BLE001
            status.latency_ms = max((time.perf_counter() - started) * 1000.0, 0.1)
            status.error = str(exc)
        return status

    async def send(self, target: str, message: str, **kwargs: Any) -> bool:
        if not self._connected or self._gmail_client is None:
            return False
        subject = str(kwargs.get("subject") or "(no subject)")
        try:
            result = self._gmail_client.send_message(target, subject, message)
            return bool(result)
        except Exception as exc:  # noqa: BLE001
            logger.error("[gmail] send failed: %s", exc)
            return False

    async def receive(self, target: str = "", **kwargs: Any) -> list[dict[str, Any]]:
        if not self._connected or self._gmail_client is None:
            return []
        try:
            messages = self._gmail_client.list_messages()
            out: list[dict[str, Any]] = []
            for msg in messages or []:
                date = getattr(msg, "date", None)
                out.append(
                    {
                        "id": getattr(msg, "id", ""),
                        "thread_id": getattr(msg, "thread_id", ""),
                        "subject": getattr(msg, "subject", ""),
                        "sender": getattr(msg, "sender", ""),
                        "recipients": list(getattr(msg, "recipients", []) or []),
                        "date": date.isoformat() if date is not None else "",
                        "snippet": getattr(msg, "snippet", ""),
                        "unread": bool(getattr(msg, "unread", False)),
                        "labels": list(getattr(msg, "labels", []) or []),
                    }
                )
            return out
        except Exception as exc:  # noqa: BLE001
            logger.error("[gmail] receive failed: %s", exc)
            return []


# --------------------------------------------------------------------------- #
# Manager                                                                     #
# --------------------------------------------------------------------------- #
class IntegrationManager:
    """Registry + async verbs over all integrations."""

    def __init__(self) -> None:
        self._integrations: dict[str, BaseIntegration] = {}

    def register(self, integration: BaseIntegration) -> None:
        self._integrations[integration.name] = integration

    def get(self, name: str) -> Optional[BaseIntegration]:
        return self._integrations.get(name)

    def list_integrations(self) -> list[dict[str, Any]]:
        return [
            {"name": inst.name, "connected": bool(inst._connected)}
            for inst in self._integrations.values()
        ]

    async def connect(self, name: str, **kwargs: Any) -> bool:
        inst = self._integrations.get(name)
        if inst is None:
            return False
        try:
            return bool(await inst.connect(**kwargs))
        except Exception as exc:  # noqa: BLE001
            logger.error("[%s] connect failed: %s", name, exc)
            return False

    async def disconnect(self, name: str) -> bool:
        inst = self._integrations.get(name)
        if inst is None:
            return False
        try:
            return bool(await inst.disconnect())
        except Exception as exc:  # noqa: BLE001
            logger.error("[%s] disconnect failed: %s", name, exc)
            return False

    async def health_check(self, name: str) -> IntegrationStatus:
        inst = self._integrations.get(name)
        if inst is None:
            return IntegrationStatus(name=name, error="Unknown integration")
        try:
            return await inst.health_check()
        except Exception as exc:  # noqa: BLE001
            return IntegrationStatus(name=name, connected=inst._connected, error=str(exc))

    async def send(self, name: str, target: str, message: str, **kwargs: Any) -> bool:
        inst = self._integrations.get(name)
        if inst is None:
            return False
        try:
            return bool(await inst.send(target, message, **kwargs))
        except Exception as exc:  # noqa: BLE001
            logger.error("[%s] send failed: %s", name, exc)
            return False

    async def receive(self, name: str, target: str = "", **kwargs: Any) -> list[dict[str, Any]]:
        inst = self._integrations.get(name)
        if inst is None:
            return []
        try:
            return list(await inst.receive(target, **kwargs))
        except Exception as exc:  # noqa: BLE001
            logger.error("[%s] receive failed: %s", name, exc)
            return []

    async def health_check_all(self) -> dict[str, dict[str, Any]]:
        """{name: status.to_dict()} for every registered integration.

        Doctor consumes these with `.get("connected")` / `.get("healthy")`.
        """
        results: dict[str, dict[str, Any]] = {}
        for name, inst in self._integrations.items():
            try:
                status = await inst.health_check()
            except Exception as exc:  # noqa: BLE001
                status = IntegrationStatus(name=name, connected=inst._connected, error=str(exc))
            results[name] = status.to_dict()
        return results


# --------------------------------------------------------------------------- #
# Module surface (doctor + CLI)                                                #
# --------------------------------------------------------------------------- #
_manager: Optional[IntegrationManager] = None

_ALL_INTEGRATION_CLASSES = (
    TelegramIntegration,
    DiscordIntegration,
    SlackIntegration,
    WhatsAppIntegration,
    GitHubIntegration,
    GoogleDriveIntegration,
    GmailIntegration,
)


def get_integration_manager() -> IntegrationManager:
    """Singleton manager with every known integration registered."""
    global _manager
    if _manager is None:
        manager = IntegrationManager()
        for cls in _ALL_INTEGRATION_CLASSES:
            manager.register(cls())
        _manager = manager
    return _manager


def reset_integration_manager() -> None:
    """Drop the cached manager (test seam)."""
    global _manager
    _manager = None


async def health_check_all() -> dict[str, dict[str, Any]]:
    """Module-level doctor entry: health of every integration."""
    return await get_integration_manager().health_check_all()


__all__ = [
    "IntegrationStatus",
    "BaseIntegration",
    "TelegramIntegration",
    "DiscordIntegration",
    "SlackIntegration",
    "WhatsAppIntegration",
    "GitHubIntegration",
    "GoogleDriveIntegration",
    "GmailIntegration",
    "IntegrationManager",
    "get_integration_manager",
    "reset_integration_manager",
    "health_check_all",
]
