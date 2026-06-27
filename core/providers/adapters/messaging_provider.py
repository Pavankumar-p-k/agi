from __future__ import annotations

import logging
import time
from typing import Any

from core.providers.base import (
    ExecutionProvider,
    ExecutionResult,
    ProviderCapabilities,
    ProviderHealth,
    ProviderHealthStatus,
)

logger = logging.getLogger(__name__)


class MessagingProvider(ExecutionProvider):
    provider_id = "messaging"
    name = "Messaging & Notifications"
    version = "1.0.0"
    priority = 10
    installed = True

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            capability_names=[
                "messaging",
                "notification",
                "email",
                "send_notification",
                "send_email",
                "send_message",
                "broadcast",
            ],
            features=[
                "email",
                "telegram",
                "slack",
                "discord",
                "notification",
            ],
        )

    async def health(self) -> ProviderHealth:
        try:
            from mcp.email_server import email_server
            ok = email_server is not None
        except Exception:
            ok = False
        try:
            from channels.controller import channel_controller
            has_channels = len(channel_controller.channels) > 0
        except Exception:
            has_channels = False

        if ok or has_channels:
            return ProviderHealth(
                status=ProviderHealthStatus.HEALTHY,
                latency_ms=0.0,
                last_checked=time.time(),
            )
        return ProviderHealth(
            status=ProviderHealthStatus.DEGRADED,
            error="No messaging channels configured",
            last_checked=time.time(),
        )

    async def execute(
        self, task: dict[str, Any], context: dict[str, Any] | None = None
    ) -> ExecutionResult:
        start = time.monotonic()
        goal = task.get("goal", "")
        action = task.get("action", task.get("capability", ""))
        channel = task.get("channel", "email")
        target = task.get("target", task.get("to", ""))
        subject = task.get("subject", "")
        body = task.get("body", task.get("message", task.get("content", "")))
        attachments = task.get("attachments", [])

        try:
            if "email" in action or channel == "email":
                return await self._send_email(target, subject, body, attachments, start)
            return await self._send_channel_message(channel, target, body, start)
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            logger.exception("[MessagingProvider] Execution failed: %s", e)
            return ExecutionResult(
                success=False,
                output="",
                error=str(e),
                exit_code=1,
                duration_ms=elapsed,
                metadata={"provider": "messaging"},
            )

    async def _send_email(
        self, to: str, subject: str, body: str, attachments: list[str], start: float
    ) -> ExecutionResult:
        from mcp.email_server import _send_email

        result = await _send_email(
            to=[to] if isinstance(to, str) else to,
            subject=subject,
            body=body,
            attachments=attachments,
        )
        elapsed = (time.monotonic() - start) * 1000
        success = "sent" in result.lower() or "queued" in result.lower()
        return ExecutionResult(
            success=success,
            output=result[:5000] if isinstance(result, str) else str(result),
            exit_code=0 if success else 1,
            duration_ms=elapsed,
            metadata={
                "provider": "messaging",
                "channel": "email",
                "to": to,
                "subject": subject,
            },
        )

    async def _send_channel_message(
        self, channel: str, target: str, message: str, start: float
    ) -> ExecutionResult:
        from channels.controller import channel_controller

        ch = channel_controller.get(channel)
        if not ch:
            elapsed = (time.monotonic() - start) * 1000
            return ExecutionResult(
                success=False,
                output="",
                error=f"Unknown channel: {channel}",
                exit_code=1,
                duration_ms=elapsed,
                metadata={"provider": "messaging", "channel": channel},
            )
        if not ch.is_running:
            elapsed = (time.monotonic() - start) * 1000
            return ExecutionResult(
                success=False,
                output="",
                error=f"Channel {channel} is not running",
                exit_code=1,
                duration_ms=elapsed,
                metadata={"provider": "messaging", "channel": channel},
            )

        ok = await ch.send(target, message)
        elapsed = (time.monotonic() - start) * 1000
        return ExecutionResult(
            success=bool(ok),
            output=f"Message sent via {channel}" if ok else f"Failed to send via {channel}",
            exit_code=0 if ok else 1,
            duration_ms=elapsed,
            metadata={
                "provider": "messaging",
                "channel": channel,
                "target": target,
            },
        )

    async def estimate_cost(self, task: dict[str, Any]) -> float:
        return 0.0

    async def estimate_latency(self, task: dict[str, Any]) -> float:
        return 50.0
