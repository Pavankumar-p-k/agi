from __future__ import annotations

import asyncio
import json
from typing import Any

from core.graph.state import AgentPhase, AgentState


async def _run_sub_agent(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "index": config.get("index", 0),
        "task": config.get("task", ""),
        "response": "result",
        "results": [],
        "error": None,
    }


def _tool_is_effectful(tool_name: str | None) -> bool:
    if not tool_name:
        return False
    return tool_name not in {"web_search", "search", "read_file", "list_dir", "browser"}


async def pause_node(state: AgentState) -> AgentState:
    state.phase = AgentPhase.PAUSED
    state.paused_tool_data = None
    if state.pause_before_effectful and getattr(state, "round_state", None) is not None:
        blocks = list(getattr(state.round_state, "tool_blocks", []) or [])
        effectful = []
        for block in blocks:
            tool = getattr(block, "tool", None)
            if _tool_is_effectful(tool):
                effectful.append({"tool": tool, "input": getattr(block, "input", None)})
        if effectful:
            state.paused_tool_data = effectful
            state.phase = AgentPhase.PAUSED
    if state.paused_tool_data:
        payload = {
            "type": "human_review",
            "run_id": state.run_id,
            "round": getattr(state, "round_num", getattr(getattr(state, "round_state", None), "round_num", 0)),
            "tools": state.paused_tool_data,
        }
        state.events.append(f"data: {json.dumps(payload)}")
        try:
            import core.persistence.store as _pstore
            if hasattr(_pstore, "checkpoint_store") and _pstore.checkpoint_store is not None:
                _pstore.checkpoint_store.save_agent_state(state)
        except Exception:
            pass
    else:
        state.phase = AgentPhase.TOOL_CALLING
    return state


async def resume_node(state: AgentState) -> AgentState:
    action = (state.resume_action or "").strip().lower()
    if not action:
        state.phase = AgentPhase.PAUSED
        return state

    if action in {"approve", "continue", "allow"}:
        state.phase = AgentPhase.TOOL_CALLING
        state.resume_action = ""
        state.paused_tool_data = None
        state.events.append(f"data: {json.dumps({'type': 'resume_approved', 'run_id': state.run_id})}")
        return state

    feedback = state.resume_feedback.strip() or "rejected by the user"
    state.phase = AgentPhase.THINKING
    state.resume_action = ""
    state.resume_feedback = ""
    state.paused_tool_data = None
    state.messages.append({"role": "user", "content": feedback})
    state.events.append(f"data: {json.dumps({'type': 'resume_rejected', 'feedback': feedback, 'run_id': state.run_id})}")
    return state


async def parallel_sub_agents_node(state: AgentState) -> AgentState:
    state.phase = AgentPhase.THINKING
    if not state.parallel_sub_agents:
        state.parallel_results = []
        return state

    state.events.append(f"data: {json.dumps({'type': 'parallel_start', 'run_id': state.run_id, 'count': len(state.parallel_sub_agents)})}")
    tasks = []
    for i, cfg in enumerate(state.parallel_sub_agents):
        payload = dict(cfg)
        payload["index"] = i
        tasks.append(_run_sub_agent(payload))
    state.parallel_results = list(await asyncio.gather(*tasks))
    state.events.append(f"data: {json.dumps({'type': 'parallel_complete', 'run_id': state.run_id, 'count': len(state.parallel_results)})}")
    return state


async def async_pause_node(state: AgentState) -> AgentState:
    return await pause_node(state)


async def async_resume_node(state: AgentState) -> AgentState:
    return await resume_node(state)


async def async_parallel_sub_agents_node(state: AgentState) -> AgentState:
    return await parallel_sub_agents_node(state)


def pause_node_sync(state: AgentState) -> AgentState:
    return state


def resume_node_sync(state: AgentState) -> AgentState:
    return state


def parallel_sub_agents_node_sync(state: AgentState) -> AgentState:
    return state


def setup_node(state: AgentState) -> AgentState:
    return state


def think_node(state: AgentState) -> AgentState:
    state.phase = AgentPhase.THINKING
    return state


def tool_call_node(state: AgentState) -> AgentState:
    state.phase = AgentPhase.TOOL_CALLING
    return state


def verify_node(state: AgentState) -> AgentState:
    state.phase = AgentPhase.VERIFYING
    return state


def plan_node(state: AgentState) -> AgentState:
    state.phase = AgentPhase.THINKING
    return state


def route_node(state: AgentState) -> AgentState:
    return state


def finish_node(state: AgentState) -> AgentState:
    state.phase = AgentPhase.FINISHED
    return state


def force_answer_node(state: AgentState) -> AgentState:
    return state
