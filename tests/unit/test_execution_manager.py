from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch, ANY

import pytest

from core.execution.context import ExecutionContext
from core.execution.manager import ExecutionManager
from core.workflow.engine import WorkflowEngine
from core.workflow.models import StepDefinition, WorkflowInstance, WorkflowStatus


@pytest.fixture
def mock_engine() -> MagicMock:
    engine = MagicMock(spec=WorkflowEngine)
    engine.start_workflow = AsyncMock()
    engine.cancel_workflow = AsyncMock()
    engine.get_status = AsyncMock()
    engine.resume_workflow = AsyncMock()
    return engine


@pytest.fixture
def mgr(mock_engine: MagicMock) -> ExecutionManager:
    m = ExecutionManager(engine=mock_engine)  # type: ignore[arg-type]
    m._bus = MagicMock()
    return m


@pytest.fixture
def ctx() -> ExecutionContext:
    return ExecutionManager.create_context(source="test", user_id="tester", metadata={"key": "val"})


class TestExecutionManagerEngine:
    def test_engine_property(self, mock_engine: MagicMock):
        m = ExecutionManager(engine=mock_engine)  # type: ignore[arg-type]
        assert m.engine is mock_engine

    def test_default_engine_is_workflow_engine(self):
        m = ExecutionManager()
        assert isinstance(m.engine, WorkflowEngine)


class TestExecutionManagerWorkflowLifecycle:
    """Tests for start_workflow, cancel, resume, get_status."""

    @pytest.mark.asyncio
    async def test_start_workflow_returns_id_and_updates_context(
        self, mgr: ExecutionManager, ctx: ExecutionContext,
    ):
        fake_instance = MagicMock(spec=WorkflowInstance)
        fake_instance.workflow_id = "wf_abc123"
        mgr._engine.start_workflow.return_value = fake_instance  # type: ignore[attr-defined]

        steps = [StepDefinition(tool_name="echo", input_data={"msg": "hi"})]
        wf_id = await mgr.start_workflow("test_flow", steps, ctx)

        assert wf_id == "wf_abc123"
        assert ctx.workflow_id == "wf_abc123"

        mgr._engine.start_workflow.assert_awaited_once_with(
            workflow_type="test_flow",
            steps=steps,
            session_id="tester",
            owner="tester",
            timeout_seconds=None,
            execution_context=ctx.metadata,
            retry_budget=0,
        )

    @pytest.mark.asyncio
    async def test_start_workflow_publishes_event(
        self, mgr: ExecutionManager, ctx: ExecutionContext,
    ):
        fake_instance = MagicMock(spec=WorkflowInstance)
        fake_instance.workflow_id = "wf_evt"
        mgr._engine.start_workflow.return_value = fake_instance  # type: ignore[attr-defined]

        await mgr.start_workflow("test_flow", [StepDefinition(tool_name="echo")], ctx)

        mgr._bus.publish_sync.assert_called_once()
        event = mgr._bus.publish_sync.call_args[0][0]
        assert event.type == "execution.workflow_started"
        assert event.payload["workflow_type"] == "test_flow"
        assert event.payload["step_count"] == 1
        assert event.payload["workflow_id"] == "wf_evt"

    @pytest.mark.asyncio
    async def test_start_workflow_records_trace(
        self, mgr: ExecutionManager, ctx: ExecutionContext,
    ):
        fake_instance = MagicMock(spec=WorkflowInstance)
        fake_instance.workflow_id = "wf_trace"
        mgr._engine.start_workflow.return_value = fake_instance  # type: ignore[attr-defined]

        with patch("memory.memory_facade.memory") as mock_mem:
            await mgr.start_workflow("test_flow", [StepDefinition(tool_name="echo")], ctx)

        mock_mem.store_trace.assert_called_once()
        call_kwargs = mock_mem.store_trace.call_args[1]
        assert call_kwargs["action_name"] == "workflow_start"
        assert call_kwargs["success"] is True
        assert call_kwargs["task_id"] == "wf_trace"

    @pytest.mark.asyncio
    async def test_start_workflow_with_timeout_and_retry(
        self, mgr: ExecutionManager, ctx: ExecutionContext,
    ):
        fake_instance = MagicMock(spec=WorkflowInstance)
        fake_instance.workflow_id = "wf_tmo"
        mgr._engine.start_workflow.return_value = fake_instance  # type: ignore[attr-defined]

        await mgr.start_workflow(
            "critical", [StepDefinition(tool_name="deploy")], ctx,
            timeout_seconds=300, retry_budget=3,
        )
        mgr._engine.start_workflow.assert_awaited_once()
        _, kwargs = mgr._engine.start_workflow.await_args
        assert kwargs["timeout_seconds"] == 300
        assert kwargs["retry_budget"] == 3

    @pytest.mark.asyncio
    async def test_cancel_returns_true_and_publishes_event(
        self, mgr: ExecutionManager, ctx: ExecutionContext,
    ):
        ctx.workflow_id = "wf_cancel"
        mgr._engine.cancel_workflow.return_value = {"status": "cancelled"}  # type: ignore[attr-defined]

        result = await mgr.cancel(ctx)
        assert result is True

        mgr._engine.cancel_workflow.assert_awaited_once_with("wf_cancel")
        mgr._bus.publish_sync.assert_called_once()
        event = mgr._bus.publish_sync.call_args[0][0]
        assert event.type == "execution.workflow_cancelled"

    @pytest.mark.asyncio
    async def test_cancel_returns_false_when_nothing_to_cancel(
        self, mgr: ExecutionManager, ctx: ExecutionContext,
    ):
        ctx.workflow_id = "wf_none"
        mgr._engine.cancel_workflow.return_value = None  # type: ignore[attr-defined]

        result = await mgr.cancel(ctx)
        assert result is False
        mgr._bus.publish_sync.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_status_returns_engine_result(
        self, mgr: ExecutionManager, ctx: ExecutionContext,
    ):
        ctx.workflow_id = "wf_stat"
        expected = {"status": "running", "progress": 0.5}
        mgr._engine.get_status.return_value = expected  # type: ignore[attr-defined]

        result = await mgr.get_status(ctx)
        assert result == expected
        mgr._engine.get_status.assert_awaited_once_with("wf_stat")

    @pytest.mark.asyncio
    async def test_resume_returns_true_and_publishes_event(
        self, mgr: ExecutionManager, ctx: ExecutionContext,
    ):
        ctx.workflow_id = "wf_res"
        mgr._engine.resume_workflow.return_value = {"status": "running"}  # type: ignore[attr-defined]

        result = await mgr.resume(ctx)
        assert result is True

        mgr._engine.resume_workflow.assert_awaited_once_with("wf_res")
        mgr._bus.publish_sync.assert_called_once()
        event = mgr._bus.publish_sync.call_args[0][0]
        assert event.type == "execution.workflow_resumed"

    @pytest.mark.asyncio
    async def test_resume_returns_false_when_nothing_to_resume(
        self, mgr: ExecutionManager, ctx: ExecutionContext,
    ):
        ctx.workflow_id = "wf_no_res"
        mgr._engine.resume_workflow.return_value = None  # type: ignore[attr-defined]

        result = await mgr.resume(ctx)
        assert result is False
        mgr._bus.publish_sync.assert_not_called()


class TestExecutionManagerPublishEdgeCases:
    """Edge cases for publish_progress, publish_completed, publish_failed."""

    def test_publish_progress_without_pct(self, mgr: ExecutionManager, ctx: ExecutionContext):
        mgr.publish_progress(ctx, "just a message")
        mgr._bus.publish_sync.assert_called_once()
        event = mgr._bus.publish_sync.call_args[0][0]
        assert event.payload["message"] == "just a message"
        assert "progress_pct" not in event.payload

    def test_publish_progress_with_zero_pct(self, mgr: ExecutionManager, ctx: ExecutionContext):
        mgr.publish_progress(ctx, "starting", 0.0)
        event = mgr._bus.publish_sync.call_args[0][0]
        assert event.payload["progress_pct"] == 0.0

    def test_publish_completed_sets_context_status(self, mgr: ExecutionManager, ctx: ExecutionContext):
        mgr.publish_completed(ctx)
        assert ctx.status == "completed"

    def test_publish_failed_sets_context_status(self, mgr: ExecutionManager, ctx: ExecutionContext):
        mgr.publish_failed(ctx, "epic fail")
        assert ctx.status == "failed"

    def test_publish_failed_includes_error(self, mgr: ExecutionManager, ctx: ExecutionContext):
        mgr.publish_failed(ctx, "error detail")
        event = mgr._bus.publish_sync.call_args[0][0]
        assert event.payload["error"] == "error detail"


class TestExecutionManagerMemoryEdgeCases:
    """Memory recording fallback when memory module is unavailable."""

    def test_record_trace_does_not_raise_on_memory_failure(
        self, mgr: ExecutionManager, ctx: ExecutionContext,
    ):
        ctx.workflow_id = "wf_mem_fail"
        with patch.dict("sys.modules", {"memory.memory_facade": None}):
            mgr.record_trace(ctx, "action", "observation", True)

    def test_record_decision_does_not_raise_on_memory_failure(
        self, mgr: ExecutionManager, ctx: ExecutionContext,
    ):
        with patch.dict("sys.modules", {"memory.memory_facade": None}):
            mgr.record_decision(ctx, "decision", "outcome", True)

    def test_record_trace_does_not_raise_on_facade_exception(
        self, mgr: ExecutionManager, ctx: ExecutionContext,
    ):
        ctx.workflow_id = "wf_ex"
        with patch("memory.memory_facade.memory") as mock_mem:
            mock_mem.store_trace.side_effect = RuntimeError("db down")
            mgr.record_trace(ctx, "action", "obs", True)
            mock_mem.store_trace.assert_called_once()

    def test_record_decision_does_not_raise_on_facade_exception(
        self, mgr: ExecutionManager, ctx: ExecutionContext,
    ):
        with patch("memory.memory_facade.memory") as mock_mem:
            mock_mem.store_decision.side_effect = RuntimeError("db down")
            mgr.record_decision(ctx, "decision", "outcome", True)
            mock_mem.store_decision.assert_called_once()


class TestExecutionManagerCreateContext:
    """Factory method edge cases."""

    def test_default_user_id_empty(self):
        ctx = ExecutionManager.create_context()
        assert ctx.user_id == ""
        assert ctx.source == ""
        assert ctx.request_id != ""

    def test_request_id_defaults_to_uuid(self):
        ctx1 = ExecutionManager.create_context()
        ctx2 = ExecutionManager.create_context()
        assert ctx1.request_id != ctx2.request_id

    def test_metadata_defaults_to_empty_dict(self):
        ctx = ExecutionManager.create_context()
        assert ctx.metadata == {}
        assert ctx.metadata is not None

    def test_all_fields_passthrough(self):
        ctx = ExecutionManager.create_context(
            source="api", user_id="u99", request_id="req_001",
            metadata={"env": "prod"},
        )
        assert ctx.source == "api"
        assert ctx.user_id == "u99"
        assert ctx.request_id == "req_001"
        assert ctx.metadata["env"] == "prod"

    def test_status_and_phase_defaults(self):
        ctx = ExecutionManager.create_context()
        assert ctx.phase == "init"
        assert ctx.status == "started"
        assert ctx.workflow_id == ""
        assert ctx.execution_id != ""
