from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.identity.models import AuthenticationState, SessionIdentity, UserIdentity


@dataclass(frozen=True)
class AuthenticationResult:
    """Typed result of the AuthenticationStage.

    Created once by AuthenticationStage and never mutated.  Records whether
    the request's identity was authenticated, the resulting state, and the
    resolved principal and session.

    Only ``AuthenticationStage`` may construct this dataclass.
    """

    authenticated: bool
    """``True`` when the caller's identity passed validation."""

    state: AuthenticationState
    """The resulting authentication state for this request."""

    principal: UserIdentity | None = None
    """Resolved user identity when authentication succeeded."""

    session: SessionIdentity | None = None
    """Validated session when authentication succeeded."""

    reason: str | None = None
    """Human-readable explanation (e.g. ``"token expired"``)."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Extensible bag for additional authentication details."""

    def __hash__(self) -> int:
        return hash((self.authenticated, self.state))
