"""EmailProvider: email actions as a capability provider.

Completed from the committed contract in tests/unit/test_email_provider.py.
Compose is local formatting; send validates recipients and delegates to the
existing email transport when one is configured (honest failure otherwise).
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from core.providers.base import (
    ExecutionProvider,
    ExecutionResult,
    ProviderCapabilities,
    ProviderHealth,
    ProviderHealthStatus,
)

logger = logging.getLogger(__name__)


class EmailProvider(ExecutionProvider):
    provider_id = "email"
    name = "Email"
    version = "1.0.0"
    priority = 80
    installed = True
    _enabled = True

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(capability_names=["email", "send_email", "compose_email"])

    async def health(self) -> ProviderHealth:
        return self._cache_health(ProviderHealth(status=ProviderHealthStatus.HEALTHY))

    async def execute(
        self, task: dict[str, Any], context: Optional[dict[str, Any]] = None
    ) -> ExecutionResult:
        action = str(task.get("action", "") or "")
        if action == "compose":
            to = str(task.get("to", "") or "")
            subject = str(task.get("subject", "") or "")
            body = str(task.get("body", "") or "")
            output = f"To: {to}\nSubject: {subject}\n\n{body}"
            return ExecutionResult(success=True, output=output)
        if action == "send":
            to = task.get("to", "") or task.get("recipients", "")
            recipients = [to] if isinstance(to, str) and to else list(to or [])
            if not recipients:
                return ExecutionResult(
                    success=False,
                    error="no recipients specified",
                )
            return await self._send(task, recipients)
        return ExecutionResult(success=False, error=f"Unknown email action: {action}")

    async def _send(
        self, task: dict[str, Any], recipients: list[str]
    ) -> ExecutionResult:
        subject = str(task.get("subject", "") or "")
        body = str(task.get("body", "") or "")
        try:
            from notifications.notifier import notifier  # existing transport
            send = getattr(notifier, "send_email", None)
            if send is None:
                return ExecutionResult(success=False, error="no email transport configured")
            result = send(to=recipients, subject=subject, body=body)
            if hasattr(result, "__await__"):
                result = await result
            return ExecutionResult(success=bool(result), output="email sent")
        except Exception as exc:
            return ExecutionResult(success=False, error=f"email send failed: {exc}")

    async def handle_tool(self, tool_name: str, content: str, **kwargs: Any) -> Optional[Any]:
        """Adapter boundary hook: route email tools to this provider."""
        if tool_name not in ("email_send", "send_email", "email_compose", "compose_email"):
            return None
        task = {"action": "send" if "send" in tool_name else "compose", "body": content}
        task.update(kwargs)
        return await self.execute(task)

    async def estimate_cost(self, task: dict[str, Any]) -> float:
        return 0.0

    async def estimate_latency(self, task: dict[str, Any]) -> float:
        return 100.0
