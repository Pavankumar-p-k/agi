# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
agent_loop.py

Streaming agent loop for odysseus-ui.
Delegates to a StateGraph for execution.
Preserves the exact same stream_agent_loop signature and SSE output format.
"""

import logging
from collections.abc import AsyncGenerator

from core.graph import build_default_graph
from core.graph.state import AgentState
from core.tools._constants import MAX_AGENT_ROUNDS

logger = logging.getLogger(__name__)


async def stream_agent_loop(
    endpoint_url: str,
    model: str,
    messages: list[dict],
    headers: dict | None = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    prompt_type: str | None = None,
    max_rounds: int = MAX_AGENT_ROUNDS,
    max_tool_calls: int = 0,
    context_length: int = 0,
    active_document=None,
    session_id: str | None = None,
    disabled_tools: set[str] | None = None,
    owner: str | None = None,
    relevant_tools: set[str] | None = None,
    fallbacks: list[tuple] | None = None,
    _is_teacher_run: bool = False,
    pause_before_effectful: bool = False,
) -> AsyncGenerator[str, None]:
    """Streaming agent loop generator.

    Yields SSE events:
      - data: {"delta": "text"}                             (text chunks)
      - data: {"type": "tool_start", "tool": "...", ...}    (before execution)
      - data: {"type": "tool_output", "tool": "...", ...}   (after execution)
      - data: {"type": "agent_step", "round": N}            (next round)
      - data: {"type": "metrics", "data": {...}}            (final metrics)
      - data: [DONE]                                        (end)
    """
    graph = build_default_graph()
    state = AgentState(
        endpoint_url=endpoint_url,
        model=model,
        messages=messages,
        headers=headers or {},
        temperature=temperature,
        max_tokens=max_tokens,
        prompt_type=prompt_type,
        max_rounds=max_rounds or MAX_AGENT_ROUNDS,
        max_tool_calls=max_tool_calls,
        context_length=context_length,
        active_document=active_document,
        session_id=session_id,
        disabled_tools=disabled_tools,
        owner=owner,
        relevant_tools=relevant_tools,
        fallbacks=list(fallbacks or []),
        _is_teacher_run=_is_teacher_run,
        pause_before_effectful=pause_before_effectful,
    )
    async for event in graph.execute(state):
        yield event
