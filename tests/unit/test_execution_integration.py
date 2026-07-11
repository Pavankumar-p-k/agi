import pytest
from unittest.mock import MagicMock, patch, ANY


# ── ExecutionContext tests ──────────────────────────────────────────

class TestExecutionContext:
    def test_advance_creates_new_instance(self):
        from core.execution import ExecutionContext
        ctx = ExecutionContext(workflow_id="wf_1", execution_id="exec_1", status="started")
        ctx2 = ctx.advance("build", "in_progress")
        assert ctx2 is not ctx
        assert ctx2.phase == "build"
        assert ctx2.status == "in_progress"
        assert ctx.status == "started"
        assert ctx.phase == "init"

    def test_advance_copies_metadata(self):
        from core.execution import ExecutionContext
        ctx = ExecutionContext(
            workflow_id="wf_1", execution_id="exec_1",
            source="test", metadata={"key": "val"},
        )
        ctx2 = ctx.advance("plan", "done")
        assert ctx2.metadata["key"] == "val"
        assert ctx2.source == "test"
        assert ctx2.workflow_id == "wf_1"

    def test_to_event_payload(self):
        from core.execution import ExecutionContext
        ctx = ExecutionContext(workflow_id="wf_1", execution_id="exec_1", source="test")
        payload = ctx.to_event_payload()
        assert payload["workflow_id"] == "wf_1"
        assert payload["execution_id"] == "exec_1"
        assert payload["source"] == "test"
        assert payload["phase"] == "init"
        assert payload["status"] == "started"
        assert "timestamp" in payload
        assert "metadata" in payload

    def test_create_context_factory(self):
        from core.execution import ExecutionManager
        ctx = ExecutionManager.create_context(source="factory_test", user_id="u1")
        assert ctx.source == "factory_test"
        assert ctx.user_id == "u1"
        assert ctx.execution_id != ""
        assert ctx.workflow_id == ""
        assert ctx.phase == "init"
        assert ctx.status == "started"


# ── ExecutionManager event tests ────────────────────────────────────

class TestExecutionManagerEvents:
    @pytest.fixture
    def mgr(self):
        from core.execution import ExecutionManager
        m = ExecutionManager()
        m._bus = MagicMock()
        return m

    @pytest.fixture
    def ctx(self):
        from core.execution import ExecutionManager
        return ExecutionManager.create_context(source="test")

    def test_publish_progress_fires_event(self, mgr, ctx):
        mgr.publish_progress(ctx, "test progress", 0.5)
        mgr._bus.publish_sync.assert_called_once()
        event = mgr._bus.publish_sync.call_args[0][0]
        assert "execution.progress" == event.type
        assert event.payload["message"] == "test progress"
        assert event.payload["progress_pct"] == 0.5

    def test_publish_completed_fires_event(self, mgr, ctx):
        mgr.publish_completed(ctx, {"result": "ok"})
        mgr._bus.publish_sync.assert_called_once()
        event = mgr._bus.publish_sync.call_args[0][0]
        assert "execution.completed" == event.type
        assert ctx.status == "completed"

    def test_publish_failed_fires_event(self, mgr, ctx):
        mgr.publish_failed(ctx, "something went wrong")
        mgr._bus.publish_sync.assert_called_once()
        event = mgr._bus.publish_sync.call_args[0][0]
        assert "execution.failed" == event.type
        assert event.payload["error"] == "something went wrong"
        assert ctx.status == "failed"


# ── ExecutionManager memory recording tests ─────────────────────────

class TestExecutionManagerMemory:
    @pytest.fixture
    def mgr(self):
        from core.execution import ExecutionManager
        m = ExecutionManager()
        m._bus = MagicMock()
        return m

    @pytest.fixture
    def ctx(self):
        from core.execution import ExecutionManager
        return ExecutionManager.create_context(
            source="test", user_id="tester", metadata={"run": 1},
        )

    @patch("memory.memory_facade.memory")
    def test_record_trace_calls_facade(self, mock_memory, mgr, ctx):
        ctx.workflow_id = "wf_test"
        mgr.record_trace(ctx, "test_action", "test observation", True,
                         action_params={"cmd": "echo"}, duration_ms=150.0)
        mock_memory.store_trace.assert_called_once_with(
            action_name="test_action",
            action_params={"cmd": "echo"},
            observation="test observation",
            success=True,
            duration_ms=150.0,
            task_id="wf_test",
            context=ctx.to_event_payload(),
            tags=[],
            user_id="tester",
        )

    @patch("memory.memory_facade.memory")
    def test_record_decision_calls_facade(self, mock_memory, mgr, ctx):
        mgr.record_decision(ctx, "deploy_choice", "deployment succeeded", True)
        mock_memory.store_decision.assert_called_once_with(
            context=ctx.phase,
            decision="deploy_choice",
            outcome="deployment succeeded",
            success=True,
            user_id="tester",
        )


# ── ControlLoop integration tests ───────────────────────────────────

class TestControlLoopIntegration:
    def test_control_loop_has_execution_manager(self):
        from core.control_loop import control_loop
        assert hasattr(control_loop, "execution_manager")
        from core.execution import ExecutionManager
        assert isinstance(control_loop.execution_manager, ExecutionManager)

    def test_run_build_publishes_start_event(self):
        """Verify that run_build publishes a progress event on build_started."""
        from core.control_loop import ControlLoop
        loop = ControlLoop(auto_approve=True, autonomous=True)
        loop.execution_manager = MagicMock()
        ctx_mock = MagicMock()
        ctx_mock.advance.return_value = ctx_mock
        loop.execution_manager.create_context.return_value = ctx_mock

        import asyncio
        try:
            asyncio.run(loop.run_build("test goal"))
        except Exception:
            pass

        loop.execution_manager.create_context.assert_called_once()
        loop.execution_manager.publish_progress.assert_any_call(ctx_mock, "build_started")


# ── AutomationLoop integration tests ────────────────────────────────

class TestAutomationLoopIntegration:
    def test_loop_class_has_execution_manager_in_init(self):
        """Verify AutomationLoop.__init__ accepts execution_manager param via AST."""
        import ast
        with open("brain/automation/loop.py") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "AutomationLoop":
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "__init__":
                        args = [a.arg for a in item.args.args]
                        assert "execution_manager" in args, (
                            f"execution_manager not found in AutomationLoop.__init__ args: {args}"
                        )
                        break
                break

    def test_execute_step_references_execution_manager_engine(self):
        """Verify _execute_step body references self.execution_manager.engine."""
        import ast
        with open("brain/automation/loop.py") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "AutomationLoop":
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "_execute_step":
                        with open("brain/automation/loop.py") as sf:
                            source_lines = sf.readlines()
                        start = item.lineno - 1
                        end = item.end_lineno
                        body = "".join(source_lines[start:end])
                        assert "self.execution_manager.engine" in body
                        return
        pytest.fail("_execute_step not found")

    def test_build_project_has_lifecycle_events(self):
        """Verify _build_project publishes lifecycle events via exec_ctx."""
        import ast
        with open("brain/automation/loop.py") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "AutomationLoop":
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "_build_project":
                        with open("brain/automation/loop.py") as sf:
                            source_lines = sf.readlines()
                        start = item.lineno - 1
                        end = item.end_lineno
                        body = "".join(source_lines[start:end])
                        assert "self.execution_manager.create_context" in body
                        assert "self.execution_manager.record_trace" in body
                        assert "self.execution_manager.publish_progress" in body
                        assert "self.execution_manager.publish_completed" in body
                        assert "self.execution_manager.publish_failed" in body
                        assert "self.execution_manager.record_decision" in body
                        return
        pytest.fail("_build_project not found")
