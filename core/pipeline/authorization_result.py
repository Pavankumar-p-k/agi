"""AuthorizationResult — output of the authorization stage (frozen artifact)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class AuthorizationResult:
    allowed: bool = False
    reason: Optional[str] = None
    scope: str = ""
    roles: frozenset = frozenset()
    permissions: frozenset = frozenset()
    # Excluded from eq/hash so results stay hashable (dict not hashable).
    metadata: dict = field(default_factory=dict, compare=False)


__all__ = ["AuthorizationResult"]
