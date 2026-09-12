"""Module: core.planner.outcomes
Outcome model for planner execution results.

At minimum distinguish:
    SUCCESS
    FAILURE
    BLOCKED
    UNCONFIRMED
    REPLANNED

Critical rule:
    No verification
    → UNCONFIRMED

    Not SUCCESS
"""
from __future__ import annotations

from enum import Enum, auto
from typing import Any


class PlannerOutcome(str, Enum):
    """Outcome of a planner execution cycle."""

    SUCCESS = "success"
    FAILURE = "failure"
    BLOCKED = "blocked"
    UNCONFIRMED = "unconfirmed"
    REPLANNED = "replanned"


def determine_outcome(
    *,
    success: bool,
    verified: bool,
    replanned: bool = False,
) -> PlannerOutcome:
    """Determine the planner outcome from execution facts.

    Rules:
    1. If not success → FAILURE
    2. If success but not verified → UNCONFIRMED
    3. If success and verified and replanned → REPLANNED
    4. If success and verified and not replanned → SUCCESS
    """
    if not success:
        return PlannerOutcome.FAILURE
    if not verified:
        return PlannerOutcome.UNCONFIRMED
    if replanned:
        return PlannerOutcome.REPLANNED
    return PlannerOutcome.SUCCESS