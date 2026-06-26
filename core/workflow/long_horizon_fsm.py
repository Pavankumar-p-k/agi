"""core/workflow/long_horizon_fsm.py
Long-Horizon Execution State Machine — deterministic multi-phase workflow control.

The LLM performs work inside EXECUTE_PHASE. The FSM decides:
- when a phase ends
- when validation succeeds
- when recovery begins
- when replanning begins
- when workflow completes

States:
  START          — initial state, awaiting workflow setup
  PLAN           — planning the execution phases
  PREPARE        — preparing environment/resources
  EXECUTE_PHASE  — executing the current phase (LLM does work here)
  VALIDATE       — validating phase outputs
  ADVANCE        — advancing to the next phase
  REPLAN         — replanning after failure
  RECOVER        — recovering from tool/validation failure
  COMPLETE       — workflow completed successfully
  FAIL           — unrecoverable error

Each state:
  - allowed_tools: which tools may be called
  - exit_conditions: when to auto-transition
  - failure_conditions: when to fail or escalate
  - max_actions: max allowed tool calls in this state
  - on_exit: target state on clean exit
  - on_failure: target state on timeout/failure
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


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


# ── State definitions ──────────────────────────────────────────

STATE_DEFS: dict[ExecutionState, dict[str, Any]] = {
    ExecutionState.START: {
        "allowed_tools": {"read_file", "write_file"},
        "exit_tools": {"write_file"},
        "max_actions": 1,
        "on_exit": ExecutionState.PLAN,
        "on_timeout": ExecutionState.FAIL,
        "on_recovery": ExecutionState.FAIL,
        "prompt": "Starting long-horizon execution. Initialize workflow context.",
    },
    ExecutionState.PLAN: {
        "allowed_tools": {"read_file", "write_file", "web_search", "web_fetch"},
        "exit_tools": {"write_file"},
        "max_actions": 5,
        "on_exit": ExecutionState.PREPARE,
        "on_timeout": ExecutionState.REPLAN,
        "on_recovery": ExecutionState.REPLAN,
        "max_retries": 2,
        "prompt": "Planning phase: define execution phases and objectives.",
    },
    ExecutionState.PREPARE: {
        "allowed_tools": {"bash", "python", "write_file", "read_file", "build_project"},
        "exit_tools": {"build_project", "write_file"},
        "max_actions": 3,
        "on_exit": ExecutionState.EXECUTE_PHASE,
        "on_timeout": ExecutionState.RECOVER,
        "on_recovery": ExecutionState.EXECUTE_PHASE,
        "max_retries": 2,
        "prompt": "Preparing environment: set up project structure and dependencies.",
    },
    ExecutionState.EXECUTE_PHASE: {
        "allowed_tools": {
            "read_file", "write_file", "edit_file", "build_project", "run_tests",
            "bash", "python", "web_search", "web_fetch",
            "browser_navigate", "browser_snapshot", "browser_fill",
            "browser_press", "browser_click", "browser_evaluate",
        },
        "exit_tools": {"build_project", "run_tests", "write_file", "send_email"},
        "max_actions": 15,
        "on_exit": ExecutionState.VALIDATE,
        "on_timeout": ExecutionState.RECOVER,
        "on_recovery": ExecutionState.EXECUTE_PHASE,
        "max_retries": 3,
        "prompt": "Executing current phase. Use appropriate tools to complete the phase objective.",
    },
    ExecutionState.VALIDATE: {
        "allowed_tools": {"read_file", "run_tests", "bash", "python", "browser_snapshot", "browser_evaluate"},
        "exit_tools": {"run_tests", "read_file"},
        "max_actions": 3,
        "on_exit": ExecutionState.ADVANCE,
        "on_timeout": ExecutionState.RECOVER,
        "on_failure": ExecutionState.REPLAN,
        "on_recovery": ExecutionState.VALIDATE,
        "max_retries": 2,
        "prompt": "Validating phase outputs: check artifacts, tests, and completion criteria.",
    },
    ExecutionState.ADVANCE: {
        "allowed_tools": {"read_file"},
        "exit_tools": set(),
        "max_actions": 0,
        "on_exit": None,
        "on_timeout": ExecutionState.FAIL,
        "on_recovery": ExecutionState.FAIL,
        "max_retries": 0,
        "prompt": "Advancing to next phase.",
    },
    ExecutionState.REPLAN: {
        "allowed_tools": {"read_file", "write_file", "web_search", "web_fetch"},
        "exit_tools": {"write_file"},
        "max_actions": 4,
        "on_exit": ExecutionState.PREPARE,
        "on_timeout": ExecutionState.FAIL,
        "on_recovery": ExecutionState.REPLAN,
        "max_retries": 2,
        "prompt": "Replanning after failure: adjust the plan and retry.",
    },
    ExecutionState.RECOVER: {
        "allowed_tools": {"read_file", "write_file", "edit_file", "bash", "python"},
        "exit_tools": {"write_file", "edit_file"},
        "max_actions": 3,
        "on_exit": ExecutionState.EXECUTE_PHASE,
        "on_timeout": ExecutionState.FAIL,
        "on_recovery": ExecutionState.RECOVER,
        "max_retries": 2,
        "prompt": "Recovering from failure: fix the issue and continue.",
    },
    ExecutionState.COMPLETE: {
        "allowed_tools": set(),
        "exit_tools": set(),
        "max_actions": 0,
        "on_exit": None,
        "on_timeout": None,
        "prompt": "Workflow complete.",
    },
    ExecutionState.FAIL: {
        "allowed_tools": {"read_file"},
        "exit_tools": set(),
        "max_actions": 1,
        "on_exit": None,
        "on_timeout": None,
        "prompt": "Workflow failed.",
    },
}


# ── Phase definitions ──────────────────────────────────────────

DEFAULT_PHASES = ["research", "plan", "build", "test", "repair", "retest", "deliver"]

PHASE_TOOLS: dict[str, set[str]] = {
    "research": {"web_search", "web_fetch", "browser_navigate", "browser_snapshot"},
    "plan": {"write_file", "read_file"},
    "build": {"write_file", "read_file", "edit_file", "build_project"},
    "test": {"run_tests", "read_file"},
    "repair": {"read_file", "edit_file", "write_file", "build_project", "run_tests"},
    "retest": {"run_tests", "read_file"},
    "deliver": {"send_email", "write_file", "read_file"},
}

PHASE_DEFS: dict[str, dict[str, Any]] = {
    "research": {
        "tools": ["web_search", "web_fetch", "browser_navigate", "browser_snapshot"],
        "prompt": "Research phase: gather information about the topic.",
        "next": "plan",
    },
    "plan": {
        "tools": ["write_file", "read_file"],
        "prompt": "Planning phase: create a plan document.",
        "next": "build",
    },
    "build": {
        "tools": ["write_file", "read_file", "edit_file", "build_project"],
        "prompt": "Build phase: write code and build the project.",
        "next": "test",
    },
    "test": {
        "tools": ["run_tests", "read_file"],
        "prompt": "Test phase: run tests and check results.",
        "next": "repair",
    },
    "repair": {
        "tools": ["read_file", "edit_file", "write_file", "build_project", "run_tests"],
        "prompt": "Repair phase: fix any failures found during testing.",
        "next": "retest",
    },
    "retest": {
        "tools": ["run_tests", "read_file"],
        "prompt": "Re-test phase: verify repairs and re-run tests.",
        "next": "deliver",
    },
    "deliver": {
        "tools": ["send_email", "write_file", "read_file"],
        "prompt": "Delivery phase: communicate results.",
        "next": None,
    },
}

PHASE_VALIDATION: dict[str, dict[str, Any]] = {
    "research": {"min_actions": 1, "expects_artifacts": True, "expected_tools": {"web_search", "web_fetch", "browser_navigate"}},
    "plan": {"min_actions": 1, "expects_artifacts": True, "expected_tools": {"write_file"}},
    "build": {"min_actions": 1, "expects_artifacts": True, "expected_tools": {"write_file", "build_project"}},
    "test": {"min_actions": 1, "expects_results": True, "expected_tools": {"run_tests"}},
    "repair": {"min_actions": 1, "expects_artifacts": True, "expected_tools": {"edit_file", "write_file"}},
    "retest": {"min_actions": 1, "expects_results": True, "expected_tools": {"run_tests"}},
    "deliver": {"min_actions": 1, "expects_artifacts": True, "expected_tools": {"send_email", "write_file"}},
}


def create_context(
    phases: list[str] | None = None,
    objective: str = "",
) -> dict[str, Any]:
    """Create a new execution context for the Long-Horizon FSM."""
    resolved_phases = phases if phases is not None else list(DEFAULT_PHASES)
    return {
        "phases": resolved_phases,
        "current_phase_index": 0,
        "completed_phases": [],
        "remaining_phases": list(resolved_phases),
        "retry_count": 0,
        "validation_failures": 0,
        "replan_count": 0,
        "current_objective": objective,
        "artifacts": {},
        "artifact_count": 0,
        "execution_history": [],
        "phase_results": {},
        "validation_results": {},
        "last_tool": "",
        "same_tool_count": 0,
        "same_phase_count": 0,
        "same_state_count": 0,
        "last_state_time": 0.0,
        "start_time": 0.0,
    }


# ── Long-Horizon Execution State Machine ───────────────────────

class LongHorizonFSM:
    """Deterministic state machine for multi-phase workflow execution.

    Tracks current state, phase progression, action counts, and auto-transitions.
    The LLM executes work inside EXECUTE_PHASE; the FSM owns all progression
    decisions.
    """

    def __init__(self, ctx: dict[str, Any] | None = None):
        self.state: ExecutionState = ExecutionState.START
        self.previous_state: ExecutionState | None = None
        self.actions_in_state: int = 0
        self.total_actions: int = 0
        self.transitions: list[dict[str, Any]] = []
        self.forced_transitions: int = 0
        self.loops_prevented: int = 0
        self.timeouts: int = 0
        self.recoveries: int = 0
        self.replans: int = 0
        self.validation_failures: int = 0
        self.retries: int = 0
        self.history: list[dict[str, Any]] = []
        self.state_entry_time: float = time.time()
        self.last_state_transition_time: float = time.time()
        self.consecutive_same_tool: int = 0
        self.last_tool_name: str = ""
        self.consecutive_same_state: int = 0
        self.consecutive_same_state_start: float = time.time()
        self.ctx: dict[str, Any] = ctx if ctx is not None else create_context()

    def get_def(self) -> dict[str, Any]:
        """Get the definition for the current state."""
        return STATE_DEFS.get(self.state, STATE_DEFS[ExecutionState.FAIL])

    def is_terminal(self) -> bool:
        """Check if FSM is in a terminal state."""
        return self.state in (ExecutionState.COMPLETE, ExecutionState.FAIL)

    def is_tool_allowed(self, tool_name: str) -> bool:
        """Check if a tool is allowed in the current state."""
        if self.is_terminal():
            return False
        allowed = self.get_def().get("allowed_tools", set())
        return tool_name in allowed

    def is_exit_tool(self, tool_name: str) -> bool:
        """Check if a tool triggers an exit transition."""
        return tool_name in self.get_def().get("exit_tools", set())

    def get_current_phase(self) -> str | None:
        """Get the current phase name, or None if all phases complete."""
        idx = self.ctx["current_phase_index"]
        phases = self.ctx["phases"]
        if idx < len(phases):
            return phases[idx]
        return None

    def record_action(self, tool_name: str, result: dict | None = None) -> None:
        """Record a tool action and update state tracking."""
        now = time.time()

        # Auto-transition: START -> PLAN on first write_file
        if self.state == ExecutionState.START and tool_name in ("write_file", "read_file"):
            self.transition_to(ExecutionState.PLAN)

        self.actions_in_state += 1
        self.total_actions += 1
        self.history.append({
            "tool": tool_name,
            "state": self.state.value,
            "phase": self.get_current_phase(),
            "time": now,
            "result": "success" if result and not result.get("error") else "error" if result else "unknown",
        })

        # Track consecutive same tool
        if tool_name == self.last_tool_name:
            self.consecutive_same_tool += 1
        else:
            self.consecutive_same_tool = 1
            self.last_tool_name = tool_name

        # Track consecutive same state
        self.consecutive_same_state += 1
        self.last_state_transition_time = now

        # Track tool in execution history
        phase = self.get_current_phase()
        if phase:
            self.ctx["execution_history"].append({
                "tool": tool_name,
                "phase": phase,
                "state": self.state.value,
                "time": now,
            })

    def record_artifact(self, name: str, artifact_type: str = "file") -> None:
        """Record an artifact produced during execution."""
        self.ctx["artifacts"][name] = {
            "type": artifact_type,
            "phase": self.get_current_phase(),
            "time": time.time(),
        }
        self.ctx["artifact_count"] = len(self.ctx["artifacts"])

    def check_loop(self) -> tuple[bool, str]:
        """Detect looping conditions.

        Returns (is_looping, reason) tuple.
        """
        # Same tool 3+ consecutive times (matches BrowserFSM threshold)
        if self.consecutive_same_tool >= 3:
            self.loops_prevented += 1
            return True, f"same_tool:{self.last_tool_name}x{self.consecutive_same_tool}"

        # Same phase repeated (no advancement)
        phase = self.get_current_phase()
        if phase:
            completed = self.ctx["completed_phases"]
            if completed and completed[-1] == phase:
                self.ctx["same_phase_count"] += 1
                if self.ctx["same_phase_count"] >= 3:
                    self.loops_prevented += 1
                    return True, f"same_phase:{phase}x{self.ctx['same_phase_count']}"

        # Same state without transition
        if self.consecutive_same_state >= 8:
            self.loops_prevented += 1
            return True, f"same_state:{self.state.value}x{self.consecutive_same_state}"

        # No artifact progress
        if self.state == ExecutionState.EXECUTE_PHASE and self.actions_in_state >= 8:
            if self.ctx["artifact_count"] == 0:
                self.loops_prevented += 1
                return True, "no_artifact_progress"

        return False, ""

    def check_stall(self, stall_timeout: float = 30.0) -> bool:
        """Check if FSM has stalled without state transitions."""
        if self.is_terminal():
            return False
        elapsed = time.time() - self.last_state_transition_time
        if elapsed >= stall_timeout and self.actions_in_state == 0:
            self.timeouts += 1
            return True
        return False

    def check_timeout(self) -> bool:
        """Check if max actions exceeded for current state.
        Terminal states (COMPLETE, FAIL) never timeout.
        """
        if self.is_terminal():
            return False
        max_actions = self.get_def().get("max_actions", 10)
        if self.actions_in_state >= max_actions:
            self.timeouts += 1
            return True
        return False

    def transition_to(self, new_state: ExecutionState, forced: bool = False) -> None:
        """Transition to a new state and reset action counter."""
        if new_state == self.state:
            return
        now = time.time()
        self.transitions.append({
            "from": self.state.value,
            "to": new_state.value,
            "forced": forced,
            "time": now,
            "actions_in_state": self.actions_in_state,
            "phase": self.get_current_phase(),
        })
        self.previous_state = self.state
        self.state = new_state
        self.actions_in_state = 0
        self.consecutive_same_tool = 0
        self.last_tool_name = ""
        self.consecutive_same_state = 0
        self.state_entry_time = now
        self.last_state_transition_time = now
        if forced:
            self.forced_transitions += 1
        logger.debug("LHF: %s -> %s%s", self.previous_state.value, new_state.value,
                     " (forced)" if forced else "")

    def handle_exit_tool(self, tool_name: str) -> ExecutionState | None:
        """Handle exit tool execution — returns target state if auto-transition applies."""
        if not self.is_exit_tool(tool_name):
            return None
        on_exit = self.get_def().get("on_exit")
        if on_exit:
            self.transition_to(on_exit)
            return on_exit
        return None

    def handle_timeout(self) -> ExecutionState | None:
        """Handle state timeout — returns fallback state, or None if terminal."""
        if self.is_terminal():
            return None
        on_timeout = self.get_def().get("on_timeout", ExecutionState.FAIL)
        if on_timeout is None:
            return None
        self.transition_to(on_timeout, forced=True)
        return on_timeout

    def handle_loop(self) -> ExecutionState | None:
        """Handle loop detection — returns target state for auto-advancement or FAIL if exhausted."""
        is_looping, reason = self.check_loop()
        if not is_looping:
            return None

        logger.info("LHF loop detected: %s (state=%s phase=%s)", reason, self.state.value, self.get_current_phase())

        if self.state == ExecutionState.EXECUTE_PHASE:
            self.transition_to(ExecutionState.VALIDATE, forced=True)
            return ExecutionState.VALIDATE
        if self.state == ExecutionState.PLAN:
            self.transition_to(ExecutionState.PREPARE, forced=True)
            return ExecutionState.PREPARE
        if self.state == ExecutionState.VALIDATE:
            # Skip to next phase on validation loop
            self.advance_phase()
            return None
        if self.state in (ExecutionState.RECOVER, ExecutionState.REPLAN):
            self.transition_to(ExecutionState.FAIL, forced=True)
            return ExecutionState.FAIL

        self.transition_to(ExecutionState.ADVANCE, forced=True)
        return ExecutionState.ADVANCE

    def advance_phase(self) -> str | None:
        """Advance to the next phase. Returns the new phase name or None if complete."""
        phase = self.get_current_phase()
        if phase:
            self.ctx["completed_phases"].append(phase)
            self.ctx["remaining_phases"] = [
                p for p in self.ctx["phases"]
                if p not in self.ctx["completed_phases"]
            ]
        self.ctx["current_phase_index"] += 1
        self.ctx["same_phase_count"] = 0

        next_phase = self.get_current_phase()
        if next_phase:
            self.transition_to(ExecutionState.EXECUTE_PHASE)
        else:
            self.transition_to(ExecutionState.COMPLETE)
        return next_phase

    def validate_phase(self, phase: str, tool_results: list[dict] | None = None) -> dict[str, Any]:
        """Validate phase completion criteria. Returns validation result dict."""
        validation_criteria = PHASE_VALIDATION.get(phase, {})
        tools_used = [h["tool"] for h in self.ctx["execution_history"] if h.get("phase") == phase]
        result = {
            "phase": phase,
            "valid": True,
            "checks": [],
            "failures": [],
        }

        # Check min actions
        min_actions = validation_criteria.get("min_actions", 0)
        if len(tools_used) < min_actions:
            result["valid"] = False
            result["failures"].append(f"min_actions: expected >= {min_actions}, got {len(tools_used)}")

        # Check expected tools
        expected = validation_criteria.get("expected_tools", set())
        if expected:
            found = set(tools_used) & expected
            if not found:
                result["valid"] = False
                result["failures"].append(f"expected_tools: none of {expected} found in {set(tools_used)}")

        # Check artifacts expected
        if validation_criteria.get("expects_artifacts") and self.ctx["artifact_count"] == 0:
            result["valid"] = False
            result["failures"].append("expects_artifacts: no artifacts recorded")

        # Check results expected
        if validation_criteria.get("expects_results"):
            has_result = any(
                h.get("result") != "error"
                for h in self.ctx["execution_history"]
                if h.get("phase") == phase
            )
            if not has_result:
                result["valid"] = False
                result["failures"].append("expects_results: no successful results found")

        self.ctx["validation_results"][phase] = result
        if not result["valid"]:
            self.validation_failures += 1
            self.ctx["validation_failures"] += 1

        return result

    def check_completion(self) -> bool:
        """Check if all phases are complete."""
        return len(self.ctx["completed_phases"]) >= len(self.ctx["phases"])

    def fraction_complete(self) -> float:
        """Return fraction of phases completed (0.0 to 1.0)."""
        if not self.ctx["phases"]:
            return 1.0
        return len(self.ctx["completed_phases"]) / len(self.ctx["phases"])

    def get_prompt(self) -> str:
        """Get the guidance prompt for the current state."""
        defn = self.get_def()
        phase = self.get_current_phase()
        base = defn.get("prompt", "")
        if phase and self.state == ExecutionState.EXECUTE_PHASE:
            phase_prompt = PHASE_DEFS.get(phase, {}).get("prompt", "")
            return f"{base} Current phase: {phase}. {phase_prompt}"
        return base

    def get_metrics(self) -> dict[str, Any]:
        """Get FSM metrics for benchmarking."""
        return {
            "fsm_final_state": self.state.value,
            "fsm_transitions": len(self.transitions),
            "fsm_forced_transitions": self.forced_transitions,
            "fsm_loops_prevented": self.loops_prevented,
            "fsm_timeouts": self.timeouts,
            "fsm_recoveries": self.recoveries,
            "fsm_replans": self.replans,
            "fsm_validation_failures": self.validation_failures,
            "fsm_retries": self.retries,
            "fsm_total_actions": self.total_actions,
            "fsm_phases_completed": len(self.ctx["completed_phases"]),
            "fsm_phases_total": len(self.ctx["phases"]),
            "fsm_fraction_complete": self.fraction_complete(),
            "fsm_transition_log": self.transitions[-20:] if self.transitions else [],
        }

    def to_context_dict(self) -> dict[str, Any]:
        """Serialize FSM state into a context dict for persistence."""
        return {
            "fsm_state": self.state.value,
            "fsm_previous_state": self.previous_state.value if self.previous_state else None,
            "fsm_actions_in_state": self.actions_in_state,
            "fsm_total_actions": self.total_actions,
            "fsm_transitions": self.transitions,
            "fsm_forced_transitions": self.forced_transitions,
            "fsm_loops_prevented": self.loops_prevented,
            "fsm_timeouts": self.timeouts,
            "fsm_recoveries": self.recoveries,
            "fsm_replans": self.replans,
            "fsm_validation_failures": self.validation_failures,
            "fsm_retries": self.retries,
            "fsm_consecutive_same_tool": self.consecutive_same_tool,
            "fsm_last_tool_name": self.last_tool_name,
            "fsm_consecutive_same_state": self.consecutive_same_state,
            "fsm_state_entry_time": self.state_entry_time,
            "fsm_last_state_transition_time": self.last_state_transition_time,
            "ctx": self.ctx,
        }

    @classmethod
    def from_context_dict(cls, data: dict[str, Any]) -> LongHorizonFSM:
        """Restore FSM from a previously serialized context dict."""
        fsm = cls(ctx=data.get("ctx", create_context()))
        fsm.state = ExecutionState(data.get("fsm_state", "START"))
        prev = data.get("fsm_previous_state")
        if prev:
            fsm.previous_state = ExecutionState(prev)
        fsm.actions_in_state = data.get("fsm_actions_in_state", 0)
        fsm.total_actions = data.get("fsm_total_actions", 0)
        fsm.transitions = data.get("fsm_transitions", [])
        fsm.forced_transitions = data.get("fsm_forced_transitions", 0)
        fsm.loops_prevented = data.get("fsm_loops_prevented", 0)
        fsm.timeouts = data.get("fsm_timeouts", 0)
        fsm.recoveries = data.get("fsm_recoveries", 0)
        fsm.replans = data.get("fsm_replans", 0)
        fsm.validation_failures = data.get("fsm_validation_failures", 0)
        fsm.retries = data.get("fsm_retries", 0)
        fsm.consecutive_same_tool = data.get("fsm_consecutive_same_tool", 0)
        fsm.last_tool_name = data.get("fsm_last_tool_name", "")
        fsm.consecutive_same_state = data.get("fsm_consecutive_same_state", 0)
        fsm.state_entry_time = data.get("fsm_state_entry_time", time.time())
        fsm.last_state_transition_time = data.get("fsm_last_state_transition_time", time.time())
        return fsm
