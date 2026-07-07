"""Read-only aggregation of the per-request security state.

``PipelineContext.security`` exposes a single frozen object combining
the identity, authentication, and authorization artifacts so that
downstream stages never need to reach for the individual fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.identity.models import IdentityContext
from core.pipeline.authentication_result import AuthenticationResult
from core.pipeline.authorization_result import AuthorizationResult


@dataclass(frozen=True)
class SecurityContext:
    """Read-only aggregation of the per-request security state.

    Every field is typed but may be ``None`` before the corresponding
    stage has run.  After the authorization stage all three fields are
    populated for every request.
    """

    identity: Optional[IdentityContext] = None
    """The resolved identity for the current request (set by load-context)."""

    authentication: Optional[AuthenticationResult] = None
    """The authentication result (set by authentication stage)."""

    authorization: Optional[AuthorizationResult] = None
    """The authorization result (set by authorization stage)."""
