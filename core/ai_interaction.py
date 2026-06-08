import logging

logger = logging.getLogger(__name__)


async def dispatch_ai_tool(
    tool: str,
    content: str,
    session_id: str | None = None,
    owner: str | None = None,
) -> tuple[str, dict]:
    logger.debug(f"AI tool dispatch: {tool} (no native handler available)")
    desc = f"{tool}: (unavailable)"
    result = {"output": f"Tool '{tool}' is not available in this build", "exit_code": 1}
    return desc, result


async def _resolve_model(owner: str = "") -> str | None:
    return None
