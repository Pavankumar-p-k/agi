from __future__ import annotations

import json
from typing import Any, Iterable
from urllib import error, request

from ..runtime.logger import get_logger
from .base import ModelRequest

logger = get_logger("jarvis_os.models.rest")


class RestModelAdapter:
    name = "rest"

    def __init__(self, config: Any) -> None:
        self.config = config
        self.base_url = getattr(config, "model_api_base_url", "").rstrip("/")
        self.generate_path = getattr(config, "model_api_generate_path", "/generate")
        self.stream_path = getattr(config, "model_api_stream_path", self.generate_path)
        self.status_path = getattr(config, "model_api_status_path", "/health")
        self.models_path = getattr(config, "model_api_models_path", "/models")

    def route(self, task: str) -> str:
        return self.config.default_models.get(task, self.config.default_models["chat"])

    def status(self) -> dict[str, Any]:
        if not self.base_url:
            return {"ready": False, "provider": self.name, "error": "model_api_base_url not configured", "models": []}
        models = []
        status_payload: dict[str, Any] = {}
        try:
            status_payload = self._get_json(self.status_path)
        except Exception as exc:
            return {"ready": False, "provider": self.name, "error": str(exc), "models": []}
        try:
            models_payload = self._get_json(self.models_path)
            models = self._extract_models(models_payload)
        except Exception:
            models = self._extract_models(status_payload)
        return {
            "ready": True,
            "provider": self.name,
            "base_url": self.base_url,
            "models": models,
            "raw_status": status_payload,
        }

    def generate(self, request_data: ModelRequest) -> dict[str, Any]:
        if not self.base_url:
            return {"ok": False, "provider": self.name, "model": request_data.model or self.route(request_data.task), "error": "model_api_base_url not configured"}
        payload = self._payload(request_data, stream=False)
        try:
            response = self._post_json(self.generate_path, payload, timeout_s=float(request_data.options.get("timeout_s", 120)))
            return {
                "ok": True,
                "provider": self.name,
                "model": payload["model"],
                "response": self._extract_response_text(response),
                "raw": response,
            }
        except Exception as exc:
            logger.debug("REST model request failed: %s", exc)
            return {"ok": False, "provider": self.name, "model": payload["model"], "error": str(exc)}

    def stream(self, request_data: ModelRequest) -> Iterable[dict[str, Any]]:
        if not self.base_url:
            yield {
                "ok": False,
                "provider": self.name,
                "model": request_data.model or self.route(request_data.task),
                "done": True,
                "error": "model_api_base_url not configured",
            }
            return
        payload = self._payload(request_data, stream=True)
        req = request.Request(
            f"{self.base_url}{self.stream_path}",
            data=json.dumps(payload).encode("utf-8"),
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
                    if line.startswith("data:"):
                        line = line[5:].strip()
                    if line == "[DONE]":
                        yield {"ok": True, "provider": self.name, "model": payload["model"], "done": True}
                        return
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        yield {
                            "ok": True,
                            "provider": self.name,
                            "model": payload["model"],
                            "chunk": line,
                            "done": False,
                        }
                        continue
                    yield {
                        "ok": True,
                        "provider": self.name,
                        "model": payload["model"],
                        "chunk": self._extract_response_text(item),
                        "done": bool(item.get("done", False)),
                        "raw": item,
                    }
        except Exception as exc:
            logger.debug("REST model stream failed: %s", exc)
            yield {"ok": False, "provider": self.name, "model": payload["model"], "done": True, "error": str(exc)}

    def _payload(self, request_data: ModelRequest, *, stream: bool) -> dict[str, Any]:
        payload = {
            "model": request_data.model or self.route(request_data.task),
            "prompt": request_data.prompt,
            "system": request_data.system,
            "task": request_data.task,
            "stream": stream,
            "options": dict(request_data.options),
        }
        return payload

    def _get_json(self, path: str) -> dict[str, Any]:
        with request.urlopen(f"{self.base_url}{path}", timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    def _post_json(self, path: str, payload: dict[str, Any], *, timeout_s: float = 120) -> dict[str, Any]:
        req = request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=timeout_s) as response:
            return json.loads(response.read().decode("utf-8"))

    def _extract_models(self, payload: dict[str, Any]) -> list[str]:
        if isinstance(payload.get("models"), list):
            models = payload["models"]
            if models and isinstance(models[0], dict):
                return [str(item.get("name", "")) for item in models if item.get("name")]
            return [str(item) for item in models]
        if payload.get("model"):
            return [str(payload["model"])]
        return []

    def _extract_response_text(self, payload: dict[str, Any]) -> str:
        for key in ("response", "text", "content", "message"):
            value = payload.get(key)
            if value:
                return str(value)
        return ""
