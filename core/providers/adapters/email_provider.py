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


class EmailProvider(ExecutionProvider):
    provider_id = "email"
    name = "Email Provider"
    version = "1.0.0"
    priority = 10
    installed = True

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            capability_names=[
                "email",
                "send_email",
                "compose_email",
                "email_attachments",
            ],
            features=[
                "send",
                "compose",
                "attachments",
                "html_body",
            ],
        )

    async def health(self) -> ProviderHealth:
        try:
            from mcp.email_server import email_server
            if email_server is not None:
                return ProviderHealth(
                    status=ProviderHealthStatus.HEALTHY,
                    latency_ms=0.0,
                    last_checked=time.time(),
                )
            return ProviderHealth(
                status=ProviderHealthStatus.DEGRADED,
                error="Email server not configured",
                last_checked=time.time(),
            )
        except ImportError:
            return ProviderHealth(
                status=ProviderHealthStatus.DOWN,
                error="mcp.email_server not available",
                last_checked=time.time(),
            )
        except Exception as e:
            return ProviderHealth(
                status=ProviderHealthStatus.DOWN,
                error=str(e),
                last_checked=time.time(),
            )

    async def execute(self, task: dict[str, Any], context: dict[str, Any] | None = None) -> ExecutionResult:
        start = time.monotonic()
        action = task.get("action", task.get("capability", "send"))
        to = task.get("to", task.get("target", ""))
        subject = task.get("subject", "")
        body = task.get("body", task.get("message", task.get("content", "")))
        attachments = task.get("attachments", [])

        try:
            if action in ("send", "send_email"):
                return await self._send(to, subject, body, attachments, start)
            elif action == "compose":
                return await self._compose(to, subject, body, start)
            else:
                elapsed = (time.monotonic() - start) * 1000
                return ExecutionResult(
                    success=False, output="",
                    error=f"Unknown email action: {action}",
                    exit_code=1, duration_ms=elapsed,
                    metadata={"provider": "email"},
                )
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            logger.exception("[EmailProvider] Execution failed: %s", e)
            return ExecutionResult(
                success=False, output="", error=str(e), exit_code=1,
                duration_ms=elapsed, metadata={"provider": "email"},
            )

    async def _send(self, to: str, subject: str, body: str, attachments: list[str], start: float) -> ExecutionResult:
        recipients = [r.strip() for r in to.split(",") if r.strip()] if to else []
        if not recipients:
            elapsed = (time.monotonic() - start) * 1000
            return ExecutionResult(
                success=False, output="",
                error="No recipients specified", exit_code=1,
                duration_ms=elapsed, metadata={"provider": "email"},
            )

        try:
            from mcp.email_server import _send_email
        except (ImportError, Exception) as e:
            elapsed = (time.monotonic() - start) * 1000
            return ExecutionResult(
                success=False, output="",
                error=f"Email server unavailable: {e}", exit_code=1,
                duration_ms=elapsed,
                metadata={"provider": "email", "action": "send"},
            )

        result = await _send_email(
            to=recipients,
            subject=subject or "(No Subject)",
            body=body or "",
            attachments=attachments or [],
        )
        elapsed = (time.monotonic() - start) * 1000
        result_str = result if isinstance(result, str) else str(result)
        success = any(kw in result_str.lower() for kw in ("sent", "queued", "ok"))
        return ExecutionResult(
            success=success,
            output=result_str[:5000],
            error="" if success else result_str,
            exit_code=0 if success else 1,
            duration_ms=elapsed,
            metadata={
                "provider": "email",
                "action": "send",
                "to": recipients,
                "subject": subject,
            },
        )

    async def _compose(self, to: str, subject: str, body: str, start: float) -> ExecutionResult:
        elapsed = (time.monotonic() - start) * 1000
        return ExecutionResult(
            success=True,
            output=f"To: {to}\nSubject: {subject}\nBody:\n{body}",
            exit_code=0,
            duration_ms=elapsed,
            metadata={"provider": "email", "action": "compose"},
        )

    async def handle_tool(
        self, tool_type: str, content: str, **kwargs: Any,
    ) -> ExecutionResult | None:
        email_tools = {"email_send", "send_email", "email_send_email"}
        if tool_type not in email_tools:
            return None
        return await self.execute({
            "action": "send",
            "to": kwargs.get("to", ""),
            "subject": kwargs.get("subject", ""),
            "body": kwargs.get("body", content),
            "attachments": kwargs.get("attachments", []),
        })

    async def estimate_cost(self, task: dict[str, Any]) -> float:
        return 0.0

    async def estimate_latency(self, task: dict[str, Any]) -> float:
        return 100.0
