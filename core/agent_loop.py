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
Now uses the canonical 19-stage pipeline (core/pipeline/process_message).
Every request flows through: Receive → Auth → Tenant → AuthZ → RateLimit →
Intent → Context → Knowledge → Reasoning → Planner → PlanValidator →
CapabilitySelection → Execution → Verification → Epistemic → Reflection →
Learning → PolicyOptimization → Memory → Metrics → Explainability → Formatter.
Preserves the exact same stream_agent_loop signature and SSE output format.
Legacy direct-graph execution is preserved as a safe fallback.
"""

import json
import logging
from collections.abc import AsyncGenerator

from core.graph import build_default_graph
from core.graph.state import AgentState
from core.pipeline import process_message
from core.pipeline.messages import Request
from core.tools._constants import MAX_AGENT_ROUNDS

logger = logging.getLogger(__name__)

# Metrics for fallback tracking
_fallback_count = 0


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
    mode: str | None = None,
    project_context: dict | None = None,
    _disable_pipeline: bool = False,
) -> AsyncGenerator[str, None]:
    """Streaming agent loop generator.

    Uses the canonical pipeline (core/pipeline/process_message). Falls back
    to direct graph execution if the pipeline is disabled or fails.

    Yields SSE events:
      - data: {"delta": "text"}                             (text chunks)
      - data: {"type": "tool_start", "tool": "...", ...}    (before execution)
      - data: {"type": "tool_output", "tool": "...", ...}   (after execution)
      - data: {"type": "agent_step", "round": N}            (next round)
      - data: {"type": "metrics", "data": {...}}            (final metrics)
      - data: [DONE]                                        (end)
    """
    # Try the canonical pipeline first
    if not _disable_pipeline:
        try:
            # Extract user goal from messages
            user_text = ""
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        for part in content:
                            if isinstance(part, dict) and part.get("type") == "text":
                                user_text = part["text"]
                                break
                    else:
                        user_text = str(content)
                    break

            request = Request(
                text=user_text,
                transport="rest",  # Could be websocket, cli, etc.
                user_id=owner or "developer",
                session_id=session_id,
                metadata={
                    "endpoint_url": endpoint_url,
                    "model": model,
                    "headers": headers or {},
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "prompt_type": prompt_type,
                    "max_rounds": max_rounds,
                    "max_tool_calls": max_tool_calls,
                    "context_length": context_length,
                    "active_document": active_document,
                    "disabled_tools": list(disabled_tools or []),
                    "relevant_tools": list(relevant_tools or []),
                    "fallbacks": fallbacks or [],
                    "_is_teacher_run": _is_teacher_run,
                    "pause_before_effectful": pause_before_effectful,
                    "mode": mode,
                    "project_context": project_context or {},
                },
            )

            response = await process_message(request)

            if response.error:
                logger.warning("[agent_loop] Pipeline returned error: %s", response.error)
                raise RuntimeError(response.error)

            # Yield the response as SSE events matching the expected format
            if response.text:
                # Stream as chunks (single chunk for now, could be split)
                yield f'data: {{"delta": {json.dumps(response.text)}}}\n\n'

            # Yield metrics
            if response.metadata:
                yield f'data: {{"type": "metrics", "data": {json.dumps(response.metadata)}}}\n\n'

            yield "data: [DONE]\n\n"
            return

        except Exception as e:
            global _fallback_count
            _fallback_count += 1
            logger.warning("[agent_loop] Pipeline failed (fallback #%d), falling back to legacy: %s", _fallback_count, e)

    # Legacy fallback: direct graph execution (unchanged behavior)
    graph = build_default_graph()
    state = AgentState(
        endpoint_url=endpoint_url,
        model=model,
        messages=messages,
        headers=headers or {},
        temperature=temperature,
        max_tokens=max_tokens,
        prompt_type=mode or prompt_type,
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
        mode=mode,
        project_context=project_context,
    )
    async for event in graph.execute(state):
        yield event


def get_fallback_count() -> int:
    """Return the number of times the legacy fallback was triggered."""
    return _fallback_count


def reset_fallback_count() -> None:
    """Reset the fallback counter."""
    global _fallback_count
    _fallback_count = 0
