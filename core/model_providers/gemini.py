"""core.model_providers.gemini — cloud Google Gemini provider.

Uses the generativelanguage REST API: POST
/v1beta/models/{model}:generateContent?key=API_KEY
"""
from __future__ import annotations

import os
import time
from typing import Any, Optional

from core.model_providers.base import ModelProvider, ModelResult, ProviderState, ProviderStatus

DEFAULT_MODEL = "gemini-2.5-flash"
_BASE = "https://generativelanguage.googleapis.com"


class GeminiProvider(ModelProvider):
    provider_id = "gemini"
    local = False

    def __init__(self, base_url: str = "", model: str = "", **kwargs: Any) -> None:
        super().__init__(base_url=base_url or _BASE, model=model or DEFAULT_MODEL, **kwargs)

    @staticmethod
    def api_key() -> str:
        return os.getenv("GEMINI_API_KEY", "")

    def health(self) -> ProviderStatus:
        status = ProviderStatus(provider=self.provider_id)
        if not self.api_key():
            status.error = "GEMINI_API_KEY not set"
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
        payload: dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature},
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        if max_tokens is not None:
            payload["generationConfig"]["maxOutputTokens"] = int(max_tokens)
        try:
            import httpx

            with httpx.Client(timeout=120.0) as client:
                response = client.post(
                    f"{self.base_url}/v1beta/models/{model_ref}:generateContent",
                    params={"key": self.api_key()},
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
            candidates = data.get("candidates") or [{}]
            parts = (candidates[0].get("content") or {}).get("parts") or []
            text = "".join(str(part.get("text", "")) for part in parts)
            return ModelResult(
                success=True,
                text=text,
                model=model_ref,
                latency_ms=round((time.perf_counter() - started) * 1000.0, 1),
            )
        except Exception as exc:  # noqa: BLE001
            return ModelResult(
                success=False,
                error=str(exc),
                model=model_ref,
                latency_ms=round((time.perf_counter() - started) * 1000.0, 1),
            )


__all__ = ["GeminiProvider"]
