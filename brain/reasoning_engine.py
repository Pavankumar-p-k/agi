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

from __future__ import annotations

import inspect
import json
import logging
import os
import re
import time
from typing import Callable

import httpx

from core.config_registry import config as _jarvis_config
from core.llm_router import complete
from core.schemas import ReasonResult

logger = logging.getLogger(__name__)

REASONING_SYSTEM = (
    "You are a reasoning engine. Think step by step inside <think> tags.\n"
    "Output your final answer inside <answer> tags.\n"
    "Be precise, logical, and consider edge cases."
)

REASONING_TEMPLATE = """Goal: {goal}

Context:
{context}

Think step by step inside <think> tags, then provide your final answer inside <answer> tags.

<think>Plan:
</think>
<think>Analysis:
</think>
<think>Critique:
</think>
<answer>
</answer>"""


class ReasoningEngine:
    def __init__(self):
        self._warmed = False
        self._trace_listeners: list[Callable] = []
        self._http = httpx.AsyncClient(timeout=3)

    @property
    def _fallback_group(self) -> str:
        return _jarvis_config.get("model_groups.reasoning_group", "chat")

    @property
    def _ollama_url(self) -> str:
        return _jarvis_config.get("ollama.base_url", os.getenv("OLLAMA_HOST", "http://localhost:11434"))

    def _get_timeout(self, default: int = 60) -> int:
        return _jarvis_config.get("brain.reasoning_timeout", default)

    # ---- Trace emission (for dashboard) ----

    def on_trace(self, listener: Callable):
        self._trace_listeners.append(listener)

    async def _emit_trace(self, thinking: str):
        for listener in self._trace_listeners:
            try:
                if inspect.iscoroutinefunction(listener):
                    await listener(thinking)
                else:
                    listener(thinking)
            except Exception as e:
                logger.exception("[Reasoning] Trace listener failed: %s", e)

    # ---- Core ----

    async def warmup(self):
        if self._warmed:
            return
        try:
            result = await complete("reasoning", [
                {"role": "system", "content": "Respond with OK."},
                {"role": "user", "content": "ping"},
            ], timeout=10)
            if result.is_ok():
                self._warmed = True
        except Exception as e:
            logger.exception("[Reasoning] warmup failed: %s", e)
            self._warmed = False

    async def _ollama_alive(self) -> bool:
        try:
            r = await self._http.get(f"{self._ollama_url}/api/tags")
            return r.status_code == 200
        except Exception as e:
            logger.debug("[Reasoning] _ollama_alive failed: %s", e)
            return False

    def _parse_cot(self, raw: str) -> tuple[str, str]:
        think = re.search(r"<think>(.*?)</think>", raw, re.DOTALL)
        answer = re.search(r"<answer>(.*?)</answer>", raw, re.DOTALL)
        thinking = think.group(1).strip() if think else ""
        final = answer.group(1).strip() if answer else raw.strip()
        return thinking, final

    async def reason(
        self,
        goal: str,
        context: str = "",
        system_override: str | None = None,
        temperature: float | None = None,
    ) -> ReasonResult:
        if self._warmed:
            alive = await self._ollama_alive()
            if not alive:
                self._warmed = False

        system = system_override or REASONING_SYSTEM
        prompt = REASONING_TEMPLATE.replace("{goal}", goal).replace("{context}", context)
        model_group = self._fallback_group

        try:
            raw_r = await complete(
                model_group,
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                timeout=self._get_timeout(60),
            )
            raw = raw_r.unwrap_or("")
        except Exception as e:
            logger.exception("[Reasoning] First complete call failed: %s", e)
            if model_group != self._fallback_group:
                model_group = self._fallback_group
                try:
                    raw_r = await complete(
                        model_group,
                        [
                            {"role": "system", "content": system},
                            {"role": "user", "content": prompt},
                        ],
                        timeout=self._get_timeout(120),
                    )
                    raw = raw_r.unwrap_or("")
                except Exception as e:
                    logger.exception("[Reasoning] Fallback complete call failed: %s", e)
                    return ReasonResult(
                        answer="I'm having trouble reasoning right now.",
                        confidence=0.0,
                        model_group="none",
                    )
            else:
                return ReasonResult(
                    answer="I'm having trouble reasoning right now.",
                    confidence=0.0,
                    model_group="none",
                )

        if model_group == "reasoning":
            self._warmed = True

        thinking, answer = self._parse_cot(raw)

        if thinking:
            await self._emit_trace(thinking)

        # Heuristic confidence
        trace_lines = [l for l in thinking.split("\n") if l.strip()]
        confidence = min(1.0, 0.3 + (len(trace_lines) * 0.15) + (len(answer) / 500) * 0.2)

        return ReasonResult(
            answer=answer,
            thinking_trace=thinking,
            confidence=round(confidence, 2),
            steps_taken=len(trace_lines),
            model_group=model_group,
        )


reasoning_engine = ReasoningEngine()
