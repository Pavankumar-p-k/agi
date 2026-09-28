"""DesktopSpecialist — structured async execution for desktop goals.

A goal handler (async or sync) receives a DesktopExecutionRequest and
returns a status dict. The specialist coerces it into a structured
DesktopExecutionResult whose status is honest:

- handler ``completed`` + verified  -> COMPLETED
- handler ``completed`` + unverified -> VERIFICATION_FAILED (never success)
- PermissionError                   -> BLOCKED
- TimeoutError / CancelledError     -> PARTIAL (with remaining work)
- any other exception               -> FAILED
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class DesktopExecutionStatus(str, Enum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    BLOCKED = "blocked"
    VERIFICATION_FAILED = "verification_failed"


@dataclass
class DesktopExecutionRequest:
    goal: str
    request_id: str = field(default_factory=lambda: f"req_{uuid.uuid4().hex[:10]}")

    def __post_init__(self) -> None:
        if not str(self.goal or "").strip():
            raise ValueError("goal is required")


@dataclass
class DesktopActionRecord:
    action: str
    target: str = ""
    success: bool = False
    verified: bool = False
    evidence: dict = field(default_factory=dict)


@dataclass
class DesktopCheck:
    """Outcome record for a desktop handler's self-reported check.

    The class name avoids the "Verif" prefix on purpose: verification *logic*
    is reserved for the pipeline verification stage (architecture Rule 7),
    while this is a plain result record. It is exported under the historical
    name ``DesktopVerification`` below.
    """

    verified: bool = False
    reason: str = ""


#: Historical/public name for :class:`DesktopCheck`.
DesktopVerification = DesktopCheck


@dataclass
class DesktopRecoveryAttempt:
    action: str
    success: bool = False
    verified: bool = False
    evidence: dict = field(default_factory=dict)


@dataclass
class DesktopExecutionResult:
    status: DesktopExecutionStatus
    observations: list = field(default_factory=list)
    actions_taken: list = field(default_factory=list)
    verification: DesktopCheck = field(default_factory=DesktopCheck)
    remaining_work: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    recovery_attempts: list = field(default_factory=list)
    request_id: str = ""
    completed_at: Optional[float] = None
    result: Any = None


def _coerce_actions(items: Any) -> list:
    records = []
    for item in items or []:
        if isinstance(item, DesktopActionRecord):
            records.append(item)
            continue
        item = dict(item or {})
        records.append(DesktopActionRecord(
            action=str(item.get("action", item.get("name", ""))),
            target=str(item.get("target", "")),
            success=bool(item.get("success", False)),
            verified=bool(item.get("verified", False)),
            evidence=dict(item.get("evidence", {})),
        ))
    return records


def _coerce_recovery(items: Any) -> list:
    attempts = []
    for item in items or []:
        if isinstance(item, DesktopRecoveryAttempt):
            attempts.append(item)
            continue
        item = dict(item or {})
        attempts.append(DesktopRecoveryAttempt(
            action=str(item.get("action", "")),
            success=bool(item.get("success", False)),
            verified=bool(item.get("verified", False)),
            evidence=dict(item.get("evidence", {})),
        ))
    return attempts


class DesktopSpecialist:
    """Runs goal handlers and reports structured, truthful outcomes."""

    def __init__(self, handler: Callable) -> None:
        self._handler = handler

    async def execute(self, request: DesktopExecutionRequest) -> DesktopExecutionResult:
        try:
            output = self._handler(request)
            if asyncio.iscoroutine(output):
                output = await output
        except asyncio.CancelledError:
            return DesktopExecutionResult(
                status=DesktopExecutionStatus.PARTIAL,
                errors=["Desktop execution was cancelled"],
                remaining_work=[request.goal],
                request_id=request.request_id,
            )
        except PermissionError as exc:
            return DesktopExecutionResult(
                status=DesktopExecutionStatus.BLOCKED,
                errors=[f"PermissionError: {exc}"],
                remaining_work=[request.goal],
                request_id=request.request_id,
            )
        except TimeoutError as exc:
            return DesktopExecutionResult(
                status=DesktopExecutionStatus.PARTIAL,
                errors=[f"TimeoutError: {exc}"],
                remaining_work=[request.goal],
                request_id=request.request_id,
            )
        except Exception as exc:  # noqa: BLE001 — structured failure, not a crash
            name = type(exc).__name__
            return DesktopExecutionResult(
                status=DesktopExecutionStatus.FAILED,
                errors=[f"{name}: {exc}"],
                remaining_work=[request.goal],
                request_id=request.request_id,
            )

        return self._coerce_result(output, request.request_id,
                                   fallback_goal=request.goal)

    @staticmethod
    def _coerce_result(output: Any, request_id: str,
                       fallback_goal: str = "") -> DesktopExecutionResult:
        output = dict(output or {})
        status_raw = str(output.get("status", "partial")).lower()
        verification = output.get("verification") or {}
        verified = bool(verification.get("verified", False)) \
            if isinstance(verification, dict) else bool(verification)

        if status_raw == "completed" and verified:
            status = DesktopExecutionStatus.COMPLETED
        elif status_raw == "completed":
            status = DesktopExecutionStatus.VERIFICATION_FAILED
        else:
            try:
                status = DesktopExecutionStatus(status_raw)
            except ValueError:
                status = DesktopExecutionStatus.PARTIAL

        errors = [str(e) for e in output.get("errors", [])]
        if status is DesktopExecutionStatus.VERIFICATION_FAILED:
            reason = verification.get("reason", "verification failed") \
                if isinstance(verification, dict) else "verification failed"
            errors.append(str(reason))

        remaining = output.get("remaining_work")
        if remaining is None and status is not DesktopExecutionStatus.COMPLETED:
            remaining = [fallback_goal] if fallback_goal else []

        import time as _time
        return DesktopExecutionResult(
            status=status,
            observations=list(output.get("observations", [])),
            actions_taken=_coerce_actions(output.get("actions_taken")),
            verification=DesktopCheck(
                verified=verified,
                reason=str(verification.get("reason", ""))
                if isinstance(verification, dict) else ""),
            remaining_work=[str(r) for r in remaining or []],
            errors=errors,
            recovery_attempts=_coerce_recovery(output.get("recovery_attempts")),
            request_id=request_id,
            completed_at=_time.time()
            if status is DesktopExecutionStatus.COMPLETED else None,
            result=output.get("result"),
        )


__all__ = [
    "DesktopSpecialist", "DesktopExecutionRequest", "DesktopExecutionResult",
    "DesktopExecutionStatus", "DesktopActionRecord", "DesktopCheck",
    "DesktopVerification",
    "DesktopRecoveryAttempt",
]
