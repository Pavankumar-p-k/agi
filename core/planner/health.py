"""Module: core.planner.health
Planner health reporting — deterministic information about planner status.

Exposes useful information such as:
    • planner available/unavailable
    • active plan
    • current state
    • failed steps
    • replans attempted
    • successful replans
    • terminal failures
    • malformed plans / contracts
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional


class PlannerAvailability(str, Enum):
    """Whether the planner is available for use."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    INITIALIZING = "initializing"
    ERROR = "error"


@dataclass
class PlannerHealthReport:
    """Structured health report for the planner subsystem."""

    availability: PlannerAvailability = PlannerAvailability.AVAILABLE
    current_state: str = "unknown"
    active_plan_id: str = ""
    failed_steps: int = 0
    replans_attempted: int = 0
    successful_replans: int = 0
    terminal_failures: int = 0
    malformed_contracts: int = 0
    active_sub_goals: int = 0
    completed_sub_goals: int = 0
    timestamp: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a serializable dict."""
        return {
            "availability": self.availability.value,
            "current_state": self.current_state,
            "active_plan_id": self.active_plan_id,
            "failed_steps": self.failed_steps,
            "replans_attempted": self.replans_attempted,
            "successful_replans": self.successful_replans,
            "terminal_failures": self.terminal_failures,
            "malformed_contracts": self.malformed_contracts,
            "active_sub_goals": self.active_sub_goals,
            "completed_sub_goals": self.completed_sub_goals,
            "timestamp": self.timestamp,
        }


class PlannerHealth:
    """Singleton-like health tracker for the planner."""

    _instance: "PlannerHealth | None" = None

    def __init__(self):
        if PlannerHealth._instance is not None:
            raise RuntimeError("Use PlannerHealth.instance() instead.")
        self._report = PlannerHealthReport(timestamp=0)
        PlannerHealth._instance = self

    @classmethod
    def instance(cls) -> "PlannerHealth":
        """Get the singleton planner health instance."""
        if cls._instance is None:
            cls._instance = PlannerHealth()
        return cls._instance

    # ——— mutating observers (called by other components) ———

    def plan_available(self, available: bool = True) -> None:
        """Set planner availability."""
        self._report.available = PlannerAvailability.AVAILABLE if available else PlannerAvailability.UNAVAILABLE

    def set_current_state(self, state: str) -> None:
        """Set the current planner state."""
        self._report.current_state = state

    def set_active_plan(self, plan_id: str) -> None:
        """Set the currently active plan ID."""
        self._report.active_plan_id = plan_id

    def step_failed(self) -> None:
        """Record that a step has failed."""
        self._report.failed_steps += 1

    def step_completed(self) -> None:
        """Record that a step has completed."""
        self._report.completed_sub_goals += 1

    def replan_attempted(self) -> None:
        """Record that a replan was attempted."""
        self._report.replans_attempted += 1

    def replan_succeeded(self) -> None:
        """Record that a replan succeeded."""
        self._report.successful_replans += 1

    def terminal_failure(self) -> None:
        """Record a terminal failure."""
        self._report.terminal_failures += 1

    def malformed_contract(self) -> None:
        """Record a malformed plan/contract."""
        self._report.malformed_contracts += 1

    def set_active_sub_goals(self, count: int) -> None:
        """Set the number of active sub-goals."""
        self._report.active_sub_goals = count

    # ——— querying ———

    def current_report(self) -> PlannerHealthReport:
        """Return the current health report."""
        self._report.timestamp = (
            self._report.timestamp + 1
        )  # simple increment as proxy
        return self._report