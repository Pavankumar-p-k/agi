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

from typing import Any
from .ollama_client import OllamaClient
from .config import AIOSConfig


class ModelRouter:
    def __init__(self, config: AIOSConfig | None = None):
        self.config = config or AIOSConfig()
        self.client = OllamaClient(self.config.ollama_host)

    def select_model(self, task: str) -> str:
        task = task.lower()
        if task in {"planning", "plan", "goal", "task decomposition", "break down"}:
            return self.config.planner_model
        if task in {"reasoning", "analysis", "think", "inference"}:
            return self.config.reasoning_model
        if task in {"code", "coding", "dev"}:
            return self.config.coder_model
        if task in {"fast", "small", "quick", "lookup", "fact"}:
            return self.config.lightweight_model
        return self.config.fast_model

    def warmup_models(self) -> dict[str, Any]:
        # Preload useful models by querying Ollama and calling /v1/models. If needed,
        # can call a lightweight prompt for each model to keep in memory.
        status = self.client.status()
        wanted = [
            self.config.planner_model,
            self.config.reasoning_model,
            self.config.coder_model,
            self.config.fast_model,
            self.config.lightweight_model,
        ]
        loaded = []
        for m in wanted:
            if "models" in status and any(str(x).startswith(m) for x in status["models"]):
                loaded.append(m)
        return {"available_models": loaded, "ollama_status": status}

    def generate(self, task: str, prompt: str, max_tokens: int | None = None) -> str:
        model = self.select_model(task)
        try:
            return self.client.generate(model, prompt, max_tokens=max_tokens or self.config.max_response_tokens)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error(f"Ollama call failed: {exc}")
            raise RuntimeError(f"Model generation failed for task '{task}': {exc}") from exc

    def status(self) -> dict:
        return self.client.status()