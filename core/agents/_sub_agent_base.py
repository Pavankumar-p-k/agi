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
"""Base class for all JARVIS sub-agents. Moved from core/sub_agents/base_agent.py."""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal

logger = logging.getLogger("jarvis.agents")

@dataclass
class AgentResult:
    agent_id: str
    agent_name: str
    mode: str
    input: str
    output: str
    success: bool
    duration_s: float
    token_estimate: int
    error: str | None = None
    outcome: str | None = None # ok | error | timeout | killed
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "mode": self.mode,
            "input": self.input[:200] + "..." if len(self.input) > 200 else self.input,
            "output": self.output,
            "success": self.success,
            "duration_s": round(self.duration_s, 2),
            "token_estimate": self.token_estimate,
            "error": self.error,
            "outcome": self.outcome,
            "metadata": self.metadata,
        }


class SubAgent(ABC):
    """Base class for all JARVIS sub-agents."""

    NAME: str = "BASE"
    DESCRIPTION: str = ""
    DEFAULT_MODE: str = "default"
    AVAILABLE_MODES: list[str] = ["default"]
    MODEL_GROUP: str = "chat"
    MAX_TOKENS: int = 2000

    def __init__(self):
        self.id = str(uuid.uuid4())[:8]
        self.status: Literal["idle", "running", "done", "failed"] = "idle"
        self._result: AgentResult | None = None

    @abstractmethod
    def get_system_prompt(self, mode: str) -> str:
        """Return the system prompt for this agent and mode."""
        ...

    async def run(self, task: str, mode: str | None = None, *, cancel_event: asyncio.Event | None = None, **kwargs) -> AgentResult:
        mode = mode or self.DEFAULT_MODE
        if mode not in self.AVAILABLE_MODES:
            mode = self.DEFAULT_MODE

        self.status = "running"
        start = time.time()

        if cancel_event and cancel_event.is_set():
            return self._cancel_result(task, mode, start)

        system = self.get_system_prompt(mode)
        user_content = self._build_user_content(task, mode, **kwargs)

        try:
            logger.info(f"[{self.NAME}:{self.id}] Starting mode={mode} task={task[:60]}...")

            if cancel_event and cancel_event.is_set():
                return self._cancel_result(task, mode, start)

            # Use the canonical pipeline for LLM completion
            from core.pipeline.internal_client import prompt as llm_prompt
            combined = f"{system}\n\n{user_content}" if system else user_content

            if cancel_event and cancel_event.is_set():
                return self._cancel_result(task, mode, start)

            output = await llm_prompt(combined)

            if cancel_event and cancel_event.is_set():
                return self._cancel_result(task, mode, start)

            from core.model_context import estimate_tokens
            tokens = estimate_tokens([{"role": "assistant", "content": output}])

            self._result = AgentResult(
                agent_id=self.id,
                agent_name=self.NAME,
                mode=mode,
                input=task,
                output=output,
                success=True,
                duration_s=time.time() - start,
                token_estimate=tokens,
            )
            self.status = "done"
            logger.info(f"[{self.NAME}:{self.id}] Done in {self._result.duration_s:.1f}s")

            # Phase 3: Emit hook
            try:
                from core.event_bus import PluginEventBus
                asyncio.create_task(PluginEventBus.instance().emit("on_agent_reply", result=self._result))
            except Exception as hook_exc:
                logger.debug("on_agent_reply hook failed: %s", hook_exc)

        except Exception as e:
            logger.error(f"[{self.NAME}:{self.id}] Error: {e}")
            self._result = AgentResult(
                agent_id=self.id, agent_name=self.NAME, mode=mode,
                input=task, output="", success=False,
                duration_s=time.time() - start, token_estimate=0, error=str(e),
            )
            self.status = "failed"

        return self._result

    def _cancel_result(self, task: str, mode: str, start: float) -> AgentResult:
        self.status = "failed"
        return AgentResult(
            agent_id=self.id, agent_name=self.NAME, mode=mode,
            input=task, output="", success=False,
            duration_s=time.time() - start, token_estimate=0, error="Cancelled by user",
            outcome="killed" # type: ignore
        )

    def _build_user_content(self, task: str, mode: str, **kwargs) -> str:
        return task

    @property
    def result(self) -> AgentResult | None:
        return self._result

    def info(self) -> dict:
        return {
            "id": self.id,
            "name": self.NAME,
            "description": self.DESCRIPTION,
            "status": self.status,
            "modes": self.AVAILABLE_MODES,
            "default_mode": self.DEFAULT_MODE,
        }
