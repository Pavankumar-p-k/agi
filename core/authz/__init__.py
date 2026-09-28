"""Authorization vocabulary re-exports.

Engine wiring lives in the ``engine`` submodule; this package surface only
exposes the schema types so ordinary callers never touch the policy engine
directly (see the architecture rules on policy access).
"""
from __future__ import annotations

from .schema import AuthContext, Permission, Role, Scope

__all__ = ["AuthContext", "Permission", "Role", "Scope"]
