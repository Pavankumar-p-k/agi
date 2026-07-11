import logging

logger = logging.getLogger(__name__)


def record_tool_metric(tool: str) -> None:
    from core.observability.metrics import inc_tool_calls_total
    inc_tool_calls_total(tool)
