"""SpecialistModule — base contract for specialist AI modules.

A specialist owns a domain (browser, desktop, coding...) and exposes
named capabilities (``domain.action``). Every capability execution:
1. dispatches to a registered handler;
2. runs the specialist's deterministic ``verify()``;
3. emits an honest outcome event on the global event bus.

Verification is mandatory: ``SpecialistResult.verified`` is False until
the handler's own verification passes — success alone is not trust.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional

from tools.base_tool import (
    CapabilityDefinition,
    CapabilityHealth,
    CapabilityType,
    RiskTier,
    VerificationSpec,
)


async def _finish_coroutine(coroutine):
    """Await to completion (called via asyncio.run from sync code)."""
    return await coroutine


@dataclass
class SpecialistResult:
    """Outcome of one specialist capability execution."""
    success: bool = False
    verified: bool = False
    output: Any = None
    error: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "verified": self.verified,
            "output": self.output,
            "error": self.error,
            "metadata": dict(self.metadata),
        }


class SpecialistModule:
    """Abstract base; subclasses set name/description/requirements and
    implement get_capabilities(), verify() and capability handlers."""

    name: str = "Specialist"
    description: str = ""
    # Environment requirements honestly declared (e.g. ["playwright"]).
    requirements: list = []

    def __init__(self) -> None:
        self._handlers: dict = {}

    @property
    def _event_bus(self):
        # Resolved lazily so tests can monkeypatch the global bus.
        from core.event_bus import global_event_bus
        return global_event_bus

    # ── contract surface ─────────────────────────────────────────────
    def get_capabilities(self) -> list:
        """Return the CapabilityDefinition list owned by this specialist."""
        raise NotImplementedError

    def verify(self, output: Any) -> bool:
        """Deterministic post-condition check on a handler's output."""
        raise NotImplementedError

    def health_check(self) -> dict:
        """Synchronous health report: status in healthy/unhealthy/unknown."""
        return {"status": "unknown", "specialist": self.name}

    def report(self) -> dict:
        """Shape used by tests/UI: identity, capabilities, security."""
        return {
            "specialist": self.name,
            "description": self.description,
            "capabilities": [c.name for c in self.get_capabilities()],
            "security": self.security_policy(),
        }

    @staticmethod
    def security_policy() -> dict:
        return {
            "page_content_untrusted": True,
            "approval_categories": ["payment", "credential_access",
                                    "account_deletion", "file_deletion",
                                    "communication"],
        }

    # ── capability execution ─────────────────────────────────────────
    def execute_capability(self, name: str,
                           params: Optional[dict] = None) -> SpecialistResult:
        """Run one capability by name with verify + event emission."""
        params = dict(params or {})
        handler = self._handlers.get(name)
        if handler is None:
            return SpecialistResult(
                success=False, verified=False,
                error=f"unknown capability '{name}' for {self.name}")

        try:
            output = handler(**params)
            if asyncio.iscoroutine(output):
                output = asyncio.run(_finish_coroutine(output))
        except TypeError:
            try:
                output = handler(params)
                if asyncio.iscoroutine(output):
                    output = asyncio.run(_finish_coroutine(output))
            except Exception as exc:  # noqa: BLE001
                return self._result(name, params, SpecialistResult(
                    success=False, verified=False, error=str(exc)))
        except Exception as exc:  # noqa: BLE001
            return self._result(name, params, SpecialistResult(
                success=False, verified=False, error=str(exc)))

        if isinstance(output, SpecialistResult):
            return self._result(name, params, output)

        success = bool(output.get("success", True)) if isinstance(output, dict) else True
        result = SpecialistResult(
            success=success,
            verified=False,
            output=output,
            error=str(output.get("error", "")) if isinstance(output, dict) else "",
        )
        return self._result(name, params, result)

    async def execute_capability_async(self, name: str,
                                       params: Optional[dict] = None) -> SpecialistResult:
        """Async twin of execute_capability for async handlers/loops."""
        params = dict(params or {})
        handler = self._handlers.get(name)
        if handler is None:
            return SpecialistResult(
                success=False, verified=False,
                error=f"unknown capability '{name}' for {self.name}")
        try:
            output = handler(**params)
            if asyncio.iscoroutine(output):
                output = await output
        except Exception as exc:  # noqa: BLE001
            return self._result(name, params, SpecialistResult(
                success=False, verified=False, error=str(exc)))
        if isinstance(output, SpecialistResult):
            return self._result(name, params, output)
        success = bool(output.get("success", True)) if isinstance(output, dict) else True
        return self._result(name, params, SpecialistResult(
            success=success, verified=False, output=output,
            error=str(output.get("error", "")) if isinstance(output, dict) else ""))

    def _result(self, name: str, params: dict,
                result: SpecialistResult) -> SpecialistResult:
        """Attach verification + emit the outcome event."""
        if result.success and not result.verified:
            try:
                result.verified = bool(self.verify(result.output))
            except Exception:  # noqa: BLE001 — verification must never crash
                result.verified = False
        if not result.success:
            result.verified = False
        self._emit_outcome_event(name, params, result)
        return result

    # ── events ───────────────────────────────────────────────────────
    def _emit_outcome_event(self, capability: str, params: dict,
                            result: SpecialistResult) -> None:
        """Emit action.verified — or goal.completed for goal-level caps."""
        output = result.output if isinstance(result.output, dict) else {}
        is_goal_level = "goal" in output and capability.endswith("workflow")
        if is_goal_level:
            event_type = "goal.completed"
            payload = {
                "specialist": self.name,
                "capability": capability,
                "goal": output.get("goal", ""),
                "verified": result.verified,
                "success": result.success,
                "status": output.get("status", ""),
            }
        else:
            event_type = "action.verified"
            payload = {
                "specialist": self.name,
                "capability": capability,
                "verified": result.verified,
                "success": result.success,
                "error": result.error,
            }
        # legacy (type, payload) API: handlers receive the payload dict.
        try:
            self._event_bus.publish_sync(event_type, payload)
        except Exception:  # noqa: BLE001 — event emission must never crash
            pass

    # ── registration helpers ─────────────────────────────────────────
    def _register(self, name: str, handler) -> None:
        self._handlers[name] = handler

    def capabilities_as_definitions(self, owner_module: str = "") -> list:
        """Build CapabilityDefinition records from get_capabilities()."""
        from tools.base_tool import CapabilityDefinition
        owner = owner_module or self.name
        definitions = []
        for cap in self.get_capabilities():
            if isinstance(cap, CapabilityDefinition):
                definitions.append(cap)
                continue
            definitions.append(CapabilityDefinition(
                name=cap.name if hasattr(cap, "name") else str(cap),
                owner_module=owner,
                description=getattr(cap, "description", ""),
            ))
        return definitions


__all__ = ["SpecialistModule", "SpecialistResult"]
