from __future__ import annotations

from typing import Any

from core.authz.engine import authz_engine
from core.tools.policy import policy_engine

NON_ADMIN_BLOCKED_TOOLS = {
    "bash",
    "shell",
    "shell_command",
    "python",
    "read_file",
    "write_file",
    "browser_evaluate",
}


def owner_is_admin_or_single_user(owner: Any) -> bool:
    value = str(owner or "").lower()
    return value.startswith("admin") or value in {"", "single_user"}


def blocked_tools_for_owner(owner: Any) -> set[str]:
    return set() if owner_is_admin_or_single_user(owner) else {
        "bash",
        "shell",
        "shell_command",
        "python",
        "read_file",
        "write_file",
    }


def is_public_blocked_tool(tool_name: Any) -> bool:
    return str(tool_name or "") in {"bash", "shell_command"}


def is_authorized_to_execute(tool_name: str, context: Any) -> bool:
    policy = policy_engine.get(tool_name)
    if policy is None:
        return tool_name not in {"browser_evaluate"}
    return authz_engine.evaluate(context, policy.required_scope)


async def async_is_authorized_to_execute(tool_name: str, context: Any) -> bool:
    return is_authorized_to_execute(tool_name, context)
