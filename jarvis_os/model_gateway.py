"""Local-first model gateway for Ollama-backed reasoning and routing."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional
from urllib import request

logger = logging.getLogger("jarvis.os.models")


class LocalModelGateway:
    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self.base_url = (self.config.get("base_url") or os.getenv("OLLAMA_URL") or "http://127.0.0.1:11434").rstrip("/")
        self.task_routes = {
            "chat": self.config.get("chat_model", "qwen2.5:7b"),
            "reasoning": self.config.get("reasoning_model", "deepseek-r1:1.5b"),
            "coding": self.config.get("coding_model", "qwen2.5-coder:3b"),
            "vision": self.config.get("vision_model", "moondream"),
            "planning": self.config.get("planning_model", "qwen3:4b"),
        }

    async def initialize(self):
        logger.info("[LocalModelGateway] initialized base_url=%s", self.base_url)

    async def shutdown(self):
        return None

    def route_for_task(self, task: str = "chat") -> str:
        return self.task_routes.get(task, self.task_routes["chat"])

    def list_models(self) -> List[Dict[str, Any]]:
        payload = self._get_json("/api/tags")
        models = payload.get("models", [])
        return [
            {
                "name": model.get("name", ""),
                "size": model.get("size", 0),
                "modified_at": model.get("modified_at", ""),
            }
            for model in models
        ]

    def status(self) -> Dict[str, Any]:
        try:
            models = self.list_models()
            return {
                "ready": True,
                "base_url": self.base_url,
                "models": models,
                "routes": dict(self.task_routes),
            }
        except Exception as exc:
            return {
                "ready": False,
                "base_url": self.base_url,
                "error": str(exc),
                "routes": dict(self.task_routes),
            }

    def generate(
        self,
        prompt: str,
        task: str = "chat",
        model: str = "",
        system: str = "",
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = {
            "model": model or self.route_for_task(task),
            "prompt": prompt,
            "stream": False,
            "options": options or {},
        }
        if system:
            payload["system"] = system
        try:
            result = self._post_json("/api/generate", payload)
            return {
                "ok": True,
                "model": payload["model"],
                "task": task,
                "response": (result.get("response") or "").strip(),
            }
        except Exception as exc:
            return {
                "ok": False,
                "model": payload["model"],
                "task": task,
                "error": str(exc),
            }

    def _get_json(self, endpoint: str) -> Dict[str, Any]:
        with request.urlopen(f"{self.base_url}{endpoint}", timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    def _post_json(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        req = request.Request(
            f"{self.base_url}{endpoint}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
