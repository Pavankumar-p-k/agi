# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""core/success_criteria.py
Defines when a build is truly done — requirement completion score + binary pass/fail.
Not LLM opinions — real checks only.
"""
import logging

from core.project_state import ProjectState, Requirement, RequirementStatus, ValidationResult

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

COMPLETION_TARGET = 100.0


def is_done(state: ProjectState, results: list[ValidationResult] = None) -> tuple[bool, list[str]]:
    """Returns (is_done: bool, reasons: list[str]).

    DONE if ALL required checks pass AND completion_score == COMPLETION_TARGET.
    """
    update_requirement_status(state)

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

    if done and state.completion_score < COMPLETION_TARGET:
        failed.append(f"completion:{state.completion_score:.0f}% < {COMPLETION_TARGET:.0f}%")
        done = False

    return done, failed


def update_requirement_status(state: ProjectState):
    """Update requirement statuses based on validation results and quality scores."""
    if not state.requirements:
        return

    checks = state.validation_results or []
    quality = state.quality_score or {}

    reqs = [Requirement(**r) if isinstance(r, dict) else r for r in state.requirements]

    all_pages_exist = any(r.passed for r in checks if r.check == "all_pages_exist")
    html_valid = any(r.passed for r in checks if r.check == "html_valid")

    for req in reqs:
        desc = req.description.lower()
        cat = req.category

        if cat == "pages":
            req.status = RequirementStatus.MET if all_pages_exist else RequirementStatus.NOT_MET
        elif cat == "features":
            if "dark mode" in desc:
                vresult = next((r for r in checks if r.check == "visual_quality"), None)
                if vresult and "dark" in vresult.details.lower():
                    req.status = RequirementStatus.MET
                else:
                    req.status = RequirementStatus.UNKNOWN
            elif "contact form" in desc:
                req.status = RequirementStatus.MET if all_pages_exist else RequirementStatus.NOT_MET
            else:
                avg_quality = quality.get("average", 0.0) if quality else 0.0
                req.status = RequirementStatus.MET if avg_quality >= 6.0 else RequirementStatus.PARTIAL
        elif cat == "tech":
            req.status = RequirementStatus.MET if html_valid else RequirementStatus.PARTIAL
        elif cat == "branding":
            vresult = next((r for r in checks if r.check == "visual_quality"), None)
            if vresult:
                passed = vresult.passed
                req.status = RequirementStatus.MET if passed else RequirementStatus.PARTIAL
            else:
                req.status = RequirementStatus.UNKNOWN
        elif cat == "business":
            req.status = RequirementStatus.MET if all_pages_exist else RequirementStatus.PARTIAL
        else:
            req.status = RequirementStatus.UNKNOWN

    state.requirements = [r.__dict__ if hasattr(r, "__dict__") else r for r in reqs]
    state.compute_completion()


def get_summary(state: ProjectState) -> dict:
    """Human-readable summary of validation status with requirement completion."""
    done, failed = is_done(state)
    checks = state.validation_results or []
    return {
        "is_done": done,
        "failed_checks": failed,
        "total_checks": len(checks),
        "passed": sum(1 for c in checks if c.passed),
        "failed": sum(1 for c in checks if not c.passed),
        "retries": state.retries,
        "max_retries": state.max_retries,
        "status": state.status,
        "completion_score": state.completion_score,
        "requirement_count": len(state.requirements),
    }


def compute_tracker(state: ProjectState) -> dict:
    """Build a requirement tracker for display."""
    update_requirement_status(state)

    if not state.requirements:
        return {"completion": 0.0, "requirements": []}

    reqs = [Requirement(**r) if isinstance(r, dict) else r for r in state.requirements]
    lines = []
    for r in reqs:
        icon = {RequirementStatus.MET: "✓", RequirementStatus.NOT_MET: "✗",
                RequirementStatus.PARTIAL: "~", RequirementStatus.UNKNOWN: "?"}.get(r.status, "?")
        lines.append({"id": r.id, "status": r.status.value, "icon": icon, "description": r.description, "category": r.category})

    return {"completion": state.completion_score, "requirements": lines}


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
