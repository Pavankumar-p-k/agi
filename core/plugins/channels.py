from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class MessageType(Enum):
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    FILE = "file"
    STICKER = "sticker"
    LOCATION = "location"
    CONTACT = "contact"
    EVENT = "event"


class ChannelCapability(Enum):
    SEND_TEXT = "send_text"
    SEND_MEDIA = "send_media"
    SEND_FILES = "send_files"
    RECEIVE_TEXT = "receive_text"
    RECEIVE_MEDIA = "receive_media"
    RECEIVE_FILES = "receive_files"
    VOICE_CALL = "voice_call"
    VIDEO_CALL = "video_call"
    GROUP_CHAT = "group_chat"
    THREADS = "threads"
    REACTIONS = "reactions"
    EDIT = "edit"
    DELETE = "delete"
    TYPING = "typing"
    WEBHOOKS = "webhooks"
    OAUTH = "oauth"
    BOT_API = "bot_api"


@dataclass
class Message:
    id: str
    channel_id: str
    text: str = ""
    type: MessageType = MessageType.TEXT
    sender: str = ""
    sender_name: str = ""
    chat_id: str = ""
    chat_name: str = ""
    reply_to: str | None = None
    attachments: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    timestamp: float = 0.0


@dataclass
class ChannelConfig:
    id: str
    name: str
    enabled: bool = True
    config: dict = field(default_factory=dict)


class ChannelContract:
    id: str = ""
    name: str = ""
    version: str = "1.0.0"
    capabilities: set[ChannelCapability] = field(default_factory=set)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not cls.id:
            cls.id = cls.__name__.lower().replace("channel", "")

    async def start(self, config: ChannelConfig) -> bool:
        raise NotImplementedError

    async def stop(self) -> bool:
        raise NotImplementedError

    async def send(self, message: Message) -> bool:
        raise NotImplementedError

    async def receive(self) -> Message | None:
        return None

    async def health(self) -> dict:
        return {"id": self.id, "healthy": False, "error": "not implemented"}

    async def set_webhook(self, url: str) -> bool:
        return False

    @property
    def is_running(self) -> bool:
        return False


class ChannelRegistry:
    def __init__(self):
        self._channels: dict[str, ChannelContract] = {}

    def register(self, channel: ChannelContract) -> None:
        self._channels[channel.id] = channel
        logger.info("[ChannelRegistry] Registered: %s (%s)", channel.id, channel.name)

    def unregister(self, channel_id: str) -> None:
        self._channels.pop(channel_id, None)

    def get(self, channel_id: str) -> ChannelContract | None:
        return self._channels.get(channel_id)

    def list_by_capability(self, cap: ChannelCapability) -> list[ChannelContract]:
        return [c for c in self._channels.values() if cap in c.capabilities]

    @property
    def all(self) -> dict[str, ChannelContract]:
        return dict(self._channels)

    @property
    def count(self) -> int:
        return len(self._channels)
