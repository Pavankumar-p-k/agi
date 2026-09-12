"""Module: core.planner.state_machine
Deterministic planner state machine with valid transitions and evidence tracking.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


class PlannerStateName(str, Enum):
    CREATED = "created"
    READY = "ready"
    RUNNING = "running"
    BLOCKED = "blocked"
    FAILED = "failed"
    REPLANNING = "replanning"
    RETRYING = "retrying"
    COMPLETED = "completed"
    ABORTED = "aborted"


@dataclass
class PlannerStateMachine:
    """Deterministic planner state machine with valid transition tracking."""

    current: PlannerStateName = PlannerStateName.CREATED
    _transition_history: list[dict[str, Any]] = field(
        default_factory=list
    )
    _failure_reason: str | None = None
    _transition_evidence: dict[str, Any] = field(default_factory=dict)

    # ——— valid transitions ———
    # CREATED
    CREATED_TO_READY = "created -> ready"
    CREATED_TO_FAILED = "created -> failed"
    # READY
    READY_TO_RUNNING = "ready -> running"
    READY_TO_FAILED = "ready -> failed"
    # RUNNING
    RUNNING_TO_COMPLETED = "running -> completed"
    RUNNING_TO_FAILED = "running -> failed"
    RUNNING_TO_BLOCKED = "running -> blocked"
    RUNNING_TO_REPLANNING = "running -> replanning"
    RUNNING_TO_RETRYING = "running -> retrying"
    # BLOCKED
    BLOCKED_TO_RETRYING = "blocked -> retrying"
    BLOCKED_TO_FAILED = "blocked -> failed"
    # FAILED
    FAILED_TO_REPLANNING = "failed -> replanning"
    FAILED_TO_ABORTED = "failed -> aborted"
    # REPLANNING
    REPLANNING_TO_RUNNING = "replanning -> running"
    REPLANNING_TO_FAILED = "replanning -> failed"
    # RETRYING
    RETRYING_TO_RUNNING = "retrying -> running"
    RETRYING_TO_FAILED = "retrying -> failed"
    # COMPLETED/ABORTED are terminal
    COMPLETED_TO_ANY = "terminal"
    ABORTED_TO_ANY = "terminal"

    # ——— transition matrix ———
    _transition_matrix: dict[PlannerStateName, set[PlannerStateName]] = field(
        init=False, default_factory=lambda: {
            PlannerStateName.CREATED: {
                PlannerStateName.READY,
                PlannerStateName.FAILED,
            },
            PlannerStateName.READY: {
                PlannerStateName.RUNNING,
                PlannerStateName.FAILED,
            },
            PlannerStateName.RUNNING: {
                PlannerStateName.COMPLETED,
                PlannerStateName.FAILED,
                PlannerStateName.BLOCKED,
                PlannerStateName.REPLANNING,
                PlannerStateName.RETRYING,
            },
            PlannerStateName.BLOCKED: {
                PlannerStateName.RETRYING,
                PlannerStateName.FAILED,
            },
            PlannerStateName.FAILED: {
                PlannerStateName.REPLANNING,
                PlannerStateName.ABORTED,
            },
            PlannerStateName.REPLANNING: {
                PlannerStateName.RUNNING,
                PlannerStateName.FAILED,
            },
            PlannerStateName.RETRYING: {
                PlannerStateName.RUNNING,
                PlannerStateName.FAILED,
            },
            PlannerStateName.COMPLETED: set(),
            PlannerStateName.ABORTED: set(),
        }
    )

    # ——— transition rules ———
    def _is_valid_transition(self, from_state: PlannerStateName, to_state: PlannerStateName) -> bool:
        allowed = self._transition_matrix.get(from_state, set())
        return to_state in allowed

    # ——— public API ———
    def transition(self, to_state: PlannerStateName, *, reason: str | None = None) -> bool:
        """Attempt a state transition. Returns True if accepted, False if invalid."""
        from_state = PlannerStateName(self.current)
        if not self._is_valid_transition(from_state, to_state):
            return False

        self.current = to_state
        if reason is not None:
            self._failure_reason = reason
        self._record_transition(from_state, to_state, reason)
        return True

    def _record_transition(
        self, from_state: PlannerStateName, to_state: PlannerStateName, reason: str | None
    ) -> None:
        self._transition_history.append(
            {
                "from": from_state.value,
                "to": to_state.value,
                "reason": reason,
                "timestamp": len(self._transition_history),  # index as proxy
            }
        )

    def can_transition_to(self, to_state: PlannerStateName) -> bool:
        """Check if a transition to the given state is valid from current state."""
        return self._is_valid_transition(PlannerStateName(self.current), to_state)

    def current_state(self) -> PlannerStateName:
        """Return the current planner state."""
        return PlannerStateName(self.current)

    def failure_reason(self) -> str | None:
        """Return the recorded failure reason, if any."""
        return self._failure_reason

    def transition_history(self) -> list[dict[str, Any]]:
        """Return a copy of the transition history for evidence/debugging."""
        return list(self._transition_history)

    def reset(self) -> None:
        """Reset the state machine to CREATED state."""
        self.current = PlannerStateName.CREATED
        self._transition_history.clear()
        self._failure_reason = None
        self._transition_evidence.clear()