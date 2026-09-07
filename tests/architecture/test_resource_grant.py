"""Tests for ResourceGrant — immutable permission grant for a resource scope.

Sprint 3 of Phase 6C.  ResourceGrant is issued by AuthorizationStage
and consumed by ResourceAccessStage and ExecutionStage.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

import pytest

from core.identity import ResourceScope, Visibility
from core.pipeline.resource_grant import ResourceGrant


class TestResourceGrantContract:
    """ResourceGrant is a frozen dataclass with correct semantics."""

    def test_frozen(self):
        """ResourceGrant cannot be mutated after creation."""
        scope = ResourceScope(tenant_id="acme")
        grant = ResourceGrant(subject_id="user-1", scope=scope, permissions=frozenset({"chat.execute"}))
        with pytest.raises(AttributeError):
            grant.subject_id = "other"  # type: ignore[misc]

    def test_defaults(self):
        """Permissions defaults to empty frozenset, expires_at and issued_at
        to None, metadata to empty dict."""
        scope = ResourceScope(tenant_id="acme")
        grant = ResourceGrant(subject_id="user-1", scope=scope)
        assert grant.permissions == frozenset()
        assert grant.expires_at is None
        assert grant.metadata == {}

    def test_all_fields_populated(self):
        """All ResourceGrant fields populated correctly."""
        scope = ResourceScope(tenant_id="acme", workspace_id="ws-1", owner_id="alice")
        now = datetime.now(timezone.utc)
        grant = ResourceGrant(
            subject_id="alice",
            scope=scope,
            permissions=frozenset({"chat.execute", "memory.read"}),
            issued_at=now,
            expires_at=None,
            metadata={"source": "authz"},
        )
        assert grant.subject_id == "alice"
        assert grant.scope == scope
        assert grant.permissions == frozenset({"chat.execute", "memory.read"})
        assert grant.issued_at == now
        assert grant.expires_at is None
        assert grant.metadata == {"source": "authz"}

    def test_equality(self):
        """Two grants with same fields are equal, different scope not equal."""
        scope = ResourceScope(tenant_id="acme")
        g1 = ResourceGrant(subject_id="u1", scope=scope, permissions=frozenset({"read"}))
        g2 = ResourceGrant(subject_id="u1", scope=scope, permissions=frozenset({"read"}))
        assert g1 == g2

        g3 = ResourceGrant(subject_id="u2", scope=scope)
        assert g1 != g3

    def test_hashable(self):
        """ResourceGrant can be used in sets and as dict keys."""
        scope = ResourceScope(tenant_id="acme")
        g1 = ResourceGrant(subject_id="u1", scope=scope, permissions=frozenset({"read"}))
        g2 = ResourceGrant(subject_id="u2", scope=scope)
        s = {g1, g2}
        assert len(s) == 2
        d = {g1: "grant-1", g2: "grant-2"}
        assert d[g1] == "grant-1"

    def test_different_subject_not_equal(self):
        """Different subject_id makes grants not equal."""
        scope = ResourceScope(tenant_id="acme")
        g1 = ResourceGrant(subject_id="alice", scope=scope)
        g2 = ResourceGrant(subject_id="bob", scope=scope)
        assert g1 != g2


class TestResourceGrantPipelineIntegration:
    """ResourceGrant is issued by AuthorizationStage and available on context."""

    def _setup_admin_auth(self, tmpdir: str) -> tuple:
        """Create an AuthManager with an admin user and return (manager, token)."""
        from core import auth as auth_module

        auth_path = os.path.join(tmpdir, "auth.json")
        old_default = auth_module.DEFAULT_AUTH_PATH
        auth_module.DEFAULT_AUTH_PATH = auth_path

        am = auth_module.AuthManager(auth_path=auth_path)
        am.setup("admin-user", "AdminPass123!")
        token = am.create_session("admin-user", "AdminPass123!")
        assert token is not None
        return am, token, old_default

    async def test_resource_grant_on_context(self):
        """AuthorizationStage sets resource_grant on context when scope is
        requested."""
        from core.pipeline.base import PipelineStage, StageOutcome, StageResult
        from core.pipeline.context import PipelineContext
        from core.pipeline.messages import Request
        from core.pipeline.pipeline import Pipeline, get_pipeline, process_message, set_pipeline
        from core.pipeline.stages.auth import AuthenticationStage
        from core.pipeline.stages.authorization import AuthorizationStage

        captured = None

        class CaptureStage(PipelineStage):
            @property
            def name(self) -> str:
                return "capture"

            async def execute(self, context: PipelineContext) -> StageResult:
                nonlocal captured
                captured = context.resource_grant
                return StageResult(outcome=StageOutcome.CONTINUE, context=context)

        with tempfile.TemporaryDirectory() as tmpdir:
            am, token, old_default = self._setup_admin_auth(tmpdir)
            try:
                from core import auth as auth_module
                auth_module.DEFAULT_AUTH_PATH = old_default

                old = get_pipeline()
                p = Pipeline()
                p.add_stage(AuthenticationStage())
                p.add_stage(AuthorizationStage())
                p.add_stage(CaptureStage())
                set_pipeline(p)

                req = Request(
                    text="hello",
                    transport="test",
                    user_id="admin-user",
                    metadata={"auth_scope": "chat.execute", "auth_token": token},
                )
                with patch("core.auth.get_auth_manager", return_value=am):
                    resp = await process_message(req)
                assert captured is not None
                assert isinstance(captured, ResourceGrant)
                assert captured.subject_id == "admin-user"
                assert captured.scope is not None
                assert captured.scope.tenant_id is not None
                set_pipeline(old)
            finally:
                auth_module.DEFAULT_AUTH_PATH = old_default

    async def test_resource_grant_in_security_context(self):
        """resource_grant is accessible through PipelineContext.security."""
        from core.pipeline.base import PipelineStage, StageOutcome, StageResult
        from core.pipeline.context import PipelineContext
        from core.pipeline.messages import Request
        from core.pipeline.pipeline import Pipeline, get_pipeline, process_message, set_pipeline
        from core.pipeline.stages.auth import AuthenticationStage
        from core.pipeline.stages.authorization import AuthorizationStage

        captured = None

        class CaptureStage(PipelineStage):
            @property
            def name(self) -> str:
                return "capture"

            async def execute(self, context: PipelineContext) -> StageResult:
                nonlocal captured
                captured = context.security.resource_grant
                return StageResult(outcome=StageOutcome.CONTINUE, context=context)

        with tempfile.TemporaryDirectory() as tmpdir:
            am, token, old_default = self._setup_admin_auth(tmpdir)
            try:
                from core import auth as auth_module
                auth_module.DEFAULT_AUTH_PATH = old_default

                old = get_pipeline()
                p = Pipeline()
                p.add_stage(AuthenticationStage())
                p.add_stage(AuthorizationStage())
                p.add_stage(CaptureStage())
                set_pipeline(p)

                req = Request(
                    text="hello",
                    transport="test",
                    user_id="admin-user",
                    metadata={"auth_scope": "chat.execute", "auth_token": token},
                )
                with patch("core.auth.get_auth_manager", return_value=am):
                    resp = await process_message(req)
                assert captured is not None
                assert isinstance(captured, ResourceGrant)
                assert captured.subject_id == "admin-user"
                set_pipeline(old)
            finally:
                auth_module.DEFAULT_AUTH_PATH = old_default

    async def test_no_grant_when_no_scope(self):
        """No ResourceGrant issued when no scope is requested."""
        from core.pipeline.base import PipelineStage, StageOutcome, StageResult
        from core.pipeline.context import PipelineContext
        from core.pipeline.messages import Request
        from core.pipeline.pipeline import Pipeline, get_pipeline, process_message, set_pipeline
        from core.pipeline.stages.auth import AuthenticationStage
        from core.pipeline.stages.authorization import AuthorizationStage

        captured = None

        class CaptureStage(PipelineStage):
            @property
            def name(self) -> str:
                return "capture"

            async def execute(self, context: PipelineContext) -> StageResult:
                nonlocal captured
                captured = context.resource_grant
                return StageResult(outcome=StageOutcome.CONTINUE, context=context)

        old = get_pipeline()
        try:
            p = Pipeline()
            p.add_stage(AuthenticationStage())
            p.add_stage(AuthorizationStage())
            p.add_stage(CaptureStage())
            set_pipeline(p)

            req = Request(text="hello", transport="test", user_id="admin-user")
            resp = await process_message(req)
            assert captured is None
        finally:
            set_pipeline(old)

    async def test_no_grant_when_denied(self):
        """No ResourceGrant issued when authorization is denied."""
        from core.pipeline.base import PipelineStage, StageOutcome, StageResult
        from core.pipeline.context import PipelineContext
        from core.pipeline.messages import Request
        from core.pipeline.pipeline import Pipeline, get_pipeline, process_message, set_pipeline
        from core.pipeline.stages.auth import AuthenticationStage
        from core.pipeline.stages.authorization import AuthorizationStage

        captured_grant = None
        captured_result = None

        class CaptureStage(PipelineStage):
            @property
            def name(self) -> str:
                return "capture"

            async def execute(self, context: PipelineContext) -> StageResult:
                nonlocal captured_grant, captured_result
                captured_grant = context.resource_grant
                captured_result = context.authorization_result
                return StageResult(outcome=StageOutcome.CONTINUE, context=context)

        old = get_pipeline()
        try:
            p = Pipeline()
            p.add_stage(AuthenticationStage())
            p.add_stage(AuthorizationStage())
            p.add_stage(CaptureStage())
            set_pipeline(p)

            req = Request(
                text="hello",
                transport="test",
                user_id="anonymous-user",
                metadata={"auth_scope": "admin.runtime"},
            )
            resp = await process_message(req)
            assert captured_result is not None
            assert captured_result.allowed is False
            assert captured_grant is None
        finally:
            set_pipeline(old)
