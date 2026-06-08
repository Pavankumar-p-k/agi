"""Server-side tool safety policy driven by RBAC."""

from __future__ import annotations

import logging
from typing import Optional, Set

from core.authz import AuthContext, Scope, Role
from core.authz.engine import authz_engine
from core.tools.policy import policy_engine

logger = logging.getLogger(__name__)


# Legacy blocklist for backward compatibility and fast-fail
NON_ADMIN_BLOCKED_TOOLS = {
    "bash", "python", "read_file", "write_file", "search_chats",
    "manage_memory", "manage_skills", "manage_tasks", "manage_endpoints",
    "manage_mcp", "manage_webhooks", "manage_tokens", "manage_documents",
    "manage_settings", "api_call", "app_api", "send_email", "reply_to_email",
    "list_emails", "read_email", "resolve_contact", "manage_contact",
    "manage_calendar", "vault_search", "vault_get", "vault_unlock",
    "download_model", "serve_model", "serve_preset", "stop_served_model",
    "cancel_download", "adopt_served_model",
}


def is_authorized_to_execute(tool_name: str, ctx: AuthContext) -> bool:
    """
    Primary RBAC entry point for tool execution authorization.
    Checks tool policy's required_scope against user's AuthContext.
    """
    if not tool_name:
        return True
        
    # 1. Admin escape hatch
    if ctx and Role.ADMIN in ctx.roles:
        return True
        
    # 2. Get tool policy and required scope
    policy = policy_engine.get_policy(tool_name)
    required_scope = str(Scope.TOOLS_EXECUTE_LOW) # Default for search etc.
    
    if policy and policy.required_scope:
        required_scope = policy.required_scope
    elif tool_name in NON_ADMIN_BLOCKED_TOOLS or tool_name.startswith("mcp__"):
        # Legacy fallback: if in blocklist but no scope defined, require HIGH
        required_scope = str(Scope.TOOLS_EXECUTE_HIGH)
        
    # 3. Evaluate via RBAC engine
    return authz_engine.evaluate(ctx, required_scope, resource=f"tool:{tool_name}")


def is_public_blocked_tool(tool_name: Optional[str]) -> bool:
    """
    LEGACY: Return True when a non-admin user must not execute this tool.
    Used by code that doesn't yet have an AuthContext.
    """
    if tool_name is None or tool_name == "":
        return False
    if not isinstance(tool_name, str):
        return True
    return tool_name in NON_ADMIN_BLOCKED_TOOLS or tool_name.startswith("mcp__")


def owner_is_admin_or_single_user(owner: Optional[str]) -> bool:
    """Return True for admins, or when auth is not configured yet."""
    try:
        from core.auth import get_auth_manager
        auth = get_auth_manager()
        if not auth.is_configured:
            return True
        return bool(owner and auth.is_admin(owner))
    except Exception as exc:
        logger.warning("Unable to evaluate owner admin status: %s", exc)
        return False


def blocked_tools_for_owner(owner: Optional[str]) -> Set[str]:
    """Tools to hide/disable for this owner under public-user policy."""
    if owner_is_admin_or_single_user(owner):
        return set()
    return set(NON_ADMIN_BLOCKED_TOOLS)
