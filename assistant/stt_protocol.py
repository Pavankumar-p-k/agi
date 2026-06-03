from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator


class STTProvider(ABC):
    """Abstract base for speech-to-text providers — matching OpenClaw's registerRealtimeTranscriptionProvider."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, language: str | None = None) -> str:
        """Transcribe audio bytes to text."""
        ...

    async def transcribe_stream(self, audio_stream: AsyncIterator[bytes]) -> AsyncIterator[str]:
        """Real-time streaming transcription. Override for providers that support it."""
        full = b""
        async for chunk in audio_stream:
            full += chunk
        result = await self.transcribe(full)
        yield result

    @abstractmethod
    async def health(self) -> bool:
        """Check if provider is healthy."""
        ...


class STTProviderRegistry:
    """Provider registry for swappable STT backends."""

    def __init__(self):
        self._providers: dict[str, STTProvider] = {}
        self._default: str | None = None

    def register(self, provider: STTProvider, make_default: bool = False) -> None:
        self._providers[provider.name] = provider
        if make_default or self._default is None:
            self._default = provider.name

    def get(self, name: str | None = None) -> STTProvider:
        name = name or self._default
        if not name or name not in self._providers:
            raise KeyError(f"STT provider '{name}' not registered. Available: {list(self._providers.keys())}")
        return self._providers[name]

    def list(self) -> list[str]:
        return list(self._providers.keys())

    @property
    def default(self) -> str | None:
        return self._default


stt_registry = STTProviderRegistry()
