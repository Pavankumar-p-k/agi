from __future__ import annotations

import json
from typing import Any, Iterable
from urllib import error, request

from ..runtime.logger import get_logger
from .base import ModelRequest

logger = get_logger("jarvis_os.models.ollama")


class OllamaRouter:
    name = "ollama"

    def __init__(self, config: Any) -> None:
        self.config = config
        self.base_url = config.ollama_base_url.rstrip("/")

    def route(self, task: str) -> str:
        return self.config.default_models.get(task, self.config.default_models["chat"])

    def status(self) -> dict[str, Any]:
        url = f"{self.base_url}/api/tags"
        try:
            with request.urlopen(url, timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return {
                "ready": True,
                "provider": self.name,
                "base_url": self.base_url,
                "models": [item.get("name", "") for item in payload.get("models", [])],
            }
        except Exception as exc:
            return {"ready": False, "provider": self.name, "base_url": self.base_url, "error": str(exc), "models": []}

    def generate(self, request_data: ModelRequest | str, task: str = "chat", system: str = "") -> dict[str, Any]:
        if isinstance(request_data, ModelRequest):
            model_request = request_data
        else:
            model_request = ModelRequest(prompt=request_data, task=task, system=system)
        model = model_request.model or self.route(model_request.task)
        body = {
            "model": model,
            "prompt": model_request.prompt,
            "system": model_request.system,
            "stream": False,
            "options": dict(model_request.options),
        }
        timeout_s = float(model_request.options.get("timeout_s", 60))
        data = json.dumps(body).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=timeout_s) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return {"ok": True, "provider": self.name, "model": model, "response": payload.get("response", "")}
        except Exception as exc:
            logger.debug("Ollama request failed: %s", exc)
            return {"ok": False, "provider": self.name, "model": model, "error": str(exc)}

    def stream(self, request_data: ModelRequest) -> Iterable[dict[str, Any]]:
        model = request_data.model or self.route(request_data.task)
        body = {
            "model": model,
            "prompt": request_data.prompt,
            "system": request_data.system,
            "stream": True,
            "options": dict(request_data.options),
        }
        req = request.Request(
            f"{self.base_url}/api/generate",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        timeout_s = float(request_data.options.get("timeout_s", 120))
        try:
            with request.urlopen(req, timeout=timeout_s) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        yield {"ok": True, "provider": self.name, "model": model, "chunk": line, "done": False}
                        continue
                    yield {
                        "ok": True,
                        "provider": self.name,
                        "model": model,
                        "chunk": payload.get("response", ""),
                        "done": bool(payload.get("done", False)),
                        "raw": payload,
                    }
        except Exception as exc:
            logger.debug("Ollama stream failed: %s", exc)
            yield {"ok": False, "provider": self.name, "model": model, "done": True, "error": str(exc)}
