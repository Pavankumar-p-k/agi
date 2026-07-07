"""Tests for AuthenticationStage and authentication integration.

Sprint 2: covers AuthenticationResult, IdentityService.authenticate_session(),
and the six replay scenarios.
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
from core.pipeline.authentication_result import AuthenticationResult
from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext
from core.pipeline.messages import Request
from core.pipeline.pipeline import Pipeline, get_pipeline, process_message, set_pipeline
from core.pipeline.stages.auth import AuthenticationStage

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
    """Captures identity and auth result after authentication."""

    @property
    def name(self) -> str:
        return "test_capture"

    async def execute(self, context: PipelineContext) -> StageResult:
        self.captured_identity = context.identity
        self.captured_auth_result = context.authentication_result
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)


class _AuthTokenStage(PipelineStage):
    """Injects an auth token into metadata before authentication."""

    def __init__(self, token: str | None):
        self.token = token

    @property
    def name(self) -> str:
        return "test_seed_auth"

    async def execute(self, context: PipelineContext) -> StageResult:
        if self.token is not None:
            context.metadata["auth_token"] = self.token
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)


async def _run_pipeline_with_auth(
    identity: IdentityContext | None,
    token: str | None = None,
) -> tuple[IdentityContext | None, AuthenticationResult | None]:
    """Run pipeline with AuthenticationStage and return identity + result."""
    capture = _IdentityCapturingStage()
    p = Pipeline()
    if token is not None:
        p.add_stage(_AuthTokenStage(token))
    p.add_stage(AuthenticationStage())
    p.add_stage(capture)

    ctx = PipelineContext(
        request_id="test-auth",
        transport="test",
        raw_input="hello",
    )
    ctx.identity = identity
    if token is not None:
        ctx.metadata["auth_token"] = token

    result = await p.execute(ctx)
    return result.identity, result.authentication_result


# ── Scenario 1: Anonymous (no identity, no token) ──────────────────────────────


@pytest.mark.asyncio
class TestAnonymous:
    """No identity context, no token → ANONYMOUS, not authenticated."""

    async def test_anonymous_no_identity(self):
        identity, auth_result = await _run_pipeline_with_auth(identity=None)
        assert auth_result is not None
        assert auth_result.authenticated is False
        assert auth_result.state == AuthenticationState.ANONYMOUS
        assert auth_result.principal is None
        assert auth_result.reason == "no identity context"

    async def test_anonymous_with_identity(self):
        identity = _make_identity()
        result_identity, auth_result = await _run_pipeline_with_auth(identity=identity)
        assert auth_result is not None
        assert auth_result.authenticated is False
        assert auth_result.state == AuthenticationState.ANONYMOUS
        assert result_identity is not None
        assert result_identity.authentication_state == AuthenticationState.ANONYMOUS


# ── Scenario 2: Identified (user_id present, no token) ─────────────────────────


@pytest.mark.asyncio
class TestIdentified:
    """User identity claimed but not validated."""

    async def test_identified_no_token(self):
        identity = _make_identity(user_id="user-1", state=AuthenticationState.IDENTIFIED)
        result_identity, auth_result = await _run_pipeline_with_auth(identity=identity)
        assert auth_result is not None
        assert auth_result.authenticated is False
        assert auth_result.state == AuthenticationState.IDENTIFIED
        assert auth_result.reason == "no authentication token provided"
        assert result_identity is not None
        assert result_identity.authentication_state == AuthenticationState.IDENTIFIED


# ── Scenario 3: Authenticated (valid token) ────────────────────────────────────


@pytest.mark.asyncio
class TestAuthenticated:
    """Valid token passed to AuthenticationStage → AUTHENTICATED."""

    @pytest.fixture
    def auth_manager_and_token(self):
        from core import auth as auth_module

        with tempfile.TemporaryDirectory() as tmpdir:
            auth_path = os.path.join(tmpdir, "auth.json")
            old_default = auth_module.DEFAULT_AUTH_PATH
            auth_module.DEFAULT_AUTH_PATH = auth_path

            am = auth_module.AuthManager(auth_path=auth_path)
            am.setup("testuser", "TestPass123!")
            token = am.create_session("testuser", "TestPass123!")
            assert token is not None
            yield am, token

            auth_module.DEFAULT_AUTH_PATH = old_default

    async def test_valid_token_updates_identity(self, auth_manager_and_token):
        """Valid token transitions IDENTIFIED → AUTHENTICATED."""
        am, token = auth_manager_and_token
        identity = _make_identity(user_id="testuser", state=AuthenticationState.IDENTIFIED)
        with patch("core.auth.get_auth_manager", return_value=am):
            result_identity, auth_result = await _run_pipeline_with_auth(
                identity=identity,
                token=token,
            )
        assert auth_result is not None
        assert auth_result.authenticated is True
        assert auth_result.state == AuthenticationState.AUTHENTICATED
        assert auth_result.principal is not None
        assert auth_result.principal.id == "testuser"
        assert result_identity is not None
        assert result_identity.authentication_state == AuthenticationState.AUTHENTICATED
        assert result_identity.user is not None
        assert result_identity.user.id == "testuser"

    async def test_valid_token_produces_authentication_result(self, auth_manager_and_token):
        """AuthenticationResult has correct fields after successful auth."""
        am, token = auth_manager_and_token
        identity = _make_identity(state=AuthenticationState.ANONYMOUS)
        with patch("core.auth.get_auth_manager", return_value=am):
            result_identity, auth_result = await _run_pipeline_with_auth(
                identity=identity,
                token=token,
            )
        assert auth_result.authenticated is True
        assert auth_result.principal is not None
        assert auth_result.principal.id == "testuser"
        assert auth_result.session is not None
        assert auth_result.session.id == token

    async def test_valid_token_replay_deterministic(self, auth_manager_and_token):
        """Same request + same token + same services → identical auth artifacts."""
        from core.pipeline.deterministic import DeterministicServices

        am, token = auth_manager_and_token
        svc = DeterministicServices.fake()
        identity = _make_identity(user_id="testuser", state=AuthenticationState.IDENTIFIED)

        async def _run():
            capture = _IdentityCapturingStage()
            p = Pipeline()
            p.add_stage(_AuthTokenStage(token))
            p.add_stage(AuthenticationStage())
            p.add_stage(capture)

            ctx = PipelineContext(
                request_id=svc.uuid4(),
                transport="test",
                raw_input="hello",
                services=svc,
            )
            ctx.identity = identity
            ctx.metadata["auth_token"] = token
            with patch("core.auth.get_auth_manager", return_value=am):
                result = await p.execute(ctx)
            return result.authentication_result

        r1 = await _run()
        r2 = await _run()
        assert r1 is not None and r2 is not None
        assert r1.authenticated == r2.authenticated
        assert r1.state == r2.state
        assert r1.principal == r2.principal
        assert r1.reason == r2.reason


# ── Scenario 4: Invalid session (bad token) ────────────────────────────────────


@pytest.mark.asyncio
class TestInvalidSession:
    """Invalid token → stays at current state, not authenticated."""

    async def test_invalid_token_rejected(self):
        identity = _make_identity(user_id="user-1", state=AuthenticationState.IDENTIFIED)
        result_identity, auth_result = await _run_pipeline_with_auth(
            identity=identity,
            token="this-is-not-a-valid-token",
        )
        assert auth_result is not None
        assert auth_result.authenticated is False
        assert auth_result.state == AuthenticationState.IDENTIFIED
        assert auth_result.reason == "invalid or expired token"
        assert result_identity is not None
        assert result_identity.authentication_state == AuthenticationState.IDENTIFIED


# ── Scenario 5: Expired session ────────────────────────────────────────────────


@pytest.mark.asyncio
class TestExpiredSession:
    """Expired token → treated as invalid."""

    @pytest.fixture
    def expired_token_fixture(self):
        from core import auth as auth_module
        import json
        import time

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
            sessions[token]["expiry"] = time.time() - 1  # 1 second in the past
            with open(sessions_path, "w") as f:
                json.dump(sessions, f)

            # Re-init AuthManager to reload expired sessions
            am2 = auth_module.AuthManager(auth_path=auth_path)
            yield am2, token

            auth_module.DEFAULT_AUTH_PATH = old_default

    async def test_expired_token_rejected(self, expired_token_fixture):
        am, token = expired_token_fixture
        identity = _make_identity(user_id="expireduser", state=AuthenticationState.IDENTIFIED)
        with patch("core.auth.get_auth_manager", return_value=am):
            result_identity, auth_result = await _run_pipeline_with_auth(
                identity=identity,
                token=token,
            )
        assert auth_result is not None
        assert auth_result.authenticated is False
        assert auth_result.reason in ("invalid or expired token",)


# ── Scenario 6: System identity ────────────────────────────────────────────────


@pytest.mark.asyncio
class TestSystemIdentity:
    """SYSTEM state is already authenticated — no token needed."""

    async def test_system_identity_authenticated(self):
        identity = _make_identity(user_id="scheduler", state=AuthenticationState.SYSTEM)
        result_identity, auth_result = await _run_pipeline_with_auth(identity=identity)
        assert auth_result is not None
        assert auth_result.authenticated is True
        assert auth_result.state == AuthenticationState.SYSTEM
        assert auth_result.reason == "system identity"

    async def test_system_identity_immutable(self):
        identity = _make_identity(user_id="scheduler", state=AuthenticationState.SYSTEM)
        result_identity, auth_result = await _run_pipeline_with_auth(
            identity=identity,
            token="some-token",
        )
        assert auth_result is not None
        assert auth_result.authenticated is True
        assert auth_result.state == AuthenticationState.SYSTEM


# ── AuthenticationResult contract tests ────────────────────────────────────────


class TestAuthenticationResultContract:
    """AuthenticationResult behaves like a frozen runtime artifact."""

    def test_frozen(self):
        r = AuthenticationResult(authenticated=True, state=AuthenticationState.AUTHENTICATED)
        with pytest.raises(Exception):
            r.authenticated = False

    def test_equality(self):
        r1 = AuthenticationResult(authenticated=False, state=AuthenticationState.ANONYMOUS)
        r2 = AuthenticationResult(authenticated=False, state=AuthenticationState.ANONYMOUS)
        assert r1 == r2

    def test_hashable(self):
        r = AuthenticationResult(authenticated=True, state=AuthenticationState.SYSTEM)
        d = {r: "value"}
        assert d[r] == "value"

    def test_defaults(self):
        r = AuthenticationResult(authenticated=False, state=AuthenticationState.ANONYMOUS)
        assert r.principal is None
        assert r.session is None
        assert r.reason is None
        assert r.metadata == {}


# ── Pipeline integration tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
class TestPipelineWithAuth:
    """Full pipeline execution with AuthenticationStage."""

    async def test_anonymous_via_process_message(self):
        """process_message with no user_id → anonymous."""
        old = get_pipeline()
        try:
            capture = _IdentityCapturingStage()
            p = Pipeline()
            p.add_stage(AuthenticationStage())
            p.add_stage(capture)
            set_pipeline(p)

            req = Request(text="hello", transport="test")
            resp = await process_message(req)
            assert resp is not None
            assert capture.captured_auth_result is not None
            assert capture.captured_auth_result.authenticated is False
            assert capture.captured_auth_result.state == AuthenticationState.ANONYMOUS
        finally:
            set_pipeline(old)

    async def test_identified_via_process_message(self):
        """process_message with user_id but no token → identified."""
        old = get_pipeline()
        try:
            capture = _IdentityCapturingStage()
            p = Pipeline()
            p.add_stage(AuthenticationStage())
            p.add_stage(capture)
            set_pipeline(p)

            req = Request(text="hello", transport="test", user_id="user-1")
            resp = await process_message(req)
            assert resp is not None
            assert capture.captured_auth_result is not None
            assert capture.captured_auth_result.authenticated is False
            assert capture.captured_auth_result.state == AuthenticationState.IDENTIFIED
        finally:
            set_pipeline(old)


# ── Post-auth identity immutability ────────────────────────────────────────────


@pytest.mark.asyncio
class TestPostAuthImmutability:
    """After AuthenticationStage, identity should not change."""

    async def test_identity_unchanged_by_downstream_stages(self):
        capture = _IdentityCapturingStage()
        p = Pipeline()
        p.add_stage(AuthenticationStage())
        p.add_stage(capture)

        identity = _make_identity(state=AuthenticationState.ANONYMOUS)
        ctx = PipelineContext(
            request_id="test-immutable",
            transport="test",
            raw_input="hello",
        )
        ctx.identity = identity
        result = await p.execute(ctx)
        assert result.authentication_result is not None
        assert result.authentication_result.state == AuthenticationState.ANONYMOUS
        assert result.identity is not None
        assert result.identity.authentication_state == AuthenticationState.ANONYMOUS


# ── IdentityService.authenticate_session unit tests ────────────────────────────


class TestAuthenticateSession:
    """IdentityService.authenticate_session() integration with AuthManager."""

    def test_authenticate_session_valid(self):
        from core import auth as auth_module

        with tempfile.TemporaryDirectory() as tmpdir:
            auth_path = os.path.join(tmpdir, "auth.json")
            old_default = auth_module.DEFAULT_AUTH_PATH
            auth_module.DEFAULT_AUTH_PATH = auth_path

            am = auth_module.AuthManager(auth_path=auth_path)
            am.setup("alice", "Secret123!")
            token = am.create_session("alice", "Secret123!")

            svc = get_identity_service()
            with patch("core.auth.get_auth_manager", return_value=am):
                result = svc.authenticate_session(token)
            assert result is not None
            user, session = result
            assert user.id == "alice"
            assert session.id == token
            assert session.user_id == "alice"

            auth_module.DEFAULT_AUTH_PATH = old_default

    def test_authenticate_session_invalid(self):
        svc = get_identity_service()
        result = svc.authenticate_session("nonsense-token")
        assert result is None

    def test_authenticate_session_empty(self):
        svc = get_identity_service()
        result = svc.authenticate_session("")
        assert result is None
