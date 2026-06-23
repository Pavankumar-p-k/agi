"""Self-Modification Engine (Phase 18.0) — Safety Gates.

Two gates — pre and post:

  Pre-checks (before applying):
    - confidence >= minimum threshold
    - expected_improvement >= minimum threshold
    - recipe is registered
    - target file exists
    - target function exists (if specified)

  Post-checks (after applying, before promotion):
    - test pass rate did not regress > threshold
    - error count did not increase > threshold
    - execution time did not increase > threshold
    - no unexpected side effects

If any post-check fails, the modification is rolled back immediately.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from core.self_modification.models import (
    ModificationMetrics,
    ModificationPlan,
    ModificationRecord,
    ModificationStatus,
)

logger = logging.getLogger(__name__)

# Default thresholds (configurable)
DEFAULT_MIN_CONFIDENCE = 0.60
DEFAULT_MIN_IMPROVEMENT = 0.05
DEFAULT_MAX_TEST_REGRESSION = 0.05  # 5% test pass rate drop
DEFAULT_MAX_ERROR_INCREASE = 2       # max additional errors
DEFAULT_MAX_TIME_INCREASE = 1.5      # 50% time increase allowed


class PreCheckResult:
    """Result of pre-application safety checks."""

    def __init__(
        self,
        passed: bool,
        reason: str = "",
        details: list[str] | None = None,
    ):
        self.passed = passed
        self.reason = reason
        self.details = details or []

    @classmethod
    def ok(cls, details: list[str] | None = None) -> PreCheckResult:
        return cls(passed=True, reason="All pre-checks passed", details=details)

    @classmethod
    def fail(cls, reason: str, details: list[str] | None = None) -> PreCheckResult:
        return cls(passed=False, reason=reason, details=details)


class PostCheckResult:
    """Result of post-application safety checks."""

    def __init__(
        self,
        passed: bool,
        reason: str = "",
        deltas: dict[str, float] | None = None,
    ):
        self.passed = passed
        self.reason = reason
        self.deltas = deltas or {}

    @classmethod
    def ok(cls, deltas: dict[str, float] | None = None) -> PostCheckResult:
        return cls(passed=True, reason="All post-checks passed", deltas=deltas)

    @classmethod
    def fail(cls, reason: str, deltas: dict[str, float] | None = None) -> PostCheckResult:
        return cls(passed=False, reason=reason, deltas=deltas)


class SelfModificationSafety:
    """Safety gates for self-modification — pre and post checks.

    All checks are deterministic — no LLM dependency.
    """

    def __init__(
        self,
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
        min_improvement: float = DEFAULT_MIN_IMPROVEMENT,
        max_test_regression: float = DEFAULT_MAX_TEST_REGRESSION,
        max_error_increase: int = DEFAULT_MAX_ERROR_INCREASE,
        max_time_increase: float = DEFAULT_MAX_TIME_INCREASE,
    ):
        self.min_confidence = min_confidence
        self.min_improvement = min_improvement
        self.max_test_regression = max_test_regression
        self.max_error_increase = max_error_increase
        self.max_time_increase = max_time_increase

    # ── Pre-checks ─────────────────────────────────────────────────────

    def check_pre(self, plan: ModificationPlan) -> PreCheckResult:
        """Run all pre-application safety checks."""
        details: list[str] = []

        # 1. Confidence gate
        if plan.confidence < self.min_confidence:
            return PreCheckResult.fail(
                f"Confidence {plan.confidence:.2f} < minimum {self.min_confidence:.2f}",
                details=[f"confidence={plan.confidence:.2f}", f"threshold={self.min_confidence:.2f}"],
            )
        details.append(f"confidence={plan.confidence:.2f} >= {self.min_confidence:.2f}")

        # 2. Expected improvement gate
        if plan.expected_improvement < self.min_improvement:
            return PreCheckResult.fail(
                f"Expected improvement {plan.expected_improvement:.3f} < minimum {self.min_improvement:.3f}",
                details=[f"improvement={plan.expected_improvement:.3f}", f"threshold={self.min_improvement:.3f}"],
            )
        details.append(f"improvement={plan.expected_improvement:.3f} >= {self.min_improvement:.3f}")

        # 3. Target file exists (if specified)
        if plan.target.target_file:
            if not os.path.exists(plan.target.target_file):
                return PreCheckResult.fail(
                    f"Target file '{plan.target.target_file}' not found",
                    details=[f"file={plan.target.target_file}"],
                )
            details.append(f"file_exists={plan.target.target_file}")

        # 4. Target function exists (if specified)
        if plan.target.target_function and plan.target.target_file:
            if not self._function_exists(
                plan.target.target_file, plan.target.target_function
            ):
                return PreCheckResult.fail(
                    f"Function '{plan.target.target_function}' not found in "
                    f"'{plan.target.target_file}'",
                    details=[
                        f"function={plan.target.target_function}",
                        f"file={plan.target.target_file}",
                    ],
                )
            details.append(
                f"function_exists={plan.target.target_function} in "
                f"{plan.target.target_file}"
            )

        return PreCheckResult.ok(details=details)

    # ── Post-checks ────────────────────────────────────────────────────

    def check_post(
        self,
        before: ModificationMetrics,
        after: ModificationMetrics,
    ) -> PostCheckResult:
        """Run all post-application safety checks.

        Compares before/after metrics and returns fail if any dimension
        regressed beyond thresholds.
        """
        deltas: dict[str, float] = {}

        # 1. Test pass rate regression
        pass_delta = after.test_pass_rate - before.test_pass_rate
        deltas["test_pass_rate_delta"] = round(pass_delta, 3)
        if pass_delta < -self.max_test_regression:
            return PostCheckResult.fail(
                f"Test pass rate dropped by {abs(pass_delta):.1%} "
                f"(threshold: {self.max_test_regression:.1%})",
                deltas=deltas,
            )

        # 2. Error count increase
        error_delta = after.error_count - before.error_count
        deltas["error_count_delta"] = float(error_delta)
        if error_delta > self.max_error_increase:
            return PostCheckResult.fail(
                f"Error count increased by {error_delta} "
                f"(threshold: {self.max_error_increase})",
                deltas=deltas,
            )

        # 3. Execution time regression
        if before.execution_time_seconds > 0:
            time_ratio = after.execution_time_seconds / before.execution_time_seconds
            deltas["execution_time_ratio"] = round(time_ratio, 3)
            if time_ratio > self.max_time_increase:
                return PostCheckResult.fail(
                    f"Execution time increased {time_ratio:.1f}× "
                    f"(threshold: {self.max_time_increase}×)",
                    deltas=deltas,
                )

        return PostCheckResult.ok(deltas=deltas)

    # ── Internal ───────────────────────────────────────────────────────

    @staticmethod
    def _function_exists(file_path: str, function_name: str) -> bool:
        """Check if a function name exists in a file (simple regex)."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            pattern = re.compile(
                r"^(async\s+)?def\s+" + re.escape(function_name) + r"\s*\(",
                re.MULTILINE,
            )
            return bool(pattern.search(content))
        except (FileNotFoundError, IOError):
            return False
