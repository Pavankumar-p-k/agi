"""core.model_providers.groq — cloud Groq provider (OpenAI-compatible API)."""
from __future__ import annotations

import os
import time
from typing import Any, Optional

from core.model_providers.base import ModelProvider, ModelResult, ProviderState, ProviderStatus

DEFAULT_MODEL = "llama-3.3-70b-versatile"
_BASE = "https://api.groq.com/openai/v1"


class GroqProvider(ModelProvider):
    provider_id = "groq"
    local = False

    def __init__(self, base_url: str = "", model: str = "", **kwargs: Any) -> None:
        super().__init__(base_url=base_url or _BASE, model=model or DEFAULT_MODEL, **kwargs)

    @staticmethod
    def api_key() -> str:
        return os.getenv("GROQ_API_KEY", "")

    def health(self) -> ProviderStatus:
        status = ProviderStatus(provider=self.provider_id)
        if not self.api_key():
            status.error = "GROQ_API_KEY not set"
            status.state = ProviderState.DISABLED
            return status
        status.available = True
        status.healthy = True
        status.state = ProviderState.HEALTHY
        return status

    def complete(
        self,
        prompt: str,
        *,
        system: str = "",
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        model: str = "",
        **kwargs: Any,
    ) -> ModelResult:
        started = time.perf_counter()
        model_ref = model or self.model
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload: dict[str, Any] = {
            "model": model_ref,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = int(max_tokens)
        try:
            import httpx

            with httpx.Client(timeout=120.0) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key()}"},
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
            usage = data.get("usage", {}) or {}
            return ModelResult(
                success=True,
                text=str(((data.get("choices") or [{}])[0].get("message") or {}).get("content", "")),
                model=model_ref,
                tokens_used=int(usage.get("total_tokens", 0) or 0),
                latency_ms=round((time.perf_counter() - started) * 1000.0, 1),
            )
        except Exception as exc:  # noqa: BLE001
            return ModelResult(
                success=False,
                error=str(exc),
                model=model_ref,
                latency_ms=round((time.perf_counter() - started) * 1000.0, 1),
            )


__all__ = ["GroqProvider"]
