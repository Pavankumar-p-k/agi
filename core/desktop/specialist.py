"""Stable delegation boundary for the native desktop specialist.

The specialist contract deliberately contains desktop-local information only.
Global orchestration, cross-specialist planning, and user-wide memory remain
outside this module.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Mapping
import asyncio
import inspect
import time
import uuid

if TYPE_CHECKING:
    from .specialist_state import DesktopLocalState


class DesktopExecutionStatus(str, Enum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    BLOCKED = "blocked"
    VERIFICATION_FAILED = "verification_failed"


@dataclass(frozen=True)
class DesktopExecutionRequest:
    goal: str
    context: Mapping[str, Any] = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def __post_init__(self) -> None:
        if not self.goal.strip():
            raise ValueError("goal is required")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DesktopActionRecord:
    action: str
    target: str = ""
    method: str = ""
    success: bool = False
    verified: bool = False
    evidence: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass(frozen=True)
class DesktopRecoveryAttempt:
    action: str
    success: bool
    verified: bool = False
    evidence: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass(frozen=True)
class DesktopVerification:
    verified: bool
    checks: tuple[dict[str, Any], ...] = ()
    reason: str = ""


@dataclass
class DesktopExecutionResult:
    status: DesktopExecutionStatus
    result: Any = None
    observations: list[dict[str, Any]] = field(default_factory=list)
    actions_taken: list[DesktopActionRecord] = field(default_factory=list)
    recovery_attempts: list[DesktopRecoveryAttempt] = field(default_factory=list)
    verification: DesktopVerification = field(
        default_factory=lambda: DesktopVerification(False)
    )
    errors: list[str] = field(default_factory=list)
    remaining_work: list[str] = field(default_factory=list)
    request_id: str = ""
    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


DesktopHandler = Callable[
    [DesktopExecutionRequest],
    DesktopExecutionResult | Mapping[str, Any] | Awaitable[
        DesktopExecutionResult | Mapping[str, Any]
    ],
]


class DesktopSpecialist:
    """Executes delegated desktop goals through an injected runtime handler."""

    def __init__(
        self,
        handler: DesktopHandler,
        state: "DesktopLocalState | None" = None,
    ):
        from .specialist_state import DesktopLocalState

        self._handler = handler
        self.state = state or DesktopLocalState()

    async def execute(
        self, request: DesktopExecutionRequest
    ) -> DesktopExecutionResult:
        self.state.begin_task(request.request_id, request.goal)
        try:
            raw = self._handler(request)
            if inspect.isawaitable(raw):
                raw = await raw
            result = self._coerce_result(raw, request.request_id)
        except asyncio.CancelledError:
            result = DesktopExecutionResult(
                status=DesktopExecutionStatus.PARTIAL,
                errors=["Desktop execution was cancelled"],
                remaining_work=[request.goal],
                request_id=request.request_id,
            )
        except (PermissionError, TimeoutError, InterruptedError) as error:
            result = DesktopExecutionResult(
                status=(
                    DesktopExecutionStatus.BLOCKED
                    if isinstance(error, PermissionError)
                    else DesktopExecutionStatus.PARTIAL
                ),
                errors=[f"{type(error).__name__}: {error}"],
                remaining_work=[request.goal],
                request_id=request.request_id,
            )
        except Exception as error:
            # The specialist boundary must turn an implementation failure into
            # truthful structured output instead of leaking a false success.
            result = DesktopExecutionResult(
                status=DesktopExecutionStatus.FAILED,
                errors=[f"{type(error).__name__}: {error}"],
                remaining_work=[request.goal],
                request_id=request.request_id,
            )
        result.request_id = result.request_id or request.request_id
        self._normalize_result(result, request.goal)
        result.completed_at = result.completed_at or time.time()
        self.state.record_result(result)
        return result

    @staticmethod
    def _coerce_result(
        raw: DesktopExecutionResult | Mapping[str, Any],
        request_id: str,
    ) -> DesktopExecutionResult:
        if isinstance(raw, DesktopExecutionResult):
            if not raw.request_id:
                raw.request_id = request_id
            return raw
        if not isinstance(raw, Mapping):
            raise TypeError("desktop handler must return a DesktopExecutionResult or mapping")

        status = raw.get("status", DesktopExecutionStatus.FAILED)
        if not isinstance(status, DesktopExecutionStatus):
            status = DesktopExecutionStatus(str(status))
        verification = raw.get("verification", {})
        if isinstance(verification, DesktopVerification):
            verification_value = verification
        else:
            verification_value = DesktopVerification(
                verified=bool(verification.get("verified", False)),
                checks=tuple(verification.get("checks", ())),
                reason=str(verification.get("reason", "")),
            )
        actions = [
            action if isinstance(action, DesktopActionRecord)
            else DesktopActionRecord(**dict(action))
            for action in raw.get("actions_taken", [])
        ]
        recovery_attempts = [
            attempt if isinstance(attempt, DesktopRecoveryAttempt)
            else DesktopRecoveryAttempt(**dict(attempt))
            for attempt in raw.get("recovery_attempts", [])
        ]
        return DesktopExecutionResult(
            status=status,
            result=raw.get("result"),
            observations=list(raw.get("observations", [])),
            actions_taken=actions,
            recovery_attempts=recovery_attempts,
            verification=verification_value,
            errors=[str(error) for error in raw.get("errors", [])],
            remaining_work=[str(item) for item in raw.get("remaining_work", [])],
            request_id=str(raw.get("request_id", request_id)),
            started_at=float(raw.get("started_at", time.time())),
            completed_at=raw.get("completed_at"),
        )

    @staticmethod
    def _normalize_result(result: DesktopExecutionResult, goal: str) -> None:
        """Enforce the contract's no-false-success invariant."""
        if result.status is DesktopExecutionStatus.COMPLETED and not result.verification.verified:
            result.status = DesktopExecutionStatus.VERIFICATION_FAILED
            result.errors.append(
                result.verification.reason
                or "Desktop execution completed without verified postcondition"
            )
            if goal not in result.remaining_work:
                result.remaining_work.append(goal)
