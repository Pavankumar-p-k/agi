"""Tool-level security checks.

Two layers:

1. A static blocklist of dangerous tools that only admins (or the
   single-user owner) may ever run.
2. Scope evaluation against the registered :class:`ToolPolicy` for the
   tool, using the shared policy engine.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from core.authz.engine import authz_engine
from core.authz.schema import AuthContext
from core.tools.policy import policy_engine

logger = logging.getLogger(__name__)

#: Tools that must never be reachable by a non-admin principal.
NON_ADMIN_BLOCKED_TOOLS = frozenset({
    "bash",
    "shell",
    "shell_command",
    "python",
    "read_file",
    "write_file",
    "edit_file",
    "batch_edit_file",
    "undo_edit_file",
    "manage_settings",
    "manage_tokens",
})

#: Scope required for tools that declare no explicit policy (deny-by-default).
DEFAULT_REQUIRED_SCOPE = "tools:execute:high"

#: Tools that are safe for an unauthenticated/limited principal.
PUBLIC_TOOLS = frozenset({"search", "read", "suggest"})


def owner_is_admin_or_single_user(owner: Any) -> bool:
    """True when *owner* is an admin or the single-user deployment owner.

    Kept as a module-level function so tests/deployments can patch it.
    """
    if owner is None:
        return False
    if isinstance(owner, AuthContext):
        return owner.is_admin
    auth = getattr(owner, "is_admin", None)
    if isinstance(auth, bool):
        return auth
    for attr in ("roles", "role"):
        roles = getattr(owner, attr, None)
        if roles is None:
            continue
        if isinstance(roles, str):
            roles = {roles}
        try:
            if any(str(r).lower() == "admin" for r in roles):
                return True
        except TypeError:
            continue
    cfg = getattr(owner, "config", None)
    if isinstance(cfg, dict):
        return bool(cfg.get("admin") or cfg.get("single_user"))
    return False


def blocked_tools_for_owner(owner: Any) -> set:
    """Tools blocked for *owner* (empty for admins/single-user owners)."""
    if owner_is_admin_or_single_user(owner):
        return set()
    return set(NON_ADMIN_BLOCKED_TOOLS)


def is_public_blocked_tool(tool_name: Any) -> bool:
    """True when *tool_name* is unsafe for a public/limited caller."""
    if not tool_name:
        return False
    name = str(tool_name).strip()
    if not name:
        return False
    return name in NON_ADMIN_BLOCKED_TOOLS


def _context_is_privileged(context: Any) -> bool:
    return owner_is_admin_or_single_user(context)


def is_authorized_to_execute(tool_id: Any, context: Any = None) -> bool:
    """True when *context* may execute *tool_id*.

    Deny-by-default: unknown tools require ``tools:execute:high``.
    """
    if not tool_id:
        return False
    name = str(tool_id)

    if name in PUBLIC_TOOLS and context is None:
        return True

    # Static blocklist: non-admins may never touch these.
    if name in NON_ADMIN_BLOCKED_TOOLS and not _context_is_privileged(context):
        return False

    policy = None
    try:
        policy = policy_engine.get_policy(name)
    except Exception:  # noqa: BLE001 — policy lookup must not break dispatch
        policy = None

    required = getattr(policy, "required_scope", None) or DEFAULT_REQUIRED_SCOPE
    if not required:
        return True
    try:
        return bool(authz_engine.evaluate(context, required))
    except Exception as exc:  # noqa: BLE001 — fail closed on evaluator errors
        logger.warning("authorization check failed for %s: %s", name, exc)
        return False


def authorize_tool_scope(tool_type: Any, owner: Any = None) -> bool:
    """Evaluate the ``tools:execute:<tier>`` scope for *owner*.

    Admin/single-user owners hold the wildcard scope; everyone else must be
    granted it explicitly. Unknown tools deny (fail closed). This lives here
    (not in the dispatch code) because tool-level scope evaluation is owned by
    this module (architecture Rule 17).
    """
    if not tool_type:
        return False
    if owner_is_admin_or_single_user(owner):
        context = AuthContext(user_id=str(owner or "single_user"),
                              scopes={"tools:execute:*"})
    else:
        context = AuthContext(user_id=str(owner or "user"), scopes=set())
    try:
        return bool(authz_engine.evaluate(context, "tools:execute:" + str(tool_type)))
    except Exception as exc:  # noqa: BLE001 — deny when the evaluator is unavailable
        logger.debug("tool scope evaluation failed for %s: %s", tool_type, exc)
        return False


async def async_is_authorized_to_execute(tool_id: Any, context: Any = None) -> bool:
    return is_authorized_to_execute(tool_id, context)


def is_authorized(tool_id: Any, context: Any = None) -> bool:
    """Alias kept for compatibility with older call sites."""
    return is_authorized_to_execute(tool_id, context)


async def async_blocked_tools_for_owner(owner: Any) -> set:
    return blocked_tools_for_owner(owner)


async def async_is_public_blocked_tool(tool_name: Any) -> bool:
    return is_public_blocked_tool(tool_name)


__all__ = [
    "NON_ADMIN_BLOCKED_TOOLS",
    "PUBLIC_TOOLS",
    "DEFAULT_REQUIRED_SCOPE",
    "owner_is_admin_or_single_user",
    "blocked_tools_for_owner",
    "is_public_blocked_tool",
    "is_authorized_to_execute",
    "is_authorized",
    "authorize_tool_scope",
    "async_is_authorized_to_execute",
    "async_blocked_tools_for_owner",
    "async_is_public_blocked_tool",
]
