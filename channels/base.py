"""Channel plugin contract — config plus the start/stop/send lifecycle.

A channel is a messaging surface (Discord, Slack, Telegram, Matrix, IRC).
Each plugin owns its connection and reports honest readiness via
``is_running``; ``send`` raises ``NotImplementedError`` unless overridden.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ChannelConfig:
    """Declarative channel configuration (env secrets stay outside)."""

    enabled: bool = False
    token: str = ""
    webhook_secret: str = ""
    extra: dict = field(default_factory=dict)


class ChannelPlugin:
    """Base class for inbound/outbound messaging channels."""

    id: str = ""
    name: str = ""

    def __init__(self, config: Optional[ChannelConfig] = None,
                 handler: Any = None) -> None:
        self.config = config if config is not None else ChannelConfig()
        self.handler = handler
        self.is_running: bool = False
        self._app: Any = None

    @property
    def enabled(self) -> bool:
        return bool(self.config.enabled)

    async def start(self, app: Any = None) -> None:
        """Attach the host application and mark the channel running."""
        self._app = app
        self.is_running = True

    async def stop(self) -> None:
        self.is_running = False

    async def send(self, target: str, message: str) -> bool:
        raise NotImplementedError(
            f"{self.id or type(self).__name__} does not implement send()")

    async def handle_message(self, sender: str, text: str, **metadata: Any) -> Any:
        """Dispatch an inbound message to the conversation handler, if wired."""
        if self.handler is None:
            return None
        result = self.handler(sender=sender, text=text, channel=self.id,
                              **metadata)
        if hasattr(result, "__await__"):
            return await result
        return result


__all__ = ["ChannelConfig", "ChannelPlugin"]
