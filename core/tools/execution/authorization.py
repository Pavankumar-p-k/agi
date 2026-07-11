import logging
import uuid

logger = logging.getLogger(__name__)


def check_rbac(tool: str, owner: str | None) -> tuple[bool, str | None]:
    from core.auth import get_auth_manager
    from core.tools.security import is_authorized_to_execute

    ctx = get_auth_manager().resolve_context(owner or "guest")

    if not is_authorized_to_execute(tool, ctx):
        desc = f"{tool}: UNAUTHORIZED"
        result = {
            "error": (
                f"Tool '{tool}' requires higher permissions than granted to your role ({', '.join(ctx.roles)}). "
                "Contact an administrator to request the necessary access."
            ),
            "exit_code": 1,
        }
        logger.warning("RBAC blocked execution: owner=%r tool=%s roles=%r", owner, tool, ctx.roles)
        return False, result
    return True, None


async def check_approval(tool: str, content: str) -> tuple[bool, str | None]:
    from core.tools.policy import policy_engine

    policy = policy_engine.get_policy(tool)
    if policy and policy.needs_confirmation:
        from mcp.server import mcp_server
        if mcp_server.is_running:
            approval_id = uuid.uuid4().hex
            decision = await mcp_server.wait_for_approval(
                kind="exec",
                approval_id=approval_id,
                tool_name=tool,
                description=policy.description or f"Execution of {tool}",
                input_preview=str(content)[:1000]
            )
            if decision == "deny":
                desc = f"{tool}: DENIED"
                result = {"error": f"Tool '{tool}' execution was denied by user via MCP Bridge.", "exit_code": 1}
                logger.info("Tool denied by user via MCP Bridge: %s (%s)", tool, decision)
                return False, result
            logger.info("Tool approved by user via MCP Bridge: %s (%s)", tool, decision)
    return True, None
