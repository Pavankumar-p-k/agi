from __future__ import annotations

from typing import Any

from core.graph.state import AgentPhase, AgentState


def route_decision(state: AgentState) -> str | None:
    if state.phase == AgentPhase.PAUSED:
        if not state.resume_action:
            return "__pause__"
        return "resume"
    if state.phase == AgentPhase.THINKING:
        if state.parallel_sub_agents:
            return "parallel_sub_agents"
        round_state = getattr(state, "round_state", None)
        if getattr(state, "pause_before_effectful", False) and round_state is not None:
            tool_blocks = list(getattr(round_state, "tool_blocks", []) or [])
            if tool_blocks:
                tool_names = [getattr(tb, "tool", None) for tb in tool_blocks]
                if any(t not in {"web_search", "search"} for t in tool_names):
                    return "pause"
    return None


async def async_route_decision(state: AgentState) -> str | None:
    return route_decision(state)
