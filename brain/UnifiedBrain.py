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

import json
import logging
import threading
from collections.abc import Callable

from core.plugins import plugin_registry
from core.schemas import CritiqueResult, ReasonResult, Step

from .cognitive_patterns import CognitivePatterns
from .epistemic_tagger import EpistemicTagger
from .reasoning_engine import reasoning_engine

logger = logging.getLogger(__name__)


class UnifiedBrain:
    """Unified cognitive core — reasoning, planning, critique, governance."""

    def __init__(self):
        self.reasoning = reasoning_engine
        self.patterns = CognitivePatterns()
        self.tagger = EpistemicTagger()
        self._governor = None
        self._gov_lock = threading.Lock()
        self._trace_listeners: list[Callable] = []

    # ---- Governance (lazy init, thread-safe) ----

    def _init_governor(self):
        if self._governor is not None:
            return
        with self._gov_lock:
            if self._governor is not None:
                return
            try:
                from governance.GovernanceValidator import GovernanceValidator
                validator = GovernanceValidator()
                self._governor = validator
            except ImportError as e:
                logger.warning("Governance modules not available, governor disabled: %s", e)
                self._governor = None

    @property
    def governor(self):
        self._init_governor()
        return self._governor

    # ---- Trace emission (for dashboard WebSocket) ----

    def on_trace(self, listener: Callable):
        self._trace_listeners.append(listener)

    async def _emit_trace(self, thinking: str):
        for listener in self._trace_listeners:
            try:
                import inspect
                if inspect.iscoroutinefunction(listener):
                    await listener(thinking)
                else:
                    listener(thinking)
            except Exception as e:
                logger.exception("Trace listener failed: %s", e)

    # ---- Core methods ----

    async def reason(self, goal: str, context: dict | None = None) -> ReasonResult:
        ctx_str = json.dumps(context or {}, indent=2)
        result = await self.reasoning.reason(goal, ctx_str)
        if result.thinking_trace:
            await self._emit_trace(result.thinking_trace)
        return result

    async def plan(self, goal: str, context: str = "") -> list[Step]:
        raw = await self.patterns.decompose(goal, context)
        conclusion = raw.get("conclusion", "")
        lines = [l.strip() for l in conclusion.split("\n") if l.strip()]
        steps = []
        for i, line in enumerate(lines):
            if line.startswith("-") or line.startswith("*") or line[0].isdigit():
                steps.append(Step(
                    id=f"step_{i}",
                    description=line.lstrip("-*1234567890. "),
                ))
        return steps or [Step(id="step_0", description=conclusion)]

    async def critique(self, output: str, context: str = "") -> CritiqueResult:
        raw = await self.patterns.critique(output, context)
        conclusion = raw.get("conclusion", "")
        trace = raw.get("trace", [])
        flaws = [conclusion] + [t for t in trace if t]
        severity = "major"
        lowered = conclusion.lower()
        if any(w in lowered for w in ["minor", "small", "nitpick", "cosmetic"]):
            severity = "minor"
        elif any(w in lowered for w in ["critical", "severe", "fatal", "broken", "incorrect"]):
            severity = "critical"
        return CritiqueResult(
            flaws=flaws,
            severity=severity,
            revised_output=conclusion,
        )

    async def reflect(self, session: list[dict]) -> str:
        conversation = json.dumps(session, indent=2)
        raw = await self.patterns.reflect(conversation)
        return raw.get("conclusion", "")

    async def three_pass(self, goal: str, context: dict | None = None) -> str:
        for _, result in await plugin_registry.run_hook("before_agent_run", task=goal):
            if result is False:
                return ""

        turn_ctx = {"goal": goal, "context": context or {}}
        r1 = await self.reason(goal, turn_ctx)
        if len(r1.answer) < 200:
            await plugin_registry.run_hook("agent_end", result={"goal": goal, "answer": r1.answer, "pass": 1})
            return r1.answer
        c = await self.critique(r1.answer)
        if c.severity == "minor":
            await plugin_registry.run_hook("agent_end", result={"goal": goal, "answer": r1.answer, "pass": 2})
            return r1.answer
        turn_ctx["flaws"] = c.flaws
        turn_ctx["draft"] = r1.answer
        r3 = await self.reason("Revise this output fixing the flaws listed.", turn_ctx)
        await plugin_registry.run_hook("agent_end", result={"goal": goal, "answer": r3.answer, "pass": 3})
        return r3.answer


unified_brain = UnifiedBrain()
