from __future__ import annotations

import logging
from enum import Enum
from typing import Any, AsyncGenerator
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class MediaType(Enum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    MUSIC = "music"
    TEXT = "text"
    CODE = "code"
    DOCUMENT = "document"


@dataclass
class MediaResult:
    type: MediaType
    data: bytes | str
    mime_type: str = ""
    filename: str = ""
    metadata: dict = field(default_factory=dict)
    duration: float = 0.0
    size: int = 0

    def __post_init__(self) -> None:
        if isinstance(self.data, bytes):
            self.size = len(self.data)
        else:
            self.size = len(self.data.encode())


@dataclass
class MediaGenerationParams:
    prompt: str
    negative_prompt: str = ""
    width: int = 512
    height: int = 512
    steps: int = 20
    seed: int | None = None
    batch_size: int = 1
    quality: str = "standard"
    format: str = "png"
    model: str = ""
    extra: dict = field(default_factory=dict)


class MediaProvider:
    type: MediaType
    name: str = ""
    version: str = "1.0.0"

    async def generate(self, params: MediaGenerationParams) -> list[MediaResult]:
        raise NotImplementedError

    async def generate_stream(self, params: MediaGenerationParams) -> AsyncGenerator[MediaResult, None]:
        results = await self.generate(params)
        for r in results:
            yield r

    async def health(self) -> dict:
        return {"type": self.type.value, "healthy": True}


class MediaRegistry:
    def __init__(self):
        self._providers: dict[str, MediaProvider] = {}

    def register(self, provider: MediaProvider) -> None:
        self._providers[f"{provider.type.value}:{provider.name}"] = provider
        logger.info("[MediaRegistry] Registered: %s/%s", provider.type.value, provider.name)

    def get(self, media_type: MediaType | str, name: str | None = None) -> MediaProvider | None:
        if isinstance(media_type, str):
            media_type = MediaType(media_type)
        if name:
            return self._providers.get(f"{media_type.value}:{name}")
        for key, p in self._providers.items():
            if key.startswith(media_type.value):
                return p
        return None

    def list_by_type(self, media_type: MediaType | str) -> list[MediaProvider]:
        if isinstance(media_type, str):
            media_type = MediaType(media_type)
        return [p for k, p in self._providers.items() if k.startswith(media_type.value)]

    @property
    def all(self) -> dict[str, MediaProvider]:
        return dict(self._providers)
