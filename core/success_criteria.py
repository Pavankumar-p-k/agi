"""core/success_criteria.py
Defines when a build is truly done — binary pass/fail based on real validation.
Not LLM opinions — real checks only.
"""
import logging
from core.project_state import ProjectState, ValidationResult

logger = logging.getLogger("success_criteria")

REQUIRED_CHECKS = [
    "all_pages_exist",
    "no_broken_links",
    "no_placeholders",
    "nav_consistent",
    "html_valid",
]

CRITICAL_CHECKS = ["all_pages_exist"]
SOFT_CHECKS = ["nav_consistent", "html_valid"]


def is_done(state: ProjectState, results: list[ValidationResult] = None) -> tuple[bool, list[str]]:
    """Returns (is_done: bool, reasons: list[str]).

    DONE if ALL required checks pass. CRITICAL checks must ALL pass.
    SOFT checks can fail up to configurable threshold.
    """
    checks = results or state.validation_results
    if not checks:
        return False, ["no_validation_results"]

    required = state.interpreted_goal.get("success_criteria", REQUIRED_CHECKS) if state.interpreted_goal else REQUIRED_CHECKS
    failed = []

    for check in required:
        matching = [r for r in checks if r.check == check]
        if not matching:
            failed.append(f"{check}:no_result")
            continue
        if not all(r.passed for r in matching):
            if check in CRITICAL_CHECKS or check not in SOFT_CHECKS:
                failed.append(f"{check}:failed")

    done = len(failed) == 0
    return done, failed


def get_summary(state: ProjectState) -> dict:
    """Human-readable summary of validation status."""
    done, failed = is_done(state)
    checks = state.validation_results
    return {
        "is_done": done,
        "failed_checks": failed,
        "total_checks": len(checks),
        "passed": sum(1 for c in checks if c.passed),
        "failed": sum(1 for c in checks if not c.passed),
        "retries": state.retries,
        "max_retries": state.max_retries,
        "status": state.status,
    }


def should_retry(state: ProjectState) -> tuple[bool, str]:
    """Determine if we should retry based on state + results.

    Returns (should_retry: bool, reason: str).
    """
    if state.retries >= state.max_retries:
        return False, "max_retries_exceeded"

    done, failed = is_done(state)
    if done:
        return False, "already_done"

    if state.status == "failed":
        return False, "build_failed"

    if not failed:
        return False, "no_failures_but_not_done"

    return True, f"retry_{state.retries + 1}_for_{','.join(failed)}"
