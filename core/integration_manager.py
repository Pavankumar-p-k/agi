"""core/integration_manager.py
Unified IntegrationManager for external service connections.
Wraps existing channel systems and provides connect/disconnect/health_check/send/receive.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DATA_DIR = Path.home() / ".jarvis" / "integrations"


@dataclass
class IntegrationStatus:
    name: str
    connected: bool = False
    healthy: bool = False
    error: str = ""
    last_connected: str = ""
    latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "connected": self.connected,
            "healthy": self.healthy,
            "error": self.error,
            "last_connected": self.last_connected,
            "latency_ms": round(self.latency_ms, 1),
        }


class BaseIntegration(ABC):
    name: str = ""

    def __init__(self):
        self._config: dict[str, Any] = {}
        self._connected = False
        self._load_config()

    @abstractmethod
    async def connect(self, **kwargs) -> bool:
        ...

    @abstractmethod
    async def disconnect(self) -> bool:
        ...

    @abstractmethod
    async def health_check(self) -> IntegrationStatus:
        ...

    @abstractmethod
    async def send(self, target: str, message: str, **kwargs) -> bool:
        ...

    @abstractmethod
    async def receive(self, **kwargs) -> list[dict[str, Any]]:
        ...

    def _config_path(self) -> Path:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        return DATA_DIR / f"{self.name}.json"

    def _load_config(self):
        path = self._config_path()
        if path.exists():
            try:
                self._config = json.loads(path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"[{self.name}] Failed to load config: {e}")
                self._config = {}

    def _save_config(self):
        path = self._config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self._config, indent=2), encoding="utf-8")

    def _get_credential(self, key: str) -> str | None:
        from core.api_key_vault import vault
        val = vault.get(f"{self.name}_{key}")
        if val:
            return val
        return os.getenv(f"{self.name.upper()}_{key.upper()}") or self._config.get(key)


class IntegrationManager:
    def __init__(self):
        self._integrations: dict[str, BaseIntegration] = {}
        self._status_cache: dict[str, IntegrationStatus] = {}

    def register(self, integration: BaseIntegration):
        self._integrations[integration.name] = integration

    def get(self, name: str) -> BaseIntegration | None:
        return self._integrations.get(name)

    def list_integrations(self) -> list[dict[str, Any]]:
        return [
            {"name": name, "connected": integ._connected}
            for name, integ in self._integrations.items()
        ]

    async def connect(self, name: str, **kwargs) -> bool:
        integ = self.get(name)
        if not integ:
            logger.error(f"Unknown integration: {name}")
            return False
        result = await integ.connect(**kwargs)
        if result:
            self._status_cache.pop(name, None)
        return result

    async def disconnect(self, name: str) -> bool:
        integ = self.get(name)
        if not integ:
            return False
        result = await integ.disconnect()
        self._status_cache.pop(name, None)
        return result

    async def health_check(self, name: str) -> IntegrationStatus:
        integ = self.get(name)
        if not integ:
            return IntegrationStatus(name=name, error="Unknown integration")
        if name in self._status_cache:
            return self._status_cache[name]
        status = await integ.health_check()
        self._status_cache[name] = status
        return status

    async def health_check_all(self) -> dict[str, IntegrationStatus]:
        results = {}
        for name, integ in self._integrations.items():
            try:
                if not integ._connected:
                    await integ.connect()
                results[name] = await integ.health_check()
            except Exception as e:
                results[name] = IntegrationStatus(name=name, error=str(e))
        self._status_cache.update(results)
        return results

    async def send(self, name: str, target: str, message: str, **kwargs) -> bool:
        integ = self.get(name)
        if not integ:
            logger.error(f"Unknown integration: {name}")
            return False
        return await integ.send(target, message, **kwargs)

    async def receive(self, name: str, **kwargs) -> list[dict[str, Any]]:
        integ = self.get(name)
        if not integ:
            logger.error(f"Unknown integration: {name}")
            return []
        return await integ.receive(**kwargs)


class GmailIntegration(BaseIntegration):
    name = "gmail"

    def __init__(self):
        super().__init__()
        self._gmail_client = None

    async def connect(self, **kwargs) -> bool:
        self._config.update(kwargs)
        self._save_config()
        try:
            headless = kwargs.get("headless", False)
            from integrations.gmail import GmailClient
            self._gmail_client = GmailClient()
            ok = await asyncio.to_thread(self._gmail_client.authenticate, headless=headless)
            self._connected = ok
            return ok
        except Exception as e:
            logger.error(f"[gmail] Connect failed: {e}")
            return False

    async def disconnect(self) -> bool:
        self._connected = False
        self._gmail_client = None
        return True

    async def health_check(self) -> IntegrationStatus:
        status = IntegrationStatus(name=self.name, connected=self._connected)
        if not self._connected:
            status.error = "Not connected"
            return status
        try:
            result = await asyncio.to_thread(self._gmail_client.health_check)
            status.healthy = result.get("healthy", False)
            status.latency_ms = result.get("latency_ms", 0)
            if not status.healthy:
                status.error = result.get("error", "Health check failed")
        except Exception as e:
            status.healthy = False
            status.error = str(e)
        return status

    async def send(self, target: str, message: str, **kwargs) -> bool:
        if not self._connected or not self._gmail_client:
            return False
        try:
            result = await asyncio.to_thread(
                self._gmail_client.send_message,
                to=target,
                subject=kwargs.get("subject", ""),
                body=message,
                cc=kwargs.get("cc"),
                body_type=kwargs.get("body_type", "plain"),
                thread_id=kwargs.get("thread_id"),
            )
            return result is not None
        except Exception as e:
            logger.error(f"[gmail] Send failed: {e}")
            return False

    async def receive(self, **kwargs) -> list[dict[str, Any]]:
        if not self._connected or not self._gmail_client:
            return []
        try:
            query = kwargs.get("query", "in:inbox")
            max_results = kwargs.get("max_results", 20)
            msgs = await asyncio.to_thread(
                self._gmail_client.list_messages,
                query=query,
                max_results=max_results,
            )
            return [{
                "id": m.id,
                "thread_id": m.thread_id,
                "subject": m.subject,
                "from": m.sender,
                "to": ", ".join(m.recipients),
                "date": m.date.isoformat() if m.date else "",
                "snippet": m.snippet,
                "unread": m.unread,
                "labels": m.labels,
                "attachments": [{"filename": a.filename, "size": a.size} for a in m.attachments],
            } for m in msgs]
        except Exception as e:
            logger.error(f"[gmail] Receive failed: {e}")
            return []


class TelegramIntegration(BaseIntegration):
    name = "telegram"

    def __init__(self):
        super().__init__()
        self._update_offset = 0

    async def connect(self, **kwargs) -> bool:
        self._config.update(kwargs)
        self._save_config()
        token = self._get_credential("bot_token") or kwargs.get("bot_token")
        if token:
            self._connected = True
            return True
        logger.warning("[telegram] No bot token configured")
        return False

    async def disconnect(self) -> bool:
        self._connected = False
        return True

    async def health_check(self) -> IntegrationStatus:
        status = IntegrationStatus(name=self.name, connected=self._connected)
        if not self._connected:
            status.error = "Not connected"
            return status
        try:
            import httpx
            token = self._get_credential("bot_token")
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"https://api.telegram.org/bot{token}/getMe", timeout=5)
                status.healthy = resp.status_code == 200
                status.latency_ms = resp.elapsed.total_seconds() * 1000
                if not status.healthy:
                    status.error = f"Telegram API error: {resp.status_code}"
        except Exception as e:
            status.healthy = False
            status.error = str(e)
        return status

    async def send(self, target: str, message: str, **kwargs) -> bool:
        if not self._connected:
            return False
        try:
            from channels import channel_controller
            await channel_controller.send("telegram", target, message)
            return True
        except Exception as e:
            logger.error(f"[telegram] Send failed: {e}")
            return False

    async def receive(self, **kwargs) -> list[dict[str, Any]]:
        if not self._connected:
            return []
        try:
            from telegram import Bot
            token = self._get_credential("bot_token")
            bot = Bot(token=token)
            timeout = kwargs.get("timeout", 2)
            limit = min(kwargs.get("limit", 10), 100)
            updates = await bot.get_updates(
                offset=self._update_offset or None,
                timeout=timeout,
                limit=limit,
                allowed_updates=["message"],
            )
            messages = []
            for u in updates:
                if u.update_id >= self._update_offset:
                    self._update_offset = u.update_id + 1
                if u.message and u.message.text:
                    messages.append({
                        "id": str(u.update_id),
                        "chat_id": str(u.effective_chat.id) if u.effective_chat else "",
                        "from_id": str(u.effective_user.id) if u.effective_user else "",
                        "from_name": u.effective_user.full_name if u.effective_user else "",
                        "text": u.message.text,
                        "date": u.message.date.isoformat() if u.message.date else "",
                    })
            return messages
        except Exception as e:
            logger.error(f"[telegram] Receive failed: {e}")
            return []


class DiscordIntegration(BaseIntegration):
    name = "discord"

    async def connect(self, **kwargs) -> bool:
        self._config.update(kwargs)
        self._save_config()
        token = self._get_credential("token") or kwargs.get("token")
        if token:
            self._connected = True
            return True
        logger.warning("[discord] No bot token configured")
        return False

    async def disconnect(self) -> bool:
        self._connected = False
        return True

    async def health_check(self) -> IntegrationStatus:
        status = IntegrationStatus(name=self.name, connected=self._connected)
        if not self._connected:
            status.error = "Not connected"
            return status
        try:
            import httpx
            token = self._get_credential("token")
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://discord.com/api/v10/users/@me",
                    headers={"Authorization": f"Bot {token}"},
                    timeout=5,
                )
                status.healthy = resp.status_code == 200
                status.latency_ms = resp.elapsed.total_seconds() * 1000
                if not status.healthy:
                    status.error = f"Discord API error: {resp.status_code}"
        except Exception as e:
            status.healthy = False
            status.error = str(e)
        return status

    async def send(self, target: str, message: str, **kwargs) -> bool:
        if not self._connected:
            return False
        try:
            from channels import channel_controller
            await channel_controller.send("discord", target, message)
            return True
        except Exception as e:
            logger.error(f"[discord] Send failed: {e}")
            return False

    async def receive(self, **kwargs) -> list[dict[str, Any]]:
        if not self._connected:
            return []
        try:
            import httpx
            token = self._get_credential("token")
            channel_id = kwargs.get("target", kwargs.get("channel_id", ""))
            if not channel_id:
                logger.warning("[discord] receive requires target or channel_id")
                return []
            limit = min(kwargs.get("limit", 10), 100)
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"https://discord.com/api/v10/channels/{channel_id}/messages",
                    headers={"Authorization": f"Bot {token}"},
                    params={"limit": limit},
                    timeout=10,
                )
                if resp.status_code == 200:
                    messages = []
                    for m in resp.json():
                        messages.append({
                            "id": m["id"],
                            "channel_id": channel_id,
                            "author_id": m["author"]["id"],
                            "author_name": m["author"]["username"],
                            "content": m.get("content", ""),
                            "timestamp": m.get("timestamp", ""),
                            "has_attachments": len(m.get("attachments", [])) > 0,
                        })
                    return messages
                logger.warning(f"[discord] Receive failed: {resp.status_code}")
        except Exception as e:
            logger.error(f"[discord] Receive failed: {e}")
        return []


class SlackIntegration(BaseIntegration):
    name = "slack"

    def __init__(self):
        super().__init__()
        self._web_client = None

    async def connect(self, **kwargs) -> bool:
        self._config.update(kwargs)
        self._save_config()
        token = self._get_credential("bot_token") or kwargs.get("bot_token")
        if token:
            from slack_sdk import WebClient
            self._web_client = WebClient(token=token)
            self._connected = True
            return True
        logger.warning("[slack] No bot token configured")
        return False

    async def disconnect(self) -> bool:
        self._web_client = None
        self._connected = False
        return True

    async def health_check(self) -> IntegrationStatus:
        status = IntegrationStatus(name=self.name, connected=self._connected)
        if not self._connected:
            status.error = "Not connected"
            return status
        try:
            resp = self._web_client.auth_test()
            status.healthy = resp.get("ok", False)
            if not status.healthy:
                status.error = "Slack auth_test failed"
        except Exception as e:
            status.healthy = False
            status.error = str(e)
        return status

    async def send(self, target: str, message: str, **kwargs) -> bool:
        if not self._connected or not self._web_client:
            return False
        try:
            self._web_client.chat_postMessage(channel=target, text=message[:3000])
            return True
        except Exception as e:
            logger.error(f"[slack] Send failed: {e}")
            return False

    async def receive(self, **kwargs) -> list[dict[str, Any]]:
        if not self._connected or not self._web_client:
            return []
        try:
            channel = kwargs.get("target", kwargs.get("channel", ""))
            if not channel:
                logger.warning("[slack] receive requires target or channel")
                return []
            limit = min(kwargs.get("limit", 10), 100)
            resp = self._web_client.conversations_history(channel=channel, limit=limit)
            if resp.get("ok", False):
                messages = []
                for m in resp.get("messages", []):
                    messages.append({
                        "id": m.get("ts", ""),
                        "channel": channel,
                        "user": m.get("user", ""),
                        "text": m.get("text", ""),
                        "timestamp": m.get("ts", ""),
                        "type": m.get("type", ""),
                    })
                return messages
            logger.warning(f"[slack] Receive failed: {resp.get('error', 'unknown')}")
        except Exception as e:
            logger.error(f"[slack] Receive failed: {e}")
        return []


class WhatsAppIntegration(BaseIntegration):
    name = "whatsapp"

    SUPPORTED_PROVIDERS = {
        "cloud_api": "integrations.whatsapp.WhatsAppCloudAPIProvider",
        "twilio": "integrations.whatsapp.TwilioWhatsAppProvider",
    }

    def __init__(self):
        super().__init__()
        self._provider = None
        self._provider_name: str = "cloud_api"
        self._webhook_handler = None
        self._media_manager = None
        self._history = None
        self._phone_manager = None

    async def connect(self, **kwargs) -> bool:
        self._config.update(kwargs)
        self._save_config()
        provider_key = kwargs.get("provider", self._config.get("provider", "cloud_api"))
        try:
            from integrations.whatsapp.webhook import WhatsAppWebhookHandler
            from integrations.whatsapp.media import MediaManager
            from integrations.whatsapp.history import WhatsAppHistory
            from integrations.whatsapp.phone_manager import WhatsAppPhoneManager

            provider_cls = self._get_provider_class(provider_key)
            if not provider_cls:
                logger.warning("[whatsapp] Unknown provider: %s", provider_key)
                return False
            self._provider = provider_cls()
            ok = await self._provider.connect(**kwargs)
            if ok:
                self._provider_name = provider_key
                self._connected = True
                self._webhook_handler = WhatsAppWebhookHandler()
                self._media_manager = MediaManager()
                self._history = WhatsAppHistory()
                self._phone_manager = WhatsAppPhoneManager()
                business_phone = getattr(self._provider, "_business_phone", "")
                if business_phone:
                    self._phone_manager.register_phone(business_phone, self._provider, make_default=True)
            return ok
        except Exception as e:
            logger.error(f"[whatsapp] Connect failed: {e}")
            return False

    def _get_provider_class(self, provider_key: str):
        import importlib
        path = self.SUPPORTED_PROVIDERS.get(provider_key)
        if not path:
            return None
        module_path, class_name = path.rsplit(".", 1)
        mod = importlib.import_module(module_path)
        return getattr(mod, class_name)

    async def disconnect(self) -> bool:
        if self._provider:
            await self._provider.disconnect()
            self._provider = None
        self._connected = False
        return True

    async def health_check(self) -> IntegrationStatus:
        status = IntegrationStatus(name=self.name, connected=self._connected)
        if not self._connected or not self._provider:
            status.error = "Not connected"
            return status
        try:
            ok = await self._provider.health_check()
            status.healthy = ok
            if not ok:
                status.error = f"{self._provider_name} health check failed"
        except Exception as e:
            status.healthy = False
            status.error = str(e)
        return status

    async def send(self, target: str, message: str, **kwargs) -> bool:
        if not self._connected or not self._provider:
            return False
        try:
            media_url = kwargs.pop("media_url", None)
            media_type = kwargs.pop("media_type", "text")
            caption = kwargs.pop("caption", None)
            filename = kwargs.pop("filename", "file")

            if media_type == "image":
                result = await self._provider.send_image(target, media_url, caption=caption, **kwargs)
            elif media_type == "document":
                result = await self._provider.send_document(target, media_url, filename=filename, caption=caption, **kwargs)
            elif media_type == "audio":
                result = await self._provider.send_audio(target, media_url, **kwargs)
            elif media_type == "location":
                result = await self._provider.send_location(
                    target,
                    latitude=kwargs.pop("latitude", 0),
                    longitude=kwargs.pop("longitude", 0),
                    name=kwargs.pop("location_name", None),
                    address=kwargs.pop("address", None),
                    **kwargs,
                )
            elif media_type == "interactive_buttons":
                body = kwargs.pop("interactive_body", None)
                if body:
                    result = await self._provider.send_interactive_buttons(target, body, **kwargs)
                else:
                    return False
            elif media_type == "interactive_list":
                body = kwargs.pop("interactive_body", None)
                if body:
                    result = await self._provider.send_interactive_list(target, body, **kwargs)
                else:
                    return False
            else:
                result = await self._provider.send_text(target, message, **kwargs)

            if result.success and self._history:
                from integrations.whatsapp.models import MessageDirection, MessageType as WAMessageType, WhatsAppMessage, MessageStatus
                from datetime import datetime
                history_msg = WhatsAppMessage(
                    id=result.message_id or "",
                    type=WAMessageType.TEXT if media_type in ("text", "interactive_buttons", "interactive_list") else WAMessageType(media_type),
                    direction=MessageDirection.OUTBOUND,
                    from_number=getattr(self._provider, "_business_phone", ""),
                    to_number=target,
                    timestamp=datetime.utcnow(),
                    text=message,
                    status=MessageStatus.SENT,
                )
                await self._history.save_message(history_msg)

            return result.success
        except Exception as e:
            logger.error(f"[whatsapp] Send failed: {e}")
            return False

    async def receive(self, **kwargs) -> list[dict[str, Any]]:
        if not self._webhook_handler:
            return []
        try:
            clear = kwargs.get("clear_buffer", True)
            limit = kwargs.get("limit", 20)
            msgs = self._webhook_handler.get_buffered_messages(clear=clear, limit=limit)

            if self._history:
                for m in msgs:
                    await self._history.save_message(m)

            return [{
                "id": m.id,
                "type": m.type.value,
                "from": m.from_number,
                "to": m.to_number,
                "text": m.text,
                "timestamp": m.timestamp.isoformat() if m.timestamp else "",
                "media": {"id": m.media.id, "mime_type": m.media.mime_type, "filename": m.media.filename} if m.media else None,
                "location": {"lat": m.location.latitude, "lon": m.location.longitude} if m.location else None,
                "context_message_id": m.context_message_id,
            } for m in msgs]
        except Exception as e:
            logger.error(f"[whatsapp] Receive failed: {e}")
            return []

    @property
    def history(self):
        return self._history

    @property
    def phone_manager(self):
        return self._phone_manager

    async def get_conversation(self, phone_a: str, phone_b: str, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        if not self._history:
            return []
        msgs = await self._history.get_conversation(phone_a, phone_b, limit=limit, offset=offset)
        return [{
            "id": m.id,
            "type": m.type.value,
            "direction": m.direction.value,
            "from": m.from_number,
            "to": m.to_number,
            "text": m.text,
            "timestamp": m.timestamp.isoformat() if m.timestamp else "",
            "status": m.status.value,
        } for m in msgs]

    async def search_conversations(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        if not self._history:
            return []
        msgs = await self._history.search_messages(query, limit=limit)
        return [{
            "id": m.id,
            "type": m.type.value,
            "direction": m.direction.value,
            "from": m.from_number,
            "to": m.to_number,
            "text": m.text,
            "timestamp": m.timestamp.isoformat() if m.timestamp else "",
        } for m in msgs]

    async def get_recent_conversations(self, limit: int = 20) -> list[dict[str, Any]]:
        if not self._history:
            return []
        return await self._history.get_recent_conversations(limit=limit)

    async def register_phone(self, phone_number: str, token: str, phone_id: str, provider_key: str = "cloud_api", make_default: bool = False) -> bool:
        try:
            provider_cls = self._get_provider_class(provider_key)
            if not provider_cls:
                return False
            provider = provider_cls()
            ok = await provider.connect(token=token, phone_id=phone_id)
            if ok and self._phone_manager:
                self._phone_manager.register_phone(phone_number, provider, make_default=make_default)
                return True
            return False
        except Exception as e:
            logger.error(f"[whatsapp] Register phone failed: {e}")
            return False

    async def unregister_phone(self, phone_number: str) -> bool:
        if not self._phone_manager:
            return False
        return self._phone_manager.unregister_phone(phone_number)

    @property
    def provider(self):
        return self._provider

    @property
    def webhook_handler(self):
        return self._webhook_handler


class GitHubIntegration(BaseIntegration):
    name = "github"

    async def connect(self, **kwargs) -> bool:
        self._config.update(kwargs)
        self._save_config()
        token = self._get_credential("token") or kwargs.get("token")
        if token:
            self._connected = True
            return True
        logger.warning("[github] No token configured")
        return False

    async def disconnect(self) -> bool:
        self._connected = False
        return True

    async def health_check(self) -> IntegrationStatus:
        status = IntegrationStatus(name=self.name, connected=self._connected)
        if not self._connected:
            status.error = "Not connected"
            return status
        try:
            import httpx
            token = self._get_credential("token")
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://api.github.com/user",
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"},
                    timeout=5,
                )
                status.healthy = resp.status_code == 200
                status.latency_ms = resp.elapsed.total_seconds() * 1000
                if not status.healthy:
                    status.error = f"GitHub API error: {resp.status_code}"
        except Exception as e:
            status.healthy = False
            status.error = str(e)
        return status

    async def send(self, target: str, message: str, **kwargs) -> bool:
        if not self._connected:
            return False
        try:
            import httpx
            token = self._get_credential("token")
            repo = kwargs.get("repo", target)
            issue_title = kwargs.get("title", message[:50])
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"https://api.github.com/repos/{repo}/issues",
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"},
                    json={"title": issue_title, "body": message},
                    timeout=10,
                )
                return resp.status_code in (200, 201)
        except Exception as e:
            logger.error(f"[github] Send failed: {e}")
            return False

    async def receive(self, **kwargs) -> list[dict[str, Any]]:
        if not self._connected:
            return []
        try:
            import httpx
            token = self._get_credential("token")
            repo = kwargs.get("repo", "")
            state = kwargs.get("state", "open")
            limit = min(kwargs.get("limit", 20), 100)
            async with httpx.AsyncClient() as client:
                if repo:
                    url = f"https://api.github.com/repos/{repo}/issues"
                    params = {"state": state, "per_page": limit, "sort": "updated", "direction": "desc"}
                else:
                    url = "https://api.github.com/issues"
                    params = {"filter": "all", "state": state, "per_page": limit, "sort": "updated", "direction": "desc"}
                resp = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"},
                    params=params,
                    timeout=10,
                )
                if resp.status_code == 200:
                    items = resp.json()
                    return [{
                        "id": item.get("id"),
                        "number": item.get("number"),
                        "title": item.get("title", ""),
                        "state": item.get("state", ""),
                        "body": item.get("body", ""),
                        "url": item.get("html_url", ""),
                        "user": item.get("user", {}).get("login", ""),
                        "created_at": item.get("created_at", ""),
                        "updated_at": item.get("updated_at", ""),
                        "labels": [l.get("name", "") for l in item.get("labels", [])],
                        "type": "pull_request" if "pull_request" in item else "issue",
                    } for item in items]
                logger.warning(f"[github] Receive failed: {resp.status_code}")
        except Exception as e:
            logger.error(f"[github] Receive failed: {e}")
        return []


class GoogleDriveIntegration(BaseIntegration):
    name = "google_drive"

    async def connect(self, **kwargs) -> bool:
        self._config.update(kwargs)
        self._save_config()
        self._connected = True
        return True

    async def disconnect(self) -> bool:
        self._connected = False
        return True

    async def health_check(self) -> IntegrationStatus:
        status = IntegrationStatus(name=self.name, connected=self._connected)
        if not self._connected:
            status.error = "Not connected"
            return status
        status.healthy = bool(self._get_credential("api_key"))
        if not status.healthy:
            status.error = "No API key configured"
        return status

    async def send(self, target: str, message: str, **kwargs) -> bool:
        logger.info(f"[google_drive] Send not yet implemented: {target}")
        return False

    async def receive(self, **kwargs) -> list[dict[str, Any]]:
        logger.info("[google_drive] Receive not yet implemented")
        return []


_integration_manager: IntegrationManager | None = None


def get_integration_manager() -> IntegrationManager:
    global _integration_manager
    if _integration_manager is None:
        _integration_manager = IntegrationManager()
        _integration_manager.register(GmailIntegration())
        _integration_manager.register(TelegramIntegration())
        _integration_manager.register(DiscordIntegration())
        _integration_manager.register(SlackIntegration())
        _integration_manager.register(WhatsAppIntegration())
        _integration_manager.register(GitHubIntegration())
        _integration_manager.register(GoogleDriveIntegration())
    return _integration_manager


async def health_check_all() -> dict[str, Any]:
    mgr = get_integration_manager()
    results = await mgr.health_check_all()
    return {name: status.to_dict() for name, status in results.items()}
