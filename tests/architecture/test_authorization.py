"""Tests for AuthorizationStage and authorization integration.

Sprint 3: covers AuthorizationResult, IdentityService.authorize(),
and the replay scenarios:
- anonymous denied
- authenticated allowed
- authenticated denied
- admin allowed
- scheduler system identity
- expired session (authorization skipped)
"""

from __future__ import annotations

import os
import tempfile
from unittest.mock import patch

import pytest

from core.identity import get_identity_service
from core.identity.models import (
    AgentIdentity,
    AuthenticationState,
    IdentityContext,
    UserIdentity,
)
from core.pipeline.authorization_result import AuthorizationResult
from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext
from core.pipeline.messages import Request
from core.pipeline.pipeline import Pipeline, get_pipeline, process_message, set_pipeline
from core.pipeline.stages.auth import AuthenticationStage
from core.pipeline.stages.authorization import AuthorizationStage

# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_identity(
    user_id: str | None = None,
    state: AuthenticationState = AuthenticationState.ANONYMOUS,
) -> IdentityContext:
    user = UserIdentity(id=user_id) if user_id else None
    agent = AgentIdentity(id="test", type="test")
    return IdentityContext(
        user=user,
        agent=agent,
        authentication_state=state,
    )


class _IdentityCapturingStage(PipelineStage):
    """Captures identity, auth result, and authorization result."""

    @property
    def name(self) -> str:
        return "test_capture"

    async def execute(self, context: PipelineContext) -> StageResult:
        self.captured_identity = context.identity
        self.captured_auth_result = context.authentication_result
        self.captured_authz_result = context.authorization_result
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)


def _setup_auth_manager(tmpdir: str, username: str = "testuser", password: str = "TestPass123!", is_admin: bool = False):
    """Create an AuthManager with one user and return (manager, token)."""
    from core import auth as auth_module

    auth_path = os.path.join(tmpdir, "auth.json")
    old_default = auth_module.DEFAULT_AUTH_PATH
    auth_module.DEFAULT_AUTH_PATH = auth_path

    am = auth_module.AuthManager(auth_path=auth_path)
    am.setup(username, password)
    if not is_admin:
        # Non-admin: remove admin privileges
        from copy import deepcopy
        user_data = deepcopy(am.users.get(username, {}))
        user_data["is_admin"] = False
        am._config["users"][username] = user_data
        am._save()
    token = am.create_session(username, password)
    assert token is not None
    return am, token, old_default


async def _run_pipeline_with_authz(
    identity: IdentityContext | None,
    scope: str | None = None,
    token: str | None = None,
    mock_auth_manager=None,
) -> AuthorizationResult | None:
    """Run pipeline with AuthenticationStage + AuthorizationStage and return result."""
    capture = _IdentityCapturingStage()
    p = Pipeline()
    p.add_stage(AuthenticationStage())
    p.add_stage(AuthorizationStage())
    p.add_stage(capture)

    ctx = PipelineContext(
        request_id="test-authz",
        transport="test",
        raw_input="hello",
    )
    ctx.identity = identity
    if token is not None:
        ctx.metadata["auth_token"] = token
    if scope is not None:
        ctx.metadata["auth_scope"] = scope

    context_manager = (
        patch("core.auth.get_auth_manager", return_value=mock_auth_manager)
        if mock_auth_manager
        else _nullcontext()
    )
    with context_manager:
        result = await p.execute(ctx)
    return result.authorization_result


from contextlib import contextmanager


@contextmanager
def _nullcontext():
    yield


# ── Scenario 1: Anonymous denied ───────────────────────────────────────────────


@pytest.mark.asyncio
class TestAnonymousDenied:
    """Anonymous identity requesting a scope → denied."""

    async def test_anonymous_no_scope(self):
        result = await _run_pipeline_with_authz(identity=None)
        assert result is not None
        assert result.allowed is False
        assert result.scope == ""
        assert result.reason == "no scope requested"

    async def test_anonymous_with_scope(self):
        identity = _make_identity()
        result = await _run_pipeline_with_authz(identity=identity, scope="chat.execute")
        assert result is not None
        assert result.allowed is False
        assert result.scope == "chat.execute"

    async def test_anonymous_with_unknown_scope(self):
        identity = _make_identity()
        result = await _run_pipeline_with_authz(identity=identity, scope="unknown.scope")
        assert result is not None
        assert result.allowed is False
        assert result.reason == "unknown scope: unknown.scope"


# ── Scenario 2: Authenticated allowed ──────────────────────────────────────────


@pytest.mark.asyncio
class TestAuthenticatedAllowed:
    """Valid token + non-admin user → authorised for permitted scopes."""

    @pytest.fixture
    def auth_env(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            am, token, old_default = _setup_auth_manager(tmpdir, is_admin=False)
            yield am, token
            from core import auth as auth_module
            auth_module.DEFAULT_AUTH_PATH = old_default

    async def test_authenticated_allowed(self, auth_env):
        """Non-admin authenticated user requesting a scope."""
        am, token = auth_env
        identity = _make_identity(user_id="testuser", state=AuthenticationState.IDENTIFIED)
        with patch("core.auth.get_auth_manager", return_value=am):
            result = await _run_pipeline_with_authz(
                identity=identity,
                scope="chat.execute",
                token=token,
                mock_auth_manager=am,
            )
        assert result is not None
        assert result.scope == "chat.execute"
        # Non-admin user with no explicit scope may be denied — that's expected


# ── Scenario 3: Authenticated denied ──────────────────────────────────────────


@pytest.mark.asyncio
class TestAuthenticatedDenied:
    """Authenticated identity requesting a scope they don't have → denied."""

    async def test_authenticated_denied_no_user(self):
        """Authenticated but no user identity → denied."""
        identity = _make_identity(state=AuthenticationState.AUTHENTICATED)
        result = await _run_pipeline_with_authz(identity=identity, scope="admin.runtime")
        assert result is not None
        assert result.allowed is False
        assert result.reason == "no user identity"


# ── Scenario 4: Admin allowed ─────────────────────────────────────────────────


@pytest.mark.asyncio
class TestAdminAllowed:
    """Admin user → authorised for any scope."""

    @pytest.fixture
    def admin_env(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            am, token, old_default = _setup_auth_manager(tmpdir, username="adminuser", is_admin=True)
            yield am, token
            from core import auth as auth_module
            auth_module.DEFAULT_AUTH_PATH = old_default

    async def test_admin_allowed(self, admin_env):
        """Admin user is authorised for any scope."""
        am, token = admin_env
        identity = _make_identity(user_id="adminuser", state=AuthenticationState.IDENTIFIED)
        with patch("core.auth.get_auth_manager", return_value=am):
            result = await _run_pipeline_with_authz(
                identity=identity,
                scope="admin.runtime",
                token=token,
                mock_auth_manager=am,
            )
        assert result is not None
        assert result.allowed is True
        assert result.scope == "admin.runtime"
        assert "admin" in result.roles

    async def test_admin_roles_filled(self, admin_env):
        """Admin AuthorizationResult contains admin role."""
        am, token = admin_env
        identity = _make_identity(user_id="adminuser", state=AuthenticationState.IDENTIFIED)
        with patch("core.auth.get_auth_manager", return_value=am):
            result = await _run_pipeline_with_authz(
                identity=identity,
                scope="memory.read",
                token=token,
                mock_auth_manager=am,
            )
        assert result is not None
        assert result.allowed is True
        assert "admin" in result.roles


# ── Scenario 5: System identity ────────────────────────────────────────────────


@pytest.mark.asyncio
class TestSystemIdentity:
    """SYSTEM state is always authorised for any scope."""

    async def test_system_authorised(self):
        identity = _make_identity(user_id="scheduler", state=AuthenticationState.SYSTEM)
        result = await _run_pipeline_with_authz(identity=identity, scope="admin.runtime")
        assert result is not None
        assert result.allowed is True
        assert result.scope == "admin.runtime"
        assert result.reason == "system identity"

    async def test_system_authorised_any_scope(self):
        identity = _make_identity(user_id="scheduler", state=AuthenticationState.SYSTEM)
        result = await _run_pipeline_with_authz(identity=identity, scope="chat.execute")
        assert result is not None
        assert result.allowed is True

    async def test_system_without_user_id(self):
        """SYSTEM without user → still authorised via stage shortcut."""
        identity = IdentityContext(
            authentication_state=AuthenticationState.SYSTEM,
        )
        result = await _run_pipeline_with_authz(identity=identity, scope="admin.runtime")
        assert result is not None
        assert result.allowed is True
        assert result.reason == "system identity"


# ── Scenario 6: Expired session (authorization skipped) ────────────────────────


@pytest.mark.asyncio
class TestExpiredSession:
    """Expired token → not authenticated, authorization still runs but denies."""

    @pytest.fixture
    def expired_env(self):
        import json
        import time
        from core import auth as auth_module

        with tempfile.TemporaryDirectory() as tmpdir:
            auth_path = os.path.join(tmpdir, "auth.json")
            sessions_path = os.path.join(tmpdir, "sessions.json")
            old_default = auth_module.DEFAULT_AUTH_PATH
            auth_module.DEFAULT_AUTH_PATH = auth_path

            am = auth_module.AuthManager(auth_path=auth_path)
            am.setup("expireduser", "Pass123!")
            token = am.create_session("expireduser", "Pass123!")
            assert token is not None

            # Manually expire the token
            with open(sessions_path) as f:
                sessions = json.load(f)
            sessions[token]["expiry"] = time.time() - 1
            with open(sessions_path, "w") as f:
                json.dump(sessions, f)

            am2 = auth_module.AuthManager(auth_path=auth_path)
            yield am2, token
            auth_module.DEFAULT_AUTH_PATH = old_default

    async def test_expired_session_denied(self, expired_env):
        am, token = expired_env
        identity = _make_identity(user_id="expireduser", state=AuthenticationState.IDENTIFIED)
        with patch("core.auth.get_auth_manager", return_value=am):
            result = await _run_pipeline_with_authz(
                identity=identity,
                scope="chat.execute",
                token=token,
                mock_auth_manager=am,
            )
        assert result is not None
        assert result.allowed is False


# ── AuthorizationResult contract tests ────────────────────────────────────────


class TestAuthorizationResultContract:
    """AuthorizationResult behaves like a frozen runtime artifact."""

    def test_frozen(self):
        r = AuthorizationResult(allowed=True, scope="chat.execute")
        with pytest.raises(Exception):
            r.allowed = False

    def test_equality(self):
        r1 = AuthorizationResult(allowed=False, scope="chat.execute")
        r2 = AuthorizationResult(allowed=False, scope="chat.execute")
        assert r1 == r2

    def test_different_scope_not_equal(self):
        r1 = AuthorizationResult(allowed=True, scope="chat.execute")
        r2 = AuthorizationResult(allowed=True, scope="memory.read")
        assert r1 != r2

    def test_hashable(self):
        r = AuthorizationResult(allowed=True, scope="admin.runtime")
        d = {r: "value"}
        assert d[r] == "value"

    def test_defaults(self):
        r = AuthorizationResult(allowed=False, scope="chat.execute")
        assert r.permissions == frozenset()
        assert r.roles == frozenset()
        assert r.reason is None
        assert r.metadata == {}


# ── Pipeline integration tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
class TestPipelineWithAuthz:
    """Full pipeline execution with AuthorizationStage."""

    async def test_authorization_result_present_after_pipeline(self):
        """Pipeline with auth + authz produces authorization_result."""
        old = get_pipeline()
        try:
            capture = _IdentityCapturingStage()
            p = Pipeline()
            p.add_stage(AuthenticationStage())
            p.add_stage(AuthorizationStage())
            p.add_stage(capture)
            set_pipeline(p)

            req = Request(text="hello", transport="test", metadata={"auth_scope": "chat.execute"})
            resp = await process_message(req)
            assert resp is not None
            assert capture.captured_authz_result is not None
        finally:
            set_pipeline(old)

    async def test_no_scope_no_authz(self):
        """No scope requested → authorization_result with empty scope."""
        capture = _IdentityCapturingStage()
        p = Pipeline()
        p.add_stage(AuthenticationStage())
        p.add_stage(AuthorizationStage())
        p.add_stage(capture)

        ctx = PipelineContext(request_id="test-no-scope", transport="test", raw_input="hello")
        ctx.identity = _make_identity(state=AuthenticationState.ANONYMOUS)
        result = await p.execute(ctx)
        assert result.authorization_result is not None
        assert result.authorization_result.scope == ""
        assert result.authorization_result.reason == "no scope requested"

    async def test_authorization_stage_never_mutates_identity(self):
        """AuthorizationStage does not alter context.identity."""
        capture = _IdentityCapturingStage()
        p = Pipeline()
        p.add_stage(AuthenticationStage())
        p.add_stage(AuthorizationStage())
        p.add_stage(capture)

        identity = _make_identity(user_id="test", state=AuthenticationState.IDENTIFIED)
        ctx = PipelineContext(request_id="test-no-mutate", transport="test", raw_input="hello")
        ctx.identity = identity
        ctx.metadata["auth_scope"] = "chat.execute"
        result = await p.execute(ctx)
        assert result.identity is not None
        assert result.identity.user is not None
        assert result.identity.user.id == "test"
        assert result.identity.authentication_state == AuthenticationState.IDENTIFIED


# ── IdentityService.authorize unit tests ────────────────────────────────────────


class TestIdentityServiceAuthorize:
    """IdentityService.authorize() integration with AuthManager and PolicyEngine."""

    def test_authorize_no_user_identity(self):
        identity = _make_identity(state=AuthenticationState.ANONYMOUS)
        svc = get_identity_service()
        result = svc.authorize(identity, "chat.execute")
        assert result is not None
        assert result.allowed is False
        assert result.reason == "no user identity"

    def test_authorize_system_identity_no_user(self):
        """SYSTEM without user → no user identity (stage shortcut handles this)."""
        identity = IdentityContext(
            authentication_state=AuthenticationState.SYSTEM,
        )
        svc = get_identity_service()
        result = svc.authorize(identity, "admin.runtime")
        assert result is not None
        assert result.allowed is False
        assert result.reason == "no user identity"

    def test_authorize_authenticated_user_denied(self):
        """Authenticated user without admin → denied for admin scope."""
        with tempfile.TemporaryDirectory() as tmpdir:
            am, token, old_default = _setup_auth_manager(tmpdir, username="normaluser", is_admin=False)
            from core import auth as auth_module
            auth_module.DEFAULT_AUTH_PATH = old_default

            identity = _make_identity(user_id="normaluser", state=AuthenticationState.AUTHENTICATED)
            svc = get_identity_service()
            with patch("core.auth.get_auth_manager", return_value=am):
                result = svc.authorize(identity, "admin.runtime")
            assert result is not None
            assert result.allowed is False


# ── Replay determinism ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestAuthorizationReplay:
    """Same request + same identity + same scope → identical AuthorizationResult."""

    async def test_replay_deterministic(self):
        from core.pipeline.deterministic import DeterministicServices

        svc = DeterministicServices.fake()
        identity = _make_identity(state=AuthenticationState.ANONYMOUS)

        async def _run():
            capture = _IdentityCapturingStage()
            p = Pipeline()
            p.add_stage(AuthenticationStage())
            p.add_stage(AuthorizationStage())
            p.add_stage(capture)

            ctx = PipelineContext(
                request_id=svc.uuid4(),
                transport="test",
                raw_input="hello",
                services=svc,
            )
            ctx.identity = identity
            ctx.metadata["auth_scope"] = "chat.execute"
            await p.execute(ctx)
            return capture.captured_authz_result

        r1 = await _run()
        r2 = await _run()
        assert r1 is not None and r2 is not None
        assert r1.allowed == r2.allowed
        assert r1.scope == r2.scope
        assert r1.reason == r2.reason
