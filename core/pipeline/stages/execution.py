from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext

logger = logging.getLogger(__name__)


class ProviderManager:
    """Centralized provider selection and fallback.

    .. code-block:: text

        Execution
            │
            ▼
        ProviderManager
            │
            ├──► primary provider  (e.g. OpenAI)
            ├──► secondary provider (e.g. Claude)
            ├──► local fallback     (e.g. Ollama)
            └──► hard fallback      (e.g. rule-based response)

    Every provider call goes through this manager — no route does its own
    fallback.
    """

    def __init__(self) -> None:
        self._providers: list[Provider] = []

    def add_provider(self, provider: Provider, *, position: int | None = None) -> None:
        if position is None:
            self._providers.append(provider)
        else:
            self._providers.insert(position, provider)

    async def execute(self, prompt: str, **kwargs: Any) -> ProviderResult:
        errors: list[str] = []
        for provider in self._providers:
            try:
                return await provider.complete(prompt, **kwargs)
            except Exception as exc:
                logger.warning("Provider %s failed: %s", provider.name, exc)
                errors.append(f"{provider.name}: {exc}")
                continue
        return ProviderResult(
            text="",
            error="All providers failed:\n" + "\n".join(errors),
            provider="none",
        )


@dataclass
class ProviderResult:
    text: str
    error: str | None = None
    provider: str = ""
    tokens: int = 0


class Provider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    async def complete(self, prompt: str, **kwargs: Any) -> ProviderResult:
        ...


class ExecutionStage(PipelineStage):
    """Execute the plan using the ProviderManager.

    This is the **only** stage that calls LLMs.  It owns the
    ``ProviderManager`` which handles model selection, routing, and
    fallback.  No other stage or route calls LLMs directly.
    """

    def __init__(self) -> None:
        self.provider_manager = ProviderManager()

    @property
    def name(self) -> str:
        return "execution"

    def with_default_providers(self) -> ExecutionStage:
        """Register the standard provider chain (cloud → Ollama fallback)."""
        try:
            self.provider_manager.add_provider(LiteLLMProvider())
        except Exception as exc:
            logger.warning("LiteLLM provider unavailable: %s", exc)
        try:
            self.provider_manager.add_provider(OllamaFallbackProvider())
        except Exception as exc:
            logger.warning("Ollama fallback provider unavailable: %s", exc)
        return self

    async def execute(self, context: PipelineContext) -> StageResult:
        prompt = context.raw_input
        if not prompt.strip():
            return StageResult(outcome=StageOutcome.CONTINUE, context=context)

        result = await self.provider_manager.execute(prompt)
        context.execution_state = "completed"
        context.execution_result = {
            "text": result.text,
            "provider": result.provider,
            "tokens": result.tokens,
        }
        if result.error:
            context.error = result.error
            context.execution_state = "failed"
            return StageResult(outcome=StageOutcome.FAIL, context=context, error=result.error)
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)


# ── Concrete provider implementations ──────────────────────────────────────


class LiteLLMProvider(Provider):
    """Primary provider that uses the existing LiteLLM router.

    Wraps ``core.llm_router.get_router().acompletion()`` — the same
    call that all existing routes use.
    """

    @property
    def name(self) -> str:
        return "litellm"

    async def complete(self, prompt: str, **kwargs: Any) -> ProviderResult:
        from core.llm_router import get_router, route_request

        model, tier, processed_query = route_request(prompt)
        model_group = "cloud" if model == "cloud" else "chat"

        messages = [
            {"role": "system", "content": "You are JARVIS, your AI assistant. Be concise."},
            {"role": "user", "content": processed_query},
        ]
        resp = await get_router().acompletion(
            model=model_group,
            messages=messages,
            timeout=kwargs.get("timeout", 60),
        )
        text = resp.choices[0].message.content if hasattr(resp, "choices") else str(resp)
        return ProviderResult(text=text, provider="litellm", tokens=0)


class OllamaFallbackProvider(Provider):
    """Fallback provider that calls Ollama directly via HTTP.

    Used when the primary LiteLLM provider fails.
    """

    @property
    def name(self) -> str:
        return "ollama_fallback"

    async def complete(self, prompt: str, **kwargs: Any) -> ProviderResult:
        import httpx

        from core.llm_router import get_ollama_url, model_for_role

        model_obj = model_for_role("chat")
        url = get_ollama_url(model_obj)
        payload = {
            "model": url.split("/")[-1].split(":")[0] if "/" in url else "llama3.1",
            "messages": [
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "options": {
                "num_predict": 1024,
                "temperature": 0.7,
            },
        }
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{url}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
            text = data.get("message", {}).get("content", "")
            return ProviderResult(text=text, provider="ollama", tokens=0)
