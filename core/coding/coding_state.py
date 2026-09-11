"""Shared state and result contracts for the Coding AI specialist."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class CodingStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class CodingCapabilityContract:
    name: str = "Coding AI"
    can: list[str] = field(default_factory=lambda: [
        "understand repositories",
        "analyze architecture",
        "inspect source code",
        "trace dependencies",
        "plan code changes",
        "implement changes through provided tools",
        "refactor",
        "debug",
        "run tests",
        "analyze build failures",
        "inspect Git changes",
        "prepare commits",
        "work with GitHub through provided tools",
        "verify implementation",
        "explain technical decisions",
    ])
    cannot: list[str] = field(default_factory=lambda: [
        "control the whole JARVIS system",
        "decide unrelated user goals",
        "replace Desktop AI",
        "replace Research AI",
        "replace the future Super-Brain",
    ])

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CodingConstraints:
    max_attempts: int = 2
    time_budget_seconds: int | None = None
    allow_high_risk: bool = False
    commands: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CodingAction:
    kind: str
    description: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CodingResult:
    status: CodingStatus
    objective: str
    plan: dict[str, Any]
    actions: list[CodingAction] = field(default_factory=list)
    files_changed: list[str] = field(default_factory=list)
    tests: list[dict[str, Any]] = field(default_factory=list)
    verification: dict[str, Any] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    remaining_risks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "objective": self.objective,
            "plan": self.plan,
            "actions": [action.to_dict() for action in self.actions],
            "files_changed": self.files_changed,
            "tests": self.tests,
            "verification": self.verification,
            "failures": self.failures,
            "evidence": self.evidence,
            "remaining_risks": self.remaining_risks,
        }
