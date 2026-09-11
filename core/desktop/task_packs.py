"""Repeatable, safety-aware validation contracts for native desktop adapters."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable
import time


@dataclass(frozen=True)
class TaskPackStep:
    name: str
    action: str
    destructive: bool = False
    expected_evidence: tuple[str, ...] = ()


@dataclass
class TaskPackResult:
    pack_id: str
    application: str
    status: str
    completed_steps: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""
    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TaskPack:
    pack_id: str
    application: str
    steps: tuple[TaskPackStep, ...]

    def validate(self) -> None:
        if not self.pack_id or not self.application or not self.steps:
            raise ValueError("task pack requires an id, application, and steps")
        names = [step.name for step in self.steps]
        if len(names) != len(set(names)):
            raise ValueError("task pack step names must be unique")


class TaskPackRunner:
    """Runs injected functions; it never invents actions or bypasses policy."""

    def __init__(
        self,
        action: Callable[[TaskPackStep], dict[str, Any]],
        verify: Callable[[TaskPackStep, dict[str, Any]], bool],
    ):
        self.action = action
        self.verify = verify

    def run(self, pack: TaskPack, *, allow_destructive: bool = False) -> TaskPackResult:
        pack.validate()
        result = TaskPackResult(pack.pack_id, pack.application, "running")
        for step in pack.steps:
            if step.destructive and not allow_destructive:
                result.status = "blocked"
                result.error = f"destructive step blocked: {step.name}"
                result.completed_at = time.time()
                return result
            try:
                evidence = self.action(step)
                if not isinstance(evidence, dict) or not self.verify(step, evidence):
                    result.status = "failed"
                    result.error = f"verification failed: {step.name}"
                    result.evidence.append(evidence if isinstance(evidence, dict) else {"value": evidence})
                    result.completed_at = time.time()
                    return result
                result.completed_steps.append(step.name)
                result.evidence.append(evidence)
            except Exception as exc:
                result.status = "failed"
                result.error = f"{step.name}: {exc}"
                result.completed_at = time.time()
                return result
        result.status = "completed"
        result.completed_at = time.time()
        return result
