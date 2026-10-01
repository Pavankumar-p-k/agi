"""MultiModalPipeline — routes messages to the right modality providers.

Providers are registered per modality (text, vision, speech-to-text) and tried
in registration order; the first success wins. Text-only messages with no
registered provider fall back to ``_default_complete``, which routes through
``core.llm_router`` (the single LLM gateway).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Optional

from core.multimodal.schema import (
    ImagePart,
    MultiModalMessage,
    TextPart,
)

logger = logging.getLogger(__name__)

_AUDIO_UNAVAILABLE = "[Audio transcription not available]"


@dataclass
class MultiModalResult:
    """Outcome of a multimodal completion."""

    text: str = ""
    error: str = ""
    model: str = ""
    chunks: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.error


class MultiModalPipeline:
    """Modality-aware completion pipeline with explicit fallback chains."""

    def __init__(self) -> None:
        self._text_providers: list[Callable] = []
        self._vision_providers: list[Callable] = []
        self._stt_providers: list[Callable] = []

    # ── registration ─────────────────────────────────────────────────
    def register_text(self, provider: Callable) -> None:
        self._text_providers.append(provider)

    def register_vision(self, provider: Callable) -> None:
        self._vision_providers.append(provider)

    def register_audio_stt(self, provider: Callable) -> None:
        self._stt_providers.append(provider)

    def register_audio(self, provider: Callable) -> None:
        self.register_audio_stt(provider)

    # ── capability queries ───────────────────────────────────────────
    @staticmethod
    def has_images(messages: list) -> bool:
        return any(getattr(m, "has_images", lambda: False)() for m in messages or [])

    @staticmethod
    def has_audio(messages: list) -> bool:
        return any(getattr(m, "has_audio", lambda: False)() for m in messages or [])

    # ── completion ───────────────────────────────────────────────────
    async def complete(self, messages: list) -> MultiModalResult:
        providers = (self._vision_providers if self.has_images(messages)
                     else self._text_providers)
        errors: list[str] = []
        for provider in list(providers):
            try:
                result = await provider(messages)
            except Exception as exc:  # noqa: BLE001 — try the next provider
                errors.append(str(exc))
                continue
            if result is None:
                errors.append("provider returned no result")
                continue
            if not self._result_error(result):
                return result
            errors.append(self._result_error(result))

        if providers:
            return MultiModalResult(
                error=f"All providers failed: {'; '.join(errors)}")
        return await self._default_complete(messages)

    async def stream_complete(self, messages: list) -> AsyncIterator[str]:
        """Yield incremental chunks from the default completion path."""
        result = await self._default_complete(messages)
        chunks = list(getattr(result, "chunks", None) or [])
        if chunks:
            for chunk in chunks:
                yield chunk
            return
        text = getattr(result, "text", "") or ""
        if text:
            yield text
        elif getattr(result, "error", ""):
            yield result.error

    async def transcribe(self, audio_bytes: bytes) -> str:
        """Transcribe audio via the registered STT providers, in order."""
        for provider in list(self._stt_providers):
            try:
                text = await provider(audio_bytes)
            except Exception as exc:  # noqa: BLE001
                logger.debug("[multimodal] STT provider failed: %s", exc)
                continue
            if text:
                return str(text)
        return _AUDIO_UNAVAILABLE

    # ── default (LLM gateway) path ───────────────────────────────────
    async def _default_complete(self, messages: list) -> MultiModalResult:
        from core import llm_router

        prompt, image_ref = _flatten(messages)
        if image_ref:
            try:
                result = await llm_router.complete_vision(prompt, image_ref)
            except Exception as exc:  # noqa: BLE001
                return MultiModalResult(error=str(exc))
            return _result_from_llm(result)
        try:
            result = llm_router.complete(prompt)
        except Exception as exc:  # noqa: BLE001
            return MultiModalResult(error=str(exc))
        return _result_from_llm(result)

    # ── helpers ──────────────────────────────────────────────────────
    @staticmethod
    def _result_error(result: Any) -> str:
        return str(getattr(result, "error", "") or "")


def _flatten(messages: list) -> tuple[str, Optional[str]]:
    """Flatten messages into (prompt, image_reference_or_None)."""
    texts: list[str] = []
    image_ref: Optional[str] = None
    for message in messages or []:
        for part in getattr(message, "parts", []) or []:
            if isinstance(part, TextPart) and part.text:
                texts.append(part.text)
            elif isinstance(part, ImagePart) and part.data and image_ref is None:
                image_ref = part.data
    return "\n".join(texts), image_ref


def _result_from_llm(result: Any) -> MultiModalResult:
    """Adapt a ``Result[str]`` from llm_router into a MultiModalResult."""
    if hasattr(result, "is_ok"):
        if result.is_ok():
            text = str(result.unwrap())
            return MultiModalResult(text=text, chunks=[text])
        # Err.unwrap() raises, so read the error payload directly.
        error = getattr(result, "_error", None)
        return MultiModalResult(error=str(error if error is not None else result))
    if isinstance(result, str):
        return MultiModalResult(text=result, chunks=[result])
    return MultiModalResult(error=str(result))


multimodal_pipeline = MultiModalPipeline()


__all__ = ["MultiModalPipeline", "MultiModalResult", "multimodal_pipeline"]
