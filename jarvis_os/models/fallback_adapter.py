from __future__ import annotations

from typing import Any, Iterable

from .base import ModelRequest


class FallbackModelAdapter:
    name = "fallback"

    def __init__(self, config: Any) -> None:
        self.config = config

    def route(self, task: str) -> str:
        return self.config.default_models.get(task, self.config.default_models["chat"])

    def status(self) -> dict[str, Any]:
        return {
            "ready": True,
            "provider": self.name,
            "message": "Limited offline fallback mode enabled.",
            "models": [self.route("chat")],
        }

    def generate(self, request_data: ModelRequest) -> dict[str, Any]:
        prompt = str(request_data.prompt or "").strip().lower()
        if any(token in prompt for token in ("time", "clock", "what time", "current time")):
            from datetime import datetime

            return {
                "ok": True,
                "provider": self.name,
                "model": request_data.model or self.route(request_data.task),
                "response": f"The current time is {datetime.now().strftime('%I:%M %p')}.",
            }

        if any(token in prompt for token in ("hello", "hi", "hey", "greetings")):
            return {
                "ok": True,
                "provider": self.name,
                "model": request_data.model or self.route(request_data.task),
                "response": "Hello! I'm JARVIS in limited offline mode. I can still help with simple questions.",
            }

        if any(token in prompt for token in ("weather", "forecast", "rain", "sunny", "cloudy")):
            return {
                "ok": True,
                "provider": self.name,
                "model": request_data.model or self.route(request_data.task),
                "response": "I need a model backend or internet access to provide weather details. Please start Ollama or configure a model API.",
            }

        return {
            "ok": True,
            "provider": self.name,
            "model": request_data.model or self.route(request_data.task),
            "response": "I'm currently running in limited offline mode. Start Ollama or configure a model API to enable full AI capabilities.",
        }

    def stream(self, request_data: ModelRequest) -> Iterable[dict[str, Any]]:
        result = self.generate(request_data)
        yield {
            "ok": True,
            "provider": self.name,
            "model": result["model"],
            "chunk": result["response"],
            "done": True,
        }
