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
import logging
import time

from core.agents._sub_agent_base import AgentResult, SubAgent

logger = logging.getLogger("jarvis.agents.forge")

try:
    from smolagents import CodeAgent, LiteLLMModel
    _SMOLAGENTS_AVAILABLE = True
except ImportError:
    _SMOLAGENTS_AVAILABLE = False
    logger.warning("smolagents not installed. Using standard generation for FORGE.")

def _forge_prompt(mode: str, lang: str = "auto") -> str:
    lang_str = "auto-detect from context" if lang == "auto" else lang
    base = (
        "You are FORGE, a production code generation sub-agent inside Jarvis — "
        "Pavan's personal AI OS built on FastAPI + Ollama + RTX 4050 local inference. "
    )
    modes = {
        "generate": (
            f"{base}Your role: generate clean, production-grade, fully-functional code. "
            f"Language: {lang_str}. "
            "Always output: working code with comments, brief usage example, "
            "and one-line note on potential edge cases. No placeholders. No TODOs. Real code only."
        ),
        "debug": (
            f"{base}Your role: identify and fix bugs with surgical precision. Language: {lang_str}. "
            "Output: 1) Bug Report (root cause in one sentence), 2) Fixed Code (complete, runnable), "
            "3) Explanation of fix, 4) Test case to verify. Be a debugger, not a teacher."
        ),
        "refactor": (
            f"{base}Your role: improve code quality, structure, and performance. Language: {lang_str}. "
            "Output: Refactored code + diff-style summary of changes (what changed and why). "
            "Prioritize: readability, performance, Pythonic/idiomatic style, reduced complexity. No feature changes."
        ),
        "explain": (
            f"{base}Your role: explain code deeply and clearly. Language: {lang_str}. "
            "Output: 1) What it does (one sentence), 2) How it works (step-by-step with line references), "
            "3) Time/Space complexity if relevant, 4) Gotchas or non-obvious behavior. Write for a senior engineer."
        ),
    }
    return modes.get(mode, modes["generate"])


class ForgeAgent(SubAgent):
    NAME = "FORGE"
    DESCRIPTION = "Production-grade code generation, debugging, refactoring, and documentation"
    DEFAULT_MODE = "generate"
    AVAILABLE_MODES = ["generate", "debug", "refactor", "doc"]
    MODEL_GROUP = "code"
    MAX_TOKENS = 3000

    def get_system_prompt(self, mode: str) -> str:
        return _forge_prompt(mode, getattr(self, "_lang", "auto"))

    async def run(self, task: str, mode: str | None = None, **kwargs) -> AgentResult:
        mode = mode or self.DEFAULT_MODE
        self._lang = kwargs.get("lang", "auto")

        # 1. Integration: smolagents CodeAgent loop
        if _SMOLAGENTS_AVAILABLE and mode in ("generate", "debug"):
            self.status = "running"
            start_time = time.time()

            try:
                # Use smolagents for bulletproof code execution/generation
                import importlib as _il
                _llm_router = _il.import_module("core.llm_router")
                model_name = _llm_router.get_router_model("code") # Usually qwen2.5-coder

                # Build smolagents compatible model
                # Note: smolagents LiteLLMModel works with Ollama prefixes
                smol_model = LiteLLMModel(model_id=f"ollama/{model_name}")

                agent = CodeAgent(
                    tools=[], # Can add more tools here later
                    model=smol_model,
                    add_base_tools=True,
                    max_steps=5
                )

                logger.info(f"[{self.NAME}:{self.id}] Running smolagents loop for {mode}...")
                # CodeAgent.run is synchronous in some versions, check if it needs thread offloading
                # For this implementation, we assume a modern async-friendly version or wrap it
                result_content = agent.run(f"{_forge_prompt(mode, self._lang)}\n\nTask: {task}")

                self._result = AgentResult(
                    agent_id=self.id,
                    agent_name=self.NAME,
                    mode=mode,
                    input=task,
                    output=str(result_content),
                    success=True,
                    duration_s=time.time() - start_time,
                    token_estimate=0,
                )
                self.status = "done"
                return self._result
            except Exception as e:
                logger.error(f"[{self.NAME}:{self.id}] smolagents loop failed: {e}")
                # Fall back to standard generation

        # 2. Fallback: Standard generation via SubAgent.run
        return await super().run(task, mode=mode, **kwargs)

    def _build_user_content(self, task: str, mode: str, **kwargs) -> str:
        self._lang = kwargs.get("lang", "auto")
        return task

