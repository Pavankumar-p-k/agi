"""core.model_providers.anthropic — cloud Anthropic (Claude) provider.

Same contract shape as openai.py: env key OPENAI/ANTHROPIC style, honest
health, direct REST call. Message API: POST /v1/messages.
"""
from __future__ import annotations

import os
import time
from typing import Any, Optional

from core.model_providers.base import ModelProvider, ModelResult, ProviderState, ProviderStatus

DEFAULT_MODEL = "claude-sonnet-4-5"
_BASE = "https://api.anthropic.com"
_VERSION = "2023-06-01"


class AnthropicProvider(ModelProvider):
    provider_id = "anthropic"
    local = False

    def __init__(self, base_url: str = "", model: str = "", **kwargs: Any) -> None:
        super().__init__(base_url=base_url or _BASE, model=model or DEFAULT_MODEL, **kwargs)

    @staticmethod
    def api_key() -> str:
        return os.getenv("ANTHROPIC_API_KEY", "")

    def health(self) -> ProviderStatus:
        status = ProviderStatus(provider=self.provider_id)
        if not self.api_key():
            status.error = "ANTHROPIC_API_KEY not set"
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
            "model": model_ref,
            "max_tokens": int(max_tokens if max_tokens is not None else 1024),
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            payload["system"] = system
        try:
            import httpx

            with httpx.Client(timeout=120.0) as client:
                response = client.post(
                    f"{self.base_url}/v1/messages",
                    headers={
                        "x-api-key": self.api_key(),
                        "anthropic-version": _VERSION,
                    },
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
            text = "".join(
                str(block.get("text", ""))
                for block in data.get("content", [])
                if block.get("type") == "text"
            )
            usage = data.get("usage", {}) or {}
            return ModelResult(
                success=True,
                text=text,
                model=model_ref,
                tokens_used=int(usage.get("output_tokens", 0) or 0),
                latency_ms=round((time.perf_counter() - started) * 1000.0, 1),
            )
        except Exception as exc:  # noqa: BLE001
            return ModelResult(
                success=False,
                error=str(exc),
                model=model_ref,
                latency_ms=round((time.perf_counter() - started) * 1000.0, 1),
            )


__all__ = ["AnthropicProvider"]
