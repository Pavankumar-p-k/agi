"""Tests for identity propagation through the pipeline.

Sprint 1: structural only — identity flows from Request → PipelineContext
without any authentication behavior.
"""

from __future__ import annotations

import pytest

from core.identity import get_identity_service, set_identity_service
from core.identity.models import AuthenticationState, IdentityContext, UserIdentity
from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext
from core.pipeline.messages import Request, Response
from core.pipeline.pipeline import Pipeline, get_pipeline, process_message, set_pipeline

pytestmark = pytest.mark.asyncio


class _IdentityCapturingStage(PipelineStage):
    """Minimal stage that captures identity for assertion."""

    @property
    def name(self) -> str:
        return "test_capture"

    async def execute(self, context: PipelineContext) -> StageResult:
        self.captured = context.identity
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)


async def test_request_holds_identity():
    identity = IdentityContext(authentication_state=AuthenticationState.SYSTEM)
    req = Request(text="hello", transport="test", identity=identity)
    assert req.identity is not None
    assert req.identity.authentication_state == AuthenticationState.SYSTEM


async def test_request_defaults_identity_none():
    req = Request(text="hello", transport="test")
    assert req.identity is None


async def test_process_message_populates_identity():
    """process_message() creates IdentityContext when user_id is provided."""
    old = get_pipeline()
    try:
        capture = _IdentityCapturingStage()
        p = Pipeline()
        p.add_stage(capture)
        set_pipeline(p)

        req = Request(text="hello", transport="test", user_id="user-1", session_id="sess-1")
        resp = await process_message(req)
        assert resp is not None
        assert capture.captured is not None
        assert capture.captured.user is not None
        assert capture.captured.user.id == "user-1"
        assert capture.captured.session is not None
        assert capture.captured.session.id == "sess-1"
        assert capture.captured.agent is not None
        assert capture.captured.agent.type == "test"
    finally:
        set_pipeline(old)


async def test_identity_in_pipeline_context_after_execution():
    """Identity populated on PipelineContext survives Pipeline.execute()."""
    svc = get_identity_service()
    pipeline = Pipeline()

    ctx = PipelineContext(
        request_id="test-1",
        transport="test",
        raw_input="hello",
    )
    ctx.identity = svc.create_context(
        user_id="user-1",
        session_id="sess-1",
        agent_type="test",
    )
    result = await pipeline.execute(ctx)
    assert result.identity is not None
    assert result.identity.user is not None
    assert result.identity.user.id == "user-1"
    assert result.identity.session is not None
    assert result.identity.session.id == "sess-1"
    assert result.identity.agent is not None
    assert result.identity.agent.type == "test"


async def test_identity_survives_all_stages():
    """Identity remains accessible after full pipeline execution."""
    pipeline = Pipeline()
    ctx = PipelineContext(
        request_id="test-2",
        transport="test",
        raw_input="hello world",
    )
    svc = get_identity_service()
    ctx.identity = svc.create_context(
        user_id="survivor",
        agent_type="test",
    )
    result = await pipeline.execute(ctx)
    assert result.identity is not None
    assert result.identity.user.id == "survivor"


async def test_anonymous_when_no_user_id():
    """When user_id is absent, authentication_state is ANONYMOUS."""
    svc = get_identity_service()
    ctx = PipelineContext(
        request_id="test-3",
        transport="test",
        raw_input="hello",
    )
    ctx.identity = svc.create_context(
        user_id=None,
        session_id=None,
        agent_type="test",
    )
    assert ctx.identity is not None
    assert ctx.identity.authentication_state == AuthenticationState.ANONYMOUS
    assert ctx.identity.user is None
