"""assistant/tts_protocol.py
TTS provider abstract base class and registry (mirrors STTProvider pattern).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TTSResult:
    audio_data: bytes
    format: str = "wav"
    sample_rate: int = 24000
    duration_sec: float = 0.0


class TTSProvider(ABC):
    name: str = ""

    @abstractmethod
    async def synthesize(self, text: str, **kwargs) -> TTSResult:
        ...

    @abstractmethod
    async def health(self) -> bool:
        ...


class TTSProviderRegistry:
    def __init__(self):
        self._providers: dict[str, type[TTSProvider]] = {}
        self._default: str = ""

    def register(self, name: str, provider: type[TTSProvider], default: bool = False):
        self._providers[name] = provider
        if default or not self._default:
            self._default = name

    def get(self, name: str = "") -> TTSProvider | None:
        provider_name = name or self._default
        cls = self._providers.get(provider_name)
        if cls:
            return cls()
        return None

    def list_providers(self) -> list[str]:
        return list(self._providers.keys())

    @property
    def default(self) -> str:
        return self._default

    @default.setter
    def default(self, name: str):
        if name in self._providers:
            self._default = name


_registry: TTSProviderRegistry | None = None


def get_tts_registry() -> TTSProviderRegistry:
    global _registry
    if _registry is None:
        _registry = TTSProviderRegistry()
    return _registry


def get_tts(name: str = "") -> TTSProvider | None:
    return get_tts_registry().get(name)
