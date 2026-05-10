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
            # Ollama failed; use deterministic fallback for planning or simple response
            if task.lower() in {"planning", "plan", "goal", "task decomposition", "break down"}:
                return "[{\"tool\": \"code_agent\", \"args\": {\"task\": \"Fallback: please execute goal manually\"}}]"
            return "Fallback response: unable to call model"

    def status(self) -> dict:
        return self.client.status()