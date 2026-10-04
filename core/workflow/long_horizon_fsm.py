"""Long-horizon execution state machine.

A small, explicit FSM that supervises multi-phase work: it gates which
tools are available per state, detects loop/timeout/stall conditions,
advances phases with per-phase validation, and exposes prompts/metrics
for the driving agent.  Rebuilt to the contract in
tests/unit/test_long_horizon_fsm.py.
"""
from __future__ import annotations

import copy
import time
from enum import Enum
from typing import Any, Optional


class ExecutionState(Enum):
    START = "START"
    PLAN = "PLAN"
    PREPARE = "PREPARE"
    EXECUTE_PHASE = "EXECUTE_PHASE"
    VALIDATE = "VALIDATE"
    ADVANCE = "ADVANCE"
    REPLAN = "REPLAN"
    RECOVER = "RECOVER"
    COMPLETE = "COMPLETE"
    FAIL = "FAIL"


DEFAULT_PHASES = ["research", "build", "test", "deliver"]

#: Same-tool / same-state repetition thresholds for loop detection.
SAME_TOOL_THRESHOLD = 3
SAME_STATE_THRESHOLD = 8
NO_ARTIFACT_THRESHOLD = 8
SAME_PHASE_THRESHOLD = 3


STATE_DEFS: dict[ExecutionState, dict[str, Any]] = {
    ExecutionState.START: {
        "allowed_tools": ["read_file", "write_file", "edit_file", "search"],
        "exit_tools": [],
        "max_actions": 5,
        "on_exit": None,
        "on_timeout": ExecutionState.PLAN,
        "on_loop": ExecutionState.PLAN,
        "prompt": "Starting long-horizon execution.",
    },
    ExecutionState.PLAN: {
        "allowed_tools": ["read_file", "write_file", "edit_file", "web_search"],
        "exit_tools": ["write_file"],
        "max_actions": 5,
        "on_exit": ExecutionState.PREPARE,
        "on_timeout": ExecutionState.REPLAN,
        "on_loop": ExecutionState.PREPARE,
        "prompt": "Planning the next steps for phase '{phase}'.",
    },
    ExecutionState.PREPARE: {
        "allowed_tools": ["read_file", "write_file", "edit_file", "bash", "python"],
        "exit_tools": ["start_execution"],
        "max_actions": 5,
        "on_exit": ExecutionState.EXECUTE_PHASE,
        "on_timeout": ExecutionState.PLAN,
        "on_loop": ExecutionState.PLAN,
        "prompt": "Preparing tools and context for phase '{phase}'.",
    },
    ExecutionState.EXECUTE_PHASE: {
        "allowed_tools": [
            "build_project", "run_tests", "write_file", "read_file",
            "edit_file", "bash", "python", "web_search", "browser_navigate",
        ],
        "exit_tools": ["build_project", "run_tests"],
        "max_actions": 20,
        "on_exit": ExecutionState.VALIDATE,
        "on_timeout": ExecutionState.REPLAN,
        "on_loop": ExecutionState.VALIDATE,
        "prompt": "Executing phase '{phase}' — produce real progress and artifacts.",
    },
    ExecutionState.VALIDATE: {
        "allowed_tools": ["read_file", "run_tests", "web_search"],
        "exit_tools": ["run_tests"],
        "max_actions": 5,
        "on_exit": ExecutionState.ADVANCE,
        "on_timeout": ExecutionState.RECOVER,
        "on_loop": ExecutionState.RECOVER,
        "prompt": "Validating output of phase '{phase}'.",
    },
    ExecutionState.ADVANCE: {
        "allowed_tools": ["read_file", "write_file"],
        "exit_tools": ["advance"],
        "max_actions": 3,
        "on_exit": ExecutionState.EXECUTE_PHASE,
        "on_timeout": ExecutionState.EXECUTE_PHASE,
        "on_loop": ExecutionState.REPLAN,
        "prompt": "Advancing to the next phase.",
    },
    ExecutionState.REPLAN: {
        "allowed_tools": ["read_file", "write_file", "edit_file"],
        "exit_tools": ["rewrite_plan"],
        "max_actions": 3,
        "on_exit": ExecutionState.PREPARE,
        "on_timeout": ExecutionState.FAIL,
        "on_loop": ExecutionState.FAIL,
        "prompt": "Replanning after insufficient progress on '{phase}'.",
    },
    ExecutionState.RECOVER: {
        "allowed_tools": ["read_file"],
        "exit_tools": ["recovery_done"],
        "max_actions": 3,
        "on_exit": ExecutionState.REPLAN,
        "on_timeout": ExecutionState.FAIL,
        "on_loop": ExecutionState.FAIL,
        "prompt": "Recovering from a failed step in '{phase}'.",
    },
    ExecutionState.COMPLETE: {
        "allowed_tools": [],
        "exit_tools": [],
        "max_actions": 0,
        "on_exit": None,
        "on_timeout": None,
        "on_loop": None,
        "prompt": "Execution complete — all phases finished.",
    },
    ExecutionState.FAIL: {
        "allowed_tools": [],
        "exit_tools": [],
        "max_actions": 0,
        "on_exit": None,
        "on_timeout": None,
        "on_loop": None,
        "prompt": "Execution failed — cannot continue.",
    },
}

#: Per-phase validation criteria consumed by ``LongHorizonFSM.validate_phase``.
PHASE_VALIDATION: dict[str, dict[str, Any]] = {
    "research": {
        "min_actions": 1,
        "expected_tools": ["web_search", "browser_navigate", "read_file", "search"],
        "requires_artifacts": False,
        "requires_success": False,
    },
    "build": {
        "min_actions": 1,
        "expected_tools": ["build_project", "write_file", "edit_file", "python", "bash"],
        "requires_artifacts": True,
        "requires_success": False,
    },
    "test": {
        "min_actions": 1,
        "expected_tools": ["run_tests", "python", "bash"],
        "requires_artifacts": False,
        "requires_success": True,
    },
    "deliver": {
        "min_actions": 1,
        "expected_tools": ["write_file", "send_email", "build_project", "edit_file"],
        "requires_artifacts": False,
        "requires_success": False,
    },
}


def create_context(phases: Optional[list[str]] = None) -> dict[str, Any]:
    """Fresh FSM context; *phases* defaults to :data:`DEFAULT_PHASES`."""
    resolved = list(DEFAULT_PHASES if phases is None else phases)
    return {
        "phases": resolved,
        "completed_phases": [],
        "remaining_phases": list(resolved),
        "artifacts": [],
        "artifact_count": 0,
        "retry_count": 0,
        "validation_failures": 0,
        "replan_count": 0,
        "same_phase_count": 0,
        "validation_results": {},
        "execution_history": [],
        "action_results": [],
    }


class LongHorizonFSM:
    """Explicit state machine supervising multi-phase execution."""

    def __init__(self, ctx: Optional[dict[str, Any]] = None) -> None:
        self.ctx: dict[str, Any] = create_context() if ctx is None else ctx
        self.state = ExecutionState.START
        self.transitions: list[dict[str, Any]] = []
        self.forced_transitions = 0
        self.loops_prevented = 0
        self.timeouts = 0
        self.total_actions = 0
        self.actions_in_state = 0
        self.last_tool_name: Optional[str] = None
        self.consecutive_same_tool = 0
        self.consecutive_same_state = 0
        self.validation_failures = int(self.ctx.get("validation_failures", 0))
        self.last_state_transition_time = time.time()

    # ── Introspection ────────────────────────────────────────────────

    def get_current_phase(self) -> Optional[str]:
        phases = self.ctx.get("phases") or []
        idx = len(self.ctx.get("completed_phases") or [])
        return phases[idx] if idx < len(phases) else None

    def is_terminal(self) -> bool:
        return self.state in (ExecutionState.COMPLETE, ExecutionState.FAIL)

    def fraction_complete(self) -> float:
        phases = self.ctx.get("phases") or []
        if not phases:
            return 1.0
        return len(self.ctx.get("completed_phases") or []) / len(phases)

    def is_tool_allowed(self, tool: str) -> bool:
        allowed = STATE_DEFS[self.state].get("allowed_tools") or []
        return tool in allowed

    def is_exit_tool(self, tool: str) -> bool:
        exit_tools = STATE_DEFS[self.state].get("exit_tools") or []
        return tool in exit_tools

    # ── Action recording ─────────────────────────────────────────────

    def record_action(self, tool: str, result: Any = None) -> None:
        if self.state == ExecutionState.START:
            self.transition_to(ExecutionState.PLAN)
        self.total_actions += 1
        self.actions_in_state += 1
        if tool == self.last_tool_name:
            self.consecutive_same_tool += 1
        else:
            self.consecutive_same_tool = 1
        self.last_tool_name = tool
        self.consecutive_same_state += 1
        if result is not None:
            self.ctx.setdefault("action_results", []).append(result)
        self.ctx.setdefault("execution_history", []).append({
            "tool": tool,
            "phase": self.get_current_phase(),
            "state": self.state.value,
            "ts": time.time(),
        })

    def record_artifact(self, name: str) -> None:
        artifacts = self.ctx.setdefault("artifacts", [])
        if name not in artifacts:
            artifacts.append(name)
        self.ctx["artifact_count"] = len(artifacts)

    # ── Loop / timeout / stall detection ─────────────────────────────

    def check_loop(self) -> tuple[bool, str]:
        if self.is_terminal():
            return False, ""
        if int(self.ctx.get("same_phase_count", 0)) >= SAME_PHASE_THRESHOLD:
            return True, "same_phase: phase repeated too many times"
        if self.consecutive_same_tool >= SAME_TOOL_THRESHOLD:
            return True, "same_tool: consecutive identical tool calls"
        if self.consecutive_same_state >= SAME_STATE_THRESHOLD:
            return True, "same_state: too many actions without state change"
        if (self.actions_in_state >= NO_ARTIFACT_THRESHOLD
                and not (self.ctx.get("artifacts") or [])):
            return True, "no_artifact: actions without any artifact progress"
        return False, ""

    def check_timeout(self) -> bool:
        if self.is_terminal():
            return False
        max_actions = int(STATE_DEFS[self.state].get("max_actions") or 0)
        if max_actions > 0 and self.actions_in_state > max_actions:
            self.timeouts += 1
            return True
        return False

    def check_stall(self, stall_timeout: float = 60.0) -> bool:
        if self.is_terminal():
            return False
        return (time.time() - self.last_state_transition_time) > stall_timeout

    # ── Handlers ─────────────────────────────────────────────────────

    def handle_timeout(self) -> Optional[ExecutionState]:
        if self.is_terminal():
            return None
        if not self.check_timeout():
            return None
        target = STATE_DEFS[self.state].get("on_timeout")
        if target is None:
            return None
        if target == ExecutionState.REPLAN:
            self.ctx["replan_count"] = int(self.ctx.get("replan_count", 0)) + 1
        self.transition_to(target, forced=True)
        return target

    def handle_loop(self) -> Optional[ExecutionState]:
        is_loop, _reason = self.check_loop()
        if not is_loop:
            return None
        target = STATE_DEFS[self.state].get("on_loop")
        if target is None:
            return None
        self.loops_prevented += 1
        self.transition_to(target, forced=True)
        return target

    def handle_exit_tool(self, tool: str) -> Optional[ExecutionState]:
        if self.is_terminal():
            return None
        defn = STATE_DEFS[self.state]
        if tool not in (defn.get("exit_tools") or []):
            return None
        target = defn.get("on_exit")
        if target is None:
            return None
        self.transition_to(target)
        return target

    # ── Transitions ──────────────────────────────────────────────────

    def transition_to(self, target: ExecutionState, forced: bool = False) -> None:
        if target == self.state:
            return
        self.transitions.append({
            "from": self.state.value,
            "to": target.value,
            "forced": bool(forced),
        })
        if forced:
            self.forced_transitions += 1
        self.state = target
        self.actions_in_state = 0
        self.consecutive_same_state = 0
        self.last_state_transition_time = time.time()

    # ── Phase lifecycle ──────────────────────────────────────────────

    def advance_phase(self) -> Optional[str]:
        phases = self.ctx.get("phases") or []
        completed = self.ctx.setdefault("completed_phases", [])
        if not phases or len(completed) >= len(phases):
            self.state = ExecutionState.COMPLETE
            return None
        completed.append(phases[len(completed)])
        self.ctx["remaining_phases"] = phases[len(completed):]
        self.ctx["same_phase_count"] = 0
        if len(completed) >= len(phases):
            self.state = ExecutionState.COMPLETE
            return None
        return phases[len(completed)]

    def check_completion(self) -> bool:
        phases = self.ctx.get("phases") or []
        if not phases:
            return True
        return len(self.ctx.get("completed_phases") or []) >= len(phases)

    def validate_phase(self, phase: str) -> dict[str, Any]:
        criteria = PHASE_VALIDATION.get(phase, {
            "min_actions": 1,
            "expected_tools": [],
            "requires_artifacts": False,
            "requires_success": False,
        })
        history = self.ctx.get("execution_history") or []
        tools = {entry.get("tool") for entry in history}
        results = self.ctx.get("action_results") or []
        artifacts = self.ctx.get("artifacts") or []

        failures: list[str] = []
        if len(history) < int(criteria.get("min_actions", 0)):
            failures.append(
                f"min_actions: recorded {len(history)} < required "
                f"{criteria.get('min_actions', 0)}"
            )
        expected = criteria.get("expected_tools") or []
        if expected and not (tools & set(expected)):
            failures.append(
                f"expected_tools: none of {sorted(expected)} were used "
                f"(used {sorted(t for t in tools if t)})"
            )
        if criteria.get("requires_artifacts") and not artifacts:
            failures.append("artifacts: phase produced no artifacts")
        if criteria.get("requires_success") and not any(
            isinstance(r, dict) and r.get("success") for r in results
        ):
            failures.append("results: no successful result recorded")

        result = {"valid": not failures, "failures": failures}
        self.ctx.setdefault("validation_results", {})[phase] = result
        if failures:
            self.validation_failures += 1
            self.ctx["validation_failures"] = self.validation_failures
        return result

    # ── Prompt / metrics / persistence ───────────────────────────────

    def get_prompt(self) -> str:
        template = STATE_DEFS[self.state].get("prompt") or ""
        return template.format(phase=self.get_current_phase() or "current")

    def get_metrics(self) -> dict[str, Any]:
        return {
            "fsm_final_state": self.state.value,
            "fsm_total_actions": self.total_actions,
            "fsm_transitions": len(self.transitions),
            "fsm_phases_total": len(self.ctx.get("phases") or []),
            "fsm_fraction_complete": self.fraction_complete(),
            "fsm_forced_transitions": self.forced_transitions,
            "fsm_loops_prevented": self.loops_prevented,
            "fsm_timeouts": self.timeouts,
            "fsm_validation_failures": self.validation_failures,
        }

    def to_context_dict(self) -> dict[str, Any]:
        return {
            "fsm_state": self.state.value,
            "ctx": copy.deepcopy(self.ctx),
            "total_actions": self.total_actions,
            "actions_in_state": self.actions_in_state,
            "last_tool_name": self.last_tool_name,
            "consecutive_same_tool": self.consecutive_same_tool,
            "consecutive_same_state": self.consecutive_same_state,
            "forced_transitions": self.forced_transitions,
            "loops_prevented": self.loops_prevented,
            "timeouts": self.timeouts,
            "validation_failures": self.validation_failures,
            "transitions": list(self.transitions),
            "last_state_transition_time": self.last_state_transition_time,
        }

    @classmethod
    def from_context_dict(cls, data: dict[str, Any]) -> "LongHorizonFSM":
        ctx = data.get("ctx") or create_context()
        fsm = cls(ctx=ctx)
        raw_state = data.get("fsm_state") or ExecutionState.START.value
        try:
            fsm.state = ExecutionState(raw_state)
        except ValueError:
            fsm.state = ExecutionState.START
        fsm.total_actions = int(data.get("total_actions", 0))
        fsm.actions_in_state = int(data.get("actions_in_state", 0))
        fsm.last_tool_name = data.get("last_tool_name")
        fsm.consecutive_same_tool = int(data.get("consecutive_same_tool", 0))
        fsm.consecutive_same_state = int(data.get("consecutive_same_state", 0))
        fsm.forced_transitions = int(data.get("forced_transitions", 0))
        fsm.loops_prevented = int(data.get("loops_prevented", 0))
        fsm.timeouts = int(data.get("timeouts", 0))
        fsm.validation_failures = int(
            data.get("validation_failures", ctx.get("validation_failures", 0))
        )
        fsm.transitions = list(data.get("transitions") or [])
        fsm.last_state_transition_time = float(
            data.get("last_state_transition_time", time.time())
        )
        return fsm
