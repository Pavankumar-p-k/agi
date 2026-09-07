"""Tests for Long-Horizon Execution State Machine."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import time
from core.workflow.long_horizon_fsm import (
    LongHorizonFSM,
    ExecutionState,
    create_context,
    STATE_DEFS,
    DEFAULT_PHASES,
    PHASE_VALIDATION,
)


def test_initial_state():
    fsm = LongHorizonFSM()
    assert fsm.state == ExecutionState.START
    assert fsm.get_current_phase() == "research"
    assert not fsm.is_terminal()
    assert fsm.fraction_complete() == 0.0


def test_custom_phases():
    phases = ["build", "test", "deliver"]
    fsm = LongHorizonFSM(ctx=create_context(phases=phases))
    assert fsm.get_current_phase() == "build"
    assert fsm.fraction_complete() == 0.0


def test_terminal_states():
    fsm = LongHorizonFSM()
    fsm.state = ExecutionState.COMPLETE
    assert fsm.is_terminal()
    fsm.state = ExecutionState.FAIL
    assert fsm.is_terminal()


def test_is_tool_allowed():
    fsm = LongHorizonFSM()
    assert not fsm.is_tool_allowed("browser_navigate")  # START only allows read/write
    assert fsm.is_tool_allowed("read_file")
    assert fsm.is_tool_allowed("write_file")

    fsm.transition_to(ExecutionState.EXECUTE_PHASE)
    assert fsm.is_tool_allowed("build_project")
    assert fsm.is_tool_allowed("browser_navigate")
    assert fsm.is_tool_allowed("read_file")

    fsm.transition_to(ExecutionState.COMPLETE)
    assert not fsm.is_tool_allowed("build_project")


def test_is_exit_tool():
    fsm = LongHorizonFSM()
    fsm.transition_to(ExecutionState.EXECUTE_PHASE)
    assert fsm.is_exit_tool("build_project")
    assert fsm.is_exit_tool("run_tests")
    assert not fsm.is_exit_tool("read_file")


def test_record_action_tracks_same_tool():
    fsm = LongHorizonFSM()
    fsm.transition_to(ExecutionState.EXECUTE_PHASE)
    fsm.record_action("build_project")
    assert fsm.consecutive_same_tool == 1
    assert fsm.last_tool_name == "build_project"
    fsm.record_action("build_project")
    assert fsm.consecutive_same_tool == 2
    fsm.record_action("read_file")
    assert fsm.consecutive_same_tool == 1
    assert fsm.last_tool_name == "read_file"


def test_record_action_auto_transition_start():
    fsm = LongHorizonFSM()
    assert fsm.state == ExecutionState.START
    fsm.record_action("write_file")
    assert fsm.state == ExecutionState.PLAN


def test_check_loop_same_tool():
    fsm = LongHorizonFSM()
    fsm.transition_to(ExecutionState.EXECUTE_PHASE)
    fsm.record_action("build_project")
    fsm.record_action("build_project")
    fsm.record_action("build_project")
    is_loop, reason = fsm.check_loop()
    assert is_loop
    assert "same_tool" in reason


def test_check_loop_no_loop():
    fsm = LongHorizonFSM()
    fsm.transition_to(ExecutionState.EXECUTE_PHASE)
    fsm.record_action("build_project")
    fsm.record_action("read_file")
    fsm.record_action("run_tests")
    is_loop, _ = fsm.check_loop()
    assert not is_loop


def test_check_loop_same_state():
    fsm = LongHorizonFSM()
    fsm.transition_to(ExecutionState.EXECUTE_PHASE)
    # Use distinct tools to avoid same_tool trigger
    for i in range(9):
        fsm.record_action(f"read_file_{i}")
    is_loop, reason = fsm.check_loop()
    assert is_loop
    assert "same_state" in reason


def test_check_loop_no_artifact_progress():
    fsm = LongHorizonFSM()
    fsm.transition_to(ExecutionState.EXECUTE_PHASE)
    fsm.last_tool_name = "read_file"
    fsm.consecutive_same_tool = 2  # Below same_tool threshold
    fsm.actions_in_state = 8
    is_loop, reason = fsm.check_loop()
    assert is_loop
    assert "no_artifact" in reason


def test_check_loop_no_artifact_prevents_when_artifact_exists():
    fsm = LongHorizonFSM()
    fsm.transition_to(ExecutionState.EXECUTE_PHASE)
    fsm.record_artifact("main.py")
    fsm.actions_in_state = 8
    fsm.consecutive_same_state = 3  # Below same_state threshold
    is_loop, reason = fsm.check_loop()
    assert not is_loop, f"Should not loop when artifacts exist: {reason}"


def test_check_timeout():
    fsm = LongHorizonFSM()
    fsm.transition_to(ExecutionState.PLAN)
    for _ in range(6):  # max_actions=5 for PLAN
        fsm.record_action("write_file")
    assert fsm.check_timeout()
    assert fsm.timeouts == 1


def test_check_timeout_by_state():
    """Test timeout via handle_timeout for PLAN state (on_timeout -> REPLAN)."""
    fsm = LongHorizonFSM()
    fsm.transition_to(ExecutionState.PLAN)
    for _ in range(6):
        fsm.record_action("write_file")
    result = fsm.handle_timeout()
    assert result == ExecutionState.REPLAN
    assert fsm.forced_transitions > 0


def test_check_timeout_terminal():
    fsm = LongHorizonFSM()
    fsm.transition_to(ExecutionState.COMPLETE)
    assert not fsm.check_timeout()
    fsm.transition_to(ExecutionState.FAIL)
    assert not fsm.check_timeout()


def test_check_timeout_not_reached():
    fsm = LongHorizonFSM()
    fsm.transition_to(ExecutionState.PLAN)
    fsm.record_action("write_file")
    assert not fsm.check_timeout()


def test_check_stall():
    fsm = LongHorizonFSM()
    fsm.last_state_transition_time = time.time() - 60
    assert fsm.check_stall(stall_timeout=30)


def test_check_stall_recent():
    fsm = LongHorizonFSM()
    fsm.last_state_transition_time = time.time() - 5
    assert not fsm.check_stall(stall_timeout=30)


def test_transition_to():
    fsm = LongHorizonFSM()
    fsm.transition_to(ExecutionState.PLAN)
    assert fsm.state == ExecutionState.PLAN
    assert fsm.actions_in_state == 0
    assert len(fsm.transitions) == 1
    assert fsm.transitions[0]["from"] == "START"
    assert fsm.transitions[0]["to"] == "PLAN"
    assert not fsm.transitions[0]["forced"]


def test_transition_to_forced():
    fsm = LongHorizonFSM()
    fsm.transition_to(ExecutionState.PLAN, forced=True)
    assert fsm.forced_transitions == 1
    assert fsm.transitions[0]["forced"]


def test_transition_to_self():
    fsm = LongHorizonFSM()
    fsm.transition_to(ExecutionState.START)
    assert len(fsm.transitions) == 0  # no transition logged


def test_handle_exit_tool():
    fsm = LongHorizonFSM()
    fsm.transition_to(ExecutionState.PLAN)
    result = fsm.handle_exit_tool("write_file")
    assert result == ExecutionState.PREPARE
    assert fsm.state == ExecutionState.PREPARE


def test_handle_exit_tool_no_match():
    fsm = LongHorizonFSM()
    fsm.transition_to(ExecutionState.PLAN)
    result = fsm.handle_exit_tool("read_file")
    assert result is None
    assert fsm.state == ExecutionState.PLAN


def test_handle_timeout():
    fsm = LongHorizonFSM()
    fsm.transition_to(ExecutionState.PLAN)
    # Force actions past max to trigger timeout
    for _ in range(6):
        fsm.record_action("write_file")
    result = fsm.handle_timeout()
    assert result == ExecutionState.REPLAN  # PLAN on_timeout -> REPLAN
    assert fsm.forced_transitions > 0


def test_handle_timeout_terminal():
    fsm = LongHorizonFSM()
    fsm.state = ExecutionState.COMPLETE
    assert fsm.handle_timeout() is None


def test_handle_loop_execute_phase():
    fsm = LongHorizonFSM()
    fsm.transition_to(ExecutionState.EXECUTE_PHASE)
    fsm.last_tool_name = "build_project"
    fsm.consecutive_same_tool = 3
    result = fsm.handle_loop()
    assert result == ExecutionState.VALIDATE
    assert fsm.state == ExecutionState.VALIDATE
    assert fsm.loops_prevented > 0


def test_handle_loop_plan():
    fsm = LongHorizonFSM()
    fsm.transition_to(ExecutionState.PLAN)
    fsm.last_tool_name = "write_file"
    fsm.consecutive_same_tool = 3
    result = fsm.handle_loop()
    assert result == ExecutionState.PREPARE
    assert fsm.state == ExecutionState.PREPARE


def test_handle_loop_no_loop():
    fsm = LongHorizonFSM()
    fsm.transition_to(ExecutionState.EXECUTE_PHASE)
    fsm.record_action("build_project")
    result = fsm.handle_loop()
    assert result is None


def test_advance_phase_to_next():
    fsm = LongHorizonFSM(ctx=create_context(phases=["build", "test", "deliver"]))
    assert fsm.get_current_phase() == "build"
    next_phase = fsm.advance_phase()
    assert next_phase == "test"
    assert fsm.get_current_phase() == "test"
    assert "build" in fsm.ctx["completed_phases"]


def test_advance_phase_to_complete():
    fsm = LongHorizonFSM(ctx=create_context(phases=["build"]))
    assert fsm.get_current_phase() == "build"
    next_phase = fsm.advance_phase()
    assert next_phase is None
    assert fsm.state == ExecutionState.COMPLETE


def test_advance_phase_completed_list():
    fsm = LongHorizonFSM(ctx=create_context(phases=["build", "test"]))
    fsm.advance_phase()
    assert fsm.ctx["completed_phases"] == ["build"]
    assert fsm.ctx["remaining_phases"] == ["test"]


def test_validate_phase_min_actions():
    fsm = LongHorizonFSM(ctx=create_context(phases=["build"]))
    # No actions recorded for build phase
    result = fsm.validate_phase("build")
    assert not result["valid"]
    assert any("min_actions" in f for f in result["failures"])


def test_validate_phase_expected_tools():
    fsm = LongHorizonFSM(ctx=create_context(phases=["build"]))
    fsm.record_action("write_file")
    fsm.record_artifact("main.py")
    result = fsm.validate_phase("build")
    assert result["valid"]
    assert len(result["failures"]) == 0


def test_validate_phase_no_artifacts():
    """Build expects artifacts; validating without artifacts should fail."""
    fsm = LongHorizonFSM(ctx=create_context(phases=["build"]))
    fsm.record_action("build_project")
    result = fsm.validate_phase("build")
    assert not result["valid"]
    assert any("artifacts" in f for f in result["failures"])


def test_validate_phase_research():
    fsm = LongHorizonFSM(ctx=create_context(phases=["research"]))
    # No research tools used
    result = fsm.validate_phase("research")
    assert not result["valid"]


def test_validate_phase_research_success():
    fsm = LongHorizonFSM(ctx=create_context(phases=["research"]))
    fsm.record_action("web_search")
    fsm.record_artifact("research_notes.md")
    result = fsm.validate_phase("research")
    assert result["valid"]


def test_validate_phase_artifacts():
    fsm = LongHorizonFSM(ctx=create_context(phases=["build"]))
    fsm.record_action("build_project")
    # No artifacts recorded but build expects artifacts
    result = fsm.validate_phase("build")
    assert not result["valid"]
    assert any("artifacts" in f for f in result["failures"])


def test_validate_phase_artifacts_success():
    fsm = LongHorizonFSM(ctx=create_context(phases=["build"]))
    fsm.record_action("build_project")
    fsm.record_artifact("output.apk")
    result = fsm.validate_phase("build")
    assert result["valid"]


def test_validate_phase_results():
    fsm = LongHorizonFSM(ctx=create_context(phases=["test"]))
    fsm.record_action("run_tests", {"success": True})
    result = fsm.validate_phase("test")
    assert result["valid"]


def test_validation_failure_tracked():
    fsm = LongHorizonFSM(ctx=create_context(phases=["build"]))
    fsm.validate_phase("build")
    assert fsm.validation_failures == 1
    assert fsm.ctx["validation_failures"] == 1


def test_check_completion():
    fsm = LongHorizonFSM(ctx=create_context(phases=["build"]))
    assert not fsm.check_completion()
    fsm.advance_phase()
    assert fsm.check_completion()


def test_fraction_complete():
    fsm = LongHorizonFSM(ctx=create_context(phases=["build", "test", "deliver"]))
    assert fsm.fraction_complete() == 0.0
    fsm.advance_phase()
    assert fsm.fraction_complete() == 1/3
    fsm.advance_phase()
    assert fsm.fraction_complete() == 2/3
    fsm.advance_phase()
    assert fsm.fraction_complete() == 1.0


def test_fraction_complete_empty():
    fsm = LongHorizonFSM(ctx=create_context(phases=[]))
    assert fsm.fraction_complete() == 1.0


def test_record_artifact():
    fsm = LongHorizonFSM(ctx=create_context(phases=["build"]))
    fsm.record_artifact("main.py")
    assert "main.py" in fsm.ctx["artifacts"]
    assert fsm.ctx["artifact_count"] == 1


def test_multiple_artifacts():
    fsm = LongHorizonFSM(ctx=create_context(phases=["build"]))
    fsm.record_artifact("main.py")
    fsm.record_artifact("test_main.py")
    assert fsm.ctx["artifact_count"] == 2


def test_get_prompt_start():
    fsm = LongHorizonFSM()
    prompt = fsm.get_prompt()
    assert "Starting" in prompt


def test_get_prompt_execute_phase():
    fsm = LongHorizonFSM()
    fsm.transition_to(ExecutionState.EXECUTE_PHASE)
    prompt = fsm.get_prompt()
    assert "Executing" in prompt
    assert "research" in prompt.lower()


def test_get_prompt_complete():
    fsm = LongHorizonFSM()
    fsm.transition_to(ExecutionState.COMPLETE)
    assert "complete" in fsm.get_prompt().lower()


def test_get_prompt_fail():
    fsm = LongHorizonFSM()
    fsm.transition_to(ExecutionState.FAIL)
    assert "failed" in fsm.get_prompt().lower()


def test_get_metrics():
    fsm = LongHorizonFSM(ctx=create_context(phases=["build", "test"]))
    fsm.transition_to(ExecutionState.EXECUTE_PHASE, forced=False)
    fsm.record_action("build_project")
    fsm.record_artifact("output.apk")
    metrics = fsm.get_metrics()
    assert metrics["fsm_final_state"] == ExecutionState.EXECUTE_PHASE.value
    assert metrics["fsm_total_actions"] == 1
    assert metrics["fsm_transitions"] == 1
    assert metrics["fsm_phases_total"] == 2
    assert metrics["fsm_fraction_complete"] == 0.0


def test_forced_transition_increments():
    fsm = LongHorizonFSM()
    fsm.transition_to(ExecutionState.PLAN, forced=True)
    fsm.transition_to(ExecutionState.PREPARE, forced=True)
    assert fsm.forced_transitions == 2


def test_loops_prevented_increments():
    fsm = LongHorizonFSM()
    fsm.transition_to(ExecutionState.EXECUTE_PHASE)
    fsm.last_tool_name = "build_project"
    fsm.consecutive_same_tool = 3
    fsm.handle_loop()
    assert fsm.loops_prevented >= 1


def test_handle_loop_recover_replan_leads_to_fail():
    fsm = LongHorizonFSM()
    fsm.transition_to(ExecutionState.RECOVER)
    fsm.last_tool_name = "write_file"
    fsm.consecutive_same_tool = 3
    result = fsm.handle_loop()
    assert result == ExecutionState.FAIL
    assert fsm.state == ExecutionState.FAIL


def test_handle_loop_replan():
    fsm = LongHorizonFSM()
    fsm.transition_to(ExecutionState.REPLAN)
    fsm.last_tool_name = "write_file"
    fsm.consecutive_same_tool = 3
    result = fsm.handle_loop()
    assert result == ExecutionState.FAIL


def test_to_from_context_dict_roundtrip():
    fsm = LongHorizonFSM(ctx=create_context(phases=["build", "test", "deliver"]))
    fsm.transition_to(ExecutionState.EXECUTE_PHASE, forced=False)
    fsm.record_action("build_project")
    fsm.record_action("build_project")
    fsm.record_artifact("output.apk")

    data = fsm.to_context_dict()
    restored = LongHorizonFSM.from_context_dict(data)

    assert restored.state == fsm.state
    assert restored.ctx["phases"] == fsm.ctx["phases"]
    assert restored.ctx["artifact_count"] == 1
    assert restored.total_actions == 2
    assert restored.last_tool_name == "build_project"
    assert restored.consecutive_same_tool == 2


def test_from_context_dict_minimal():
    data = {"fsm_state": "START", "ctx": create_context()}
    restored = LongHorizonFSM.from_context_dict(data)
    assert restored.state == ExecutionState.START
    assert restored.total_actions == 0
    assert restored.get_current_phase() == "research"


def test_state_defs_are_consistent():
    """Every state must have a definition."""
    for state in ExecutionState:
        assert state in STATE_DEFS, f"Missing definition for {state}"
        defn = STATE_DEFS[state]
        assert "allowed_tools" in defn
        assert "exit_tools" in defn
        assert "max_actions" in defn
        assert "on_exit" in defn
        assert "on_timeout" in defn
        assert "prompt" in defn


def test_all_phases_have_validation():
    """Every default phase must have validation criteria."""
    for phase in DEFAULT_PHASES:
        assert phase in PHASE_VALIDATION, f"Missing validation for phase {phase}"


def test_execute_phase_allows_all_major_tools():
    defn = STATE_DEFS[ExecutionState.EXECUTE_PHASE]
    allowed = defn["allowed_tools"]
    for tool in ("build_project", "run_tests", "write_file", "read_file",
                  "edit_file", "bash", "python", "web_search"):
        assert tool in allowed, f"EXECUTE_PHASE should allow {tool}"


def test_start_to_plan_flow():
    """Full flow: START -> record -> PLAN."""
    fsm = LongHorizonFSM()
    fsm.record_action("write_file")
    assert fsm.state == ExecutionState.PLAN


def test_plan_to_prepare_flow():
    """Full flow: START -> PLAN -> exit -> PREPARE."""
    fsm = LongHorizonFSM()
    fsm.record_action("write_file")  # START -> PLAN
    assert fsm.state == ExecutionState.PLAN
    fsm.handle_exit_tool("write_file")  # PLAN -> PREPARE
    assert fsm.state == ExecutionState.PREPARE


def test_execute_to_validate_flow():
    """Full flow: EXECUTE_PHASE -> exit -> VALIDATE."""
    fsm = LongHorizonFSM()
    fsm.transition_to(ExecutionState.EXECUTE_PHASE)
    fsm.handle_exit_tool("build_project")
    assert fsm.state == ExecutionState.VALIDATE


def test_validate_to_advance_flow():
    """Full flow: VALIDATE -> exit -> ADVANCE."""
    fsm = LongHorizonFSM()
    fsm.transition_to(ExecutionState.VALIDATE)
    fsm.handle_exit_tool("run_tests")
    assert fsm.state == ExecutionState.ADVANCE


def test_validate_failure_leads_to_replan():
    """On validation failure, VALIDATE on_timeout -> RECOVER, not ADVANCE."""
    # The VALIDATE state on_timeout triggers RECOVER
    defn = STATE_DEFS[ExecutionState.VALIDATE]
    assert defn["on_timeout"] == ExecutionState.RECOVER


def test_replan_timeout_leads_to_fail():
    defn = STATE_DEFS[ExecutionState.REPLAN]
    assert defn["on_timeout"] == ExecutionState.FAIL


def test_recovery_loop_leads_to_fail():
    fsm = LongHorizonFSM()
    fsm.transition_to(ExecutionState.RECOVER)
    fsm.last_tool_name = "write_file"
    fsm.consecutive_same_tool = 3
    result = fsm.handle_loop()
    assert result == ExecutionState.FAIL


def test_validate_phase_tracks_validation_failures():
    fsm = LongHorizonFSM(ctx=create_context(phases=["build"]))
    fsm.validate_phase("build")
    assert fsm.validation_failures == 1
    fsm.validate_phase("build")
    assert fsm.validation_failures == 2


def test_artifacts_persist_across_advance():
    fsm = LongHorizonFSM(ctx=create_context(phases=["build", "test"]))
    fsm.record_artifact("main.py")
    fsm.advance_phase()
    assert "main.py" in fsm.ctx["artifacts"]
    assert fsm.ctx["artifact_count"] == 1
    assert fsm.get_current_phase() == "test"


def test_execution_history_tracks_phase():
    fsm = LongHorizonFSM(ctx=create_context(phases=["build"]))
    fsm.transition_to(ExecutionState.EXECUTE_PHASE)
    fsm.record_action("build_project")
    assert len(fsm.ctx["execution_history"]) == 1
    entry = fsm.ctx["execution_history"][0]
    assert entry["tool"] == "build_project"
    assert entry["phase"] == "build"


def test_same_phase_detection():
    fsm = LongHorizonFSM(ctx=create_context(phases=["build", "test"]))
    # Simulate running build twice
    fsm.ctx["completed_phases"].append("build")
    fsm.ctx["completed_phases"].append("build")
    fsm.ctx["same_phase_count"] = 3
    is_loop, reason = fsm.check_loop()
    assert is_loop
    assert "same_phase" in reason


def test_check_loop_no_loop_on_first_action():
    fsm = LongHorizonFSM()
    assert not fsm.check_loop()[0]


def test_initial_retry_count():
    fsm = LongHorizonFSM()
    assert fsm.ctx["retry_count"] == 0


def test_initial_validation_failures():
    fsm = LongHorizonFSM()
    assert fsm.ctx["validation_failures"] == 0


def test_initial_replan_count():
    fsm = LongHorizonFSM()
    assert fsm.ctx["replan_count"] == 0


def test_empty_phases_no_current():
    fsm = LongHorizonFSM(ctx=create_context(phases=[]))
    assert fsm.get_current_phase() is None


def test_complete_is_terminal():
    assert ExecutionState.COMPLETE in (ExecutionState.COMPLETE, ExecutionState.FAIL)
    fsm = LongHorizonFSM()
    fsm.state = ExecutionState.COMPLETE
    assert fsm.is_terminal()


def test_fail_is_terminal():
    fsm = LongHorizonFSM()
    fsm.state = ExecutionState.FAIL
    assert fsm.is_terminal()


def test_validation_results_persisted():
    fsm = LongHorizonFSM(ctx=create_context(phases=["build"]))
    fsm.record_action("build_project")
    fsm.record_artifact("output.apk")
    result = fsm.validate_phase("build")
    cached = fsm.ctx["validation_results"]["build"]
    assert cached == result
    assert cached["valid"]


def test_advance_clears_same_phase_count():
    fsm = LongHorizonFSM(ctx=create_context(phases=["build", "test"]))
    fsm.ctx["same_phase_count"] = 5
    fsm.advance_phase()
    assert fsm.ctx["same_phase_count"] == 0


def test_stall_check_only_in_non_terminal():
    fsm = LongHorizonFSM()
    fsm.state = ExecutionState.COMPLETE
    assert not fsm.check_stall(stall_timeout=1)
    fsm.state = ExecutionState.FAIL
    assert not fsm.check_stall(stall_timeout=1)
