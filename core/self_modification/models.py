"""Self-Modification Engine (Phase 18.0) — data models.

Covers:
  - ModificationRecipe: predefined transformation types
  - ModificationTarget: what to modify (system, file, function)
  - ModificationPlan: planner output (recipe + target + params)
  - ModificationStatus: lifecycle states
  - ModificationRecord: persisted outcome
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ModificationRecipe(str, Enum):
    """Predefined modification recipes — the only allowed transformations.

    Each recipe is a safe, deterministic, testable transformation.
    No arbitrary code generation.
    """

    ADD_RETRY_LOOP = "add_retry_loop"
    """Wrap a tool function body in a retry loop (max 3 attempts)."""

    ADD_VERIFICATION_STEP = "add_verification_step"
    """Add a post-execution verification call after the primary operation."""

    INCREASE_TIMEOUT = "increase_timeout"
    """Increase timeout constants/parameters in a module."""

    ENABLE_FAILURE_MEMORY = "enable_failure_memory"
    """Wire PatternFailureMemory recording into a tool handler."""

    ADD_CALIBRATION_HOOK = "add_calibration_hook"
    """Add prediction accuracy tracking hook to a tool/strategy."""

    PROMOTE_PROPERTY = "promote_property"
    """Set a structural property to True in the registry (no code change)."""


class ModificationStatus(str, Enum):
    """Lifecycle state of a modification attempt."""

    PLANNED = "planned"
    """Recipe selected, target identified, not yet executed."""

    IN_PROGRESS = "in_progress"
    """Snapshot taken, patches being applied."""

    APPLIED = "applied"
    """Patches applied successfully, pending measurement."""

    PROMOTED = "promoted"
    """Modification passed all gates and is now permanent."""

    ROLLED_BACK = "rolled_back"
    """Modification failed safety gates and was reverted."""

    FAILED = "failed"
    """Modification could not be applied (pre-check failed, patch error)."""


@dataclass
class ModificationTarget:
    """What to modify — identifies the subsystem, file, and function."""

    system_name: str
    """Canonical system name (e.g. 'browser_automation', 'automated_build')."""

    target_file: str
    """Relative path from project root (e.g. 'core/tools/browser_tools.py')."""

    target_function: str = ""
    """Function/class name to modify (empty if file-level change)."""

    anchor_text: str = ""
    """Unique text anchor in the file for the transformation."""

    extra_params: dict[str, Any] = field(default_factory=dict)
    """Recipe-specific parameters (e.g. timeout_value, retry_count)."""


@dataclass
class ModificationPlan:
    """A complete plan for self-modification — planner output."""

    plan_id: str
    proposal_id: str
    recipe: ModificationRecipe
    target: ModificationTarget
    rationale: str
    expected_improvement: float = 0.0
    confidence: float = 0.0
    status: ModificationStatus = ModificationStatus.PLANNED
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "proposal_id": self.proposal_id,
            "recipe": self.recipe.value,
            "target_system": self.target.system_name,
            "target_file": self.target.target_file,
            "target_function": self.target.target_function,
            "rationale": self.rationale,
            "expected_improvement": round(self.expected_improvement, 3),
            "confidence": round(self.confidence, 3),
            "status": self.status.value,
        }


@dataclass
class ModificationRecord:
    """Persisted outcome of a modification attempt."""

    record_id: str
    plan_id: str
    proposal_id: str
    recipe: str
    target_system: str
    target_file: str
    status: ModificationStatus
    before_metrics: dict[str, float] = field(default_factory=dict)
    after_metrics: dict[str, float] = field(default_factory=dict)
    error_message: str = ""
    patch_count: int = 0
    test_count: int = 0
    test_passed: int = 0
    test_failed: int = 0
    created_at: str = ""
    completed_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "plan_id": self.plan_id,
            "proposal_id": self.proposal_id,
            "recipe": self.recipe,
            "target_system": self.target_system,
            "status": self.status.value,
            "patch_count": self.patch_count,
            "test_count": self.test_count,
            "test_passed": self.test_passed,
            "test_failed": self.test_failed,
            "error": self.error_message[:120] if self.error_message else "",
        }

    def success(self) -> bool:
        """True if the modification is currently promoted."""
        return self.status == ModificationStatus.PROMOTED

    def was_rolled_back(self) -> bool:
        return self.status == ModificationStatus.ROLLED_BACK


@dataclass
class ModificationMetrics:
    """Metrics collected before and after a modification for comparison."""

    test_pass_rate: float = 0.0
    execution_time_seconds: float = 0.0
    error_count: int = 0
    coverage_percent: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "test_pass_rate": round(self.test_pass_rate, 3),
            "execution_time_seconds": round(self.execution_time_seconds, 3),
            "error_count": float(self.error_count),
            "coverage_percent": round(self.coverage_percent, 3),
        }
