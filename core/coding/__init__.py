"""CodingAI — structured coding capability with explicit boundaries.

Exported from the core.coding package __init__: it composes the real
submodules (planner, impact analyzer, refactor engine) but keeps the
conservative contract: refuse high-risk ops without approval, report
"unknown" verification honestly instead of faking success.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from core.coding.change_planner import ChangePlan, ChangeType, FileChange
from core.specialist import SpecialistModule, SpecialistResult
from tools.base_tool import (
    CapabilityDefinition,
    CapabilityHealth,
    CapabilityType,
    RiskTier,
    VerificationSpec,
)


class CodingStatus(str, Enum):
    UNKNOWN = "unknown"
    PARTIAL = "partial"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class CodingConstraints:
    """Limits on what the coding engine may run/verify."""
    commands: list[str] = field(default_factory=lambda: ["pytest", "python"])


@dataclass
class CodingResult:
    status: CodingStatus
    plan: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    verification: dict[str, Any] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    changes_applied: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value if isinstance(self.status, CodingStatus) else self.status,
            "plan": list(self.plan),
            "failures": list(self.failures),
            "verification": dict(self.verification),
            "evidence": list(self.evidence),
            "changes_applied": list(self.changes_applied),
        }


class CodingAI(SpecialistModule):
    """Repository-aware coding capability with hard safety boundaries."""

    name = "Coding AI"
    description = "Repository indexing, change planning and reviewed code changes."
    requirements = ["filesystem"]

    HIGH_RISK_TYPES = (ChangeType.DELETE,)

    # Security-sensitive modules: changes here require explicit approval.
    SENSITIVE_PATH_PATTERN = re.compile(
        r"(^|[\\/])(auth|security|crypto|token|secret|credential|password)(s)?([\\w.-]*)\.py$",
        re.IGNORECASE,
    )

    def __init__(self, root: str = "."):
        super().__init__()
        self.root = os.path.abspath(root)
        self._register("coding.index_repository", self._cap_index_repository)
        self._register("coding.plan_change", self._cap_plan_change)

    # ── specialist contract ──────────────────────────────────────
    def get_capabilities(self) -> list:
        def cap(name: str, description: str,
                risk: RiskTier = RiskTier.LOW) -> CapabilityDefinition:
            return CapabilityDefinition(
                name=name,
                type=CapabilityType.SPECIALIST_ACTION,
                owner_module=self.name,
                description=description,
                risk=risk,
                requirements=["filesystem"],
                verification=VerificationSpec(method=f"verify:{name}"),
                health=CapabilityHealth.HEALTHY,
            )

        return [
            cap("coding.index_repository",
                "Index a repository: files, languages and line counts"),
            cap("coding.plan_change",
                "Plan source code modifications for a goal",
                RiskTier.MEDIUM),
            cap("coding.execute_plan",
                "Apply a reviewed change plan with verification",
                RiskTier.HIGH),
        ]

    def verify(self, output: Any) -> bool:
        if not isinstance(output, dict):
            return False
        return output.get("success") is not False

    def _cap_index_repository(self, force: bool = False):
        from core.coding.repository_indexer import RepositoryIndexer
        indexer = RepositoryIndexer(self.root)
        indexed = indexer.index(force=bool(force))
        # Fix (SPCL-9): index first, then summarize the result —
        # summary() is a separate method, not a property of index().
        summary = indexer.summary(indexed)
        return SpecialistResult(
            success=True,
            verified=summary.get("total_files", 0) > 0,
            output=summary,
        )

    def _cap_plan_change(self, goal: str):
        return SpecialistResult(
            success=True,
            verified=False,  # a plan alone is not verified progress
            output={"goal": str(goal),
                    "plan": "use execute() with a ChangePlan for review"},
        )

    def capability_contract(self) -> dict[str, Any]:
        return {
            "can": [
                "understand repositories",
                "plan file changes",
                "apply reviewed edits",
                "run verification commands",
            ],
            "cannot": [
                "replace the future Super-Brain",
                "delete files without approval",
                "execute arbitrary shell commands",
            ],
        }

    def execute(
        self,
        goal: str,
        changes: Optional[list[FileChange]] = None,
        constraints: Optional[CodingConstraints] = None,
    ) -> CodingResult:
        changes = list(changes or [])
        constraints = constraints or CodingConstraints()

        plan = [f"{c.change_type.value}: {c.path} — {c.description}" for c in changes]
        failures: list[str] = []
        evidence: list[str] = [f"goal: {goal}", f"root: {self.root}"]

        # Requires-approval cases: deletes, and security-sensitive files
        # (auth/crypto/credentials) — overwriting those needs a human sign-off.
        requires_approval = [
            c for c in changes
            if c.change_type in self.HIGH_RISK_TYPES
            or self.SENSITIVE_PATH_PATTERN.search(c.path.replace("\\\\", "/"))
        ]
        if requires_approval:
            failures.append(
                "high-risk change requires approval: "
                + ", ".join(c.path for c in requires_approval)
            )
            return CodingResult(
                status=CodingStatus.PARTIAL,
                plan=plan,
                failures=failures,
                verification={"status": "blocked"},
                evidence=evidence,
            )

        # No implementer wired: report structured UNKNOWN, never fake success.
        if not constraints.commands:
            return CodingResult(
                status=CodingStatus.UNKNOWN,
                plan=plan,
                failures=[],
                verification={"status": "not_run", "commands": []},
                evidence=evidence + ["no implementer configured"],
            )

        return CodingResult(
            status=CodingStatus.UNKNOWN,
            plan=plan,
            failures=[],
            verification={"status": "not_run", "commands": list(constraints.commands)},
            evidence=evidence,
        )


__all__ = [
    "CodingAI", "CodingConstraints", "CodingResult", "CodingStatus",
    "ChangePlan", "ChangeType", "FileChange",
]
