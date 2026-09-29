"""AuthenticationStage — resolves identity + token into AuthenticationResult.

States:
  no identity context at all            -> ANONYMOUS  ("no identity context")
  identity claimed, no token            -> IDENTIFIED ("no authentication token provided")
  token + valid session                 -> AUTHENTICATED (principal filled)
  token + invalid/expired session       -> IDENTIFIED (token rejected)
"""
from __future__ import annotations

from typing import Any, Optional

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.pipeline import PipelineContext
from core.identity.models import (
    AuthenticationState,
    SessionIdentity,
    UserIdentity,
)
from core.pipeline.authentication_result import AuthenticationResult, SessionInfo


class AuthenticationStage(PipelineStage):
    @property
    def name(self) -> str:
        return "authentication"

    async def execute(self, context: PipelineContext) -> StageResult:
        identity = getattr(context, "identity", None)
        token = (context.metadata or {}).get("auth_token")

        # 0) SYSTEM identities are pre-authenticated (scheduler/internal).
        state0 = getattr(identity, "authentication_state", None)
        state0_val = getattr(state0, "value", state0)
        if state0_val == AuthenticationState.SYSTEM.value:
            from core.identity.models import UserIdentity as _UserIdentity
            from core.pipeline.authentication_result import SessionInfo as _SessionInfo
            user0 = getattr(identity, "user", None) or _UserIdentity(
                id="system", roles=["admin"])
            context.authentication_result = AuthenticationResult(
                authenticated=True,
                state=AuthenticationState.SYSTEM,
                reason="system identity",
                principal=user0,
                session=_SessionInfo(id="system", user_id=getattr(user0, "id", None)),
                user_id=getattr(user0, "id", None),
            )
            return StageResult(outcome=StageOutcome.CONTINUE, context=context)

        # 1) No identity context at all -> ANONYMOUS
        if identity is None and not token:
            context.authentication_result = AuthenticationResult(
                authenticated=False,
                state=AuthenticationState.ANONYMOUS,
                reason="no identity context",
            )
            return StageResult(outcome=StageOutcome.CONTINUE, context=context)

        # 2) Identity claimed (user_id) but no token.
        # Keep the identity's declared state verbatim — ANONYMOUS stays
        # ANONYMOUS (never silently promoted); a bare user_id claim without
        # an explicit state is IDENTIFIED (unverified).
        user_id = getattr(identity, "user", None) and identity.user.id
        if not token:
            if identity is not None:
                state = getattr(identity, "authentication_state", None)
                if state is None:
                    state = AuthenticationState.IDENTIFIED
            else:
                state = AuthenticationState.IDENTIFIED
            context.authentication_result = AuthenticationResult(
                authenticated=False,
                state=state,
                reason="no authentication token provided",
                user_id=user_id,
            )
            if identity is not None:
                identity.authentication_state = state
            return StageResult(outcome=StageOutcome.CONTINUE, context=context)

        # 3) Token present -> validate via AuthManager
        principal: Optional[UserIdentity] = None
        session: Optional[SessionInfo] = None
        username: Optional[str] = None
        valid = False
        try:
            from core.auth import get_auth_manager
            am = get_auth_manager()
            username = am.get_username_for_token(token)
            valid = bool(username)
        except Exception:  # noqa: BLE001 — auth manager unavailable
            valid = False

        if valid:
            principal = UserIdentity(id=username or "", username=username or "")
            session = SessionInfo(id=token, user_id=username)
            context.authentication_result = AuthenticationResult(
                authenticated=True,
                state=AuthenticationState.AUTHENTICATED,
                reason="valid session token",
                principal=principal,
                session=session,
                user_id=username,
            )
            if identity is not None:
                identity.authentication_state = AuthenticationState.AUTHENTICATED
                identity.user = principal
                identity.session = SessionIdentity(id=token, user_id=username)
        else:
            context.authentication_result = AuthenticationResult(
                authenticated=False,
                state=AuthenticationState.IDENTIFIED,
                reason="invalid or expired token",
                user_id=user_id,
            )
            if identity is not None:
                identity.authentication_state = AuthenticationState.IDENTIFIED
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)
