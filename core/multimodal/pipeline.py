# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass, field

from .schema import (
    AudioPart,
    ImagePart,
    MultiModalMessage,
    ProviderFormat,
)

logger = logging.getLogger("jarvis.multimodal.pipeline")


@dataclass
class PipelineResult:
    text: str = ""
    latency_ms: float = 0.0
    model: str = ""
    provider: ProviderFormat = ProviderFormat.OPENAI
    error: str = ""
    chunks: list[str] = field(default_factory=list)


class MultiModalPipeline:
    """Unified multi-modal pipeline with format conversion, routing, and fallback.

    Accepts ``list[MultiModalMessage]``, routes to the best model based on
    content type (vision model for images, any model for text), converts
    to the target provider's format, and provides fallback chains.
    """

    def __init__(self):
        self._vision_providers: list[Callable[[list[MultiModalMessage]], Awaitable[PipelineResult]]] = []
        self._text_providers: list[Callable[[list[MultiModalMessage]], Awaitable[PipelineResult]]] = []
        self._audio_providers: list[Callable[[bytes], Awaitable[str]]] = []

    def register_vision(self, fn: Callable[[list[MultiModalMessage]], Awaitable[PipelineResult]]) -> None:
        self._vision_providers.append(fn)

    def register_text(self, fn: Callable[[list[MultiModalMessage]], Awaitable[PipelineResult]]) -> None:
        self._text_providers.append(fn)

    def register_audio_stt(self, fn: Callable[[bytes], Awaitable[str]]) -> None:
        self._audio_providers.append(fn)

    async def complete(
        self,
        messages: list[MultiModalMessage],
        stream: bool = False,
    ) -> PipelineResult:
        """Route a multi-modal message list to the best provider.

        Inspects messages for image/audio content and routes accordingly.
        Falls back through the chain if the primary provider fails.
        """
        has_images = any(
            isinstance(p, ImagePart) for m in messages for p in m.parts
        )
        has_audio = any(
            isinstance(p, AudioPart) for m in messages for p in m.parts
        )

        providers = self._vision_providers if has_images else self._text_providers

        if not providers:
            # Default: use LiteLLM router
            return await self._default_complete(messages, stream=stream)

        errors = []
        for provider_fn in providers:
            try:
                result = await provider_fn(messages)
                if result.text or not result.error:
                    if stream:
                        result.chunks = [result.text]
                    return result
                errors.append(result.error)
            except Exception as e:
                errors.append(str(e))
                logger.warning("[MM] Provider failed: %s", e)

        return PipelineResult(
            text="",
            error=f"All providers failed: {'; '.join(errors)}",
        )

    async def transcribe(self, audio_bytes: bytes) -> str:
        """Transcribe audio using the registered STT providers (fallback chain).

        Audio providers in order: Faster-Whisper (local) → Deepgram → Azure Speech.
        """
        if not self._audio_providers:
            return "[Audio transcription not available]"

        errors = []
        for stt_fn in self._audio_providers:
            try:
                text = await stt_fn(audio_bytes)
                if text:
                    return text
            except Exception as e:
                errors.append(str(e))

        logger.warning("[MM] All STT providers failed: %s", "; ".join(errors))
        return "[Transcription failed]"

    async def _default_complete(
        self,
        messages: list[MultiModalMessage],
        stream: bool = False,
    ) -> PipelineResult:
        """Default completion via canonical pipeline or llm_router for vision."""
        import importlib as _il

        has_images = any(
            isinstance(p, ImagePart) for m in messages for p in m.parts
        )

        start = asyncio.get_event_loop().time()
        try:
            if has_images:
                _llm_router = _il.import_module("core.llm_router")
                openai_messages = [m.to_openai_dict() for m in messages]
                result = await _llm_router.complete_vision(openai_messages)
                elapsed = (asyncio.get_event_loop().time() - start) * 1000
                if result.is_ok():
                    text = result.unwrap()
                    return PipelineResult(text=text, latency_ms=elapsed, model="default")
                return PipelineResult(error=result.unwrap_or("Unknown error"))
            else:
                from core.pipeline.internal_client import prompt as llm_prompt
                text_content = "\n".join(m.to_text() for m in messages if hasattr(m, "to_text"))
                if not text_content:
                    text_content = str(messages)
                text = await llm_prompt(text_content)
                elapsed = (asyncio.get_event_loop().time() - start) * 1000
                return PipelineResult(text=text, latency_ms=elapsed, model="default")
        except Exception as e:
            elapsed = (asyncio.get_event_loop().time() - start) * 1000
            return PipelineResult(
                text="",
                latency_ms=elapsed,
                error=str(e),
            )

    async def stream_complete(
        self,
        messages: list[MultiModalMessage],
    ) -> AsyncGenerator[str, None]:
        """Stream a multi-modal completion, yielding text chunks."""
        result = await self.complete(messages, stream=True)
        if result.error and not result.text:
            yield f"[Error: {result.error}]"
            return
        if result.chunks:
            for chunk in result.chunks:
                yield chunk
        else:
            yield result.text


multimodal_pipeline = MultiModalPipeline()
