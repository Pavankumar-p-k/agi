from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ChannelConfig:
    enabled: bool = False
    token: str = ""
    webhook_secret: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


class ChannelPlugin:
    id: str = ""
    name: str = ""
    description: str = ""

    def __init__(self, config: ChannelConfig | None = None):
        self.config = config or ChannelConfig()
        self._running = False
        self._brain = None

    async def start(self, brain: Any) -> None:
        self._brain = brain
        self._running = True
        logger.info("[Channels] %s started", self.name)

    async def stop(self) -> None:
        self._running = False
        logger.info("[Channels] %s stopped", self.name)

    async def send(self, target: str, message: str) -> bool:
        raise NotImplementedError

    @property
    def is_running(self) -> bool:
        return self._running
