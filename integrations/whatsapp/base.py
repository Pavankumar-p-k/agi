from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from .models import InteractiveBody, WhatsAppMessage, SendResult

logger = logging.getLogger(__name__)


class BaseWhatsAppProvider(ABC):
    name: str = ""

    def __init__(self):
        self._connected = False
        self._config: dict[str, Any] = {}

    @abstractmethod
    async def connect(self, **kwargs) -> bool:
        ...

    @abstractmethod
    async def disconnect(self) -> bool:
        ...

    @abstractmethod
    async def send_text(self, to: str, text: str, **kwargs) -> SendResult:
        ...

    @abstractmethod
    async def send_image(self, to: str, image_url: str, caption: str | None = None, **kwargs) -> SendResult:
        ...

    @abstractmethod
    async def send_document(self, to: str, document_url: str, filename: str, caption: str | None = None, **kwargs) -> SendResult:
        ...

    @abstractmethod
    async def send_audio(self, to: str, audio_url: str, **kwargs) -> SendResult:
        ...

    @abstractmethod
    async def send_location(self, to: str, latitude: float, longitude: float, name: str | None = None, address: str | None = None, **kwargs) -> SendResult:
        ...

    @abstractmethod
    async def download_media(self, media_id: str, mime_type: str) -> bytes | None:
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...

    @abstractmethod
    async def get_business_profile(self) -> dict[str, Any]:
        ...

    async def send_interactive_buttons(self, to: str, body: InteractiveBody, **kwargs) -> SendResult:
        raise NotImplementedError(f"{self.name} does not support interactive buttons")

    async def send_interactive_list(self, to: str, body: InteractiveBody, **kwargs) -> SendResult:
        raise NotImplementedError(f"{self.name} does not support interactive lists")

    @property
    def is_connected(self) -> bool:
        return self._connected

    def configure(self, **kwargs):
        self._config.update(kwargs)
