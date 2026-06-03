from __future__ import annotations

from .base import ChannelPlugin, ChannelConfig
from .controller import ChannelController
from .processor import process_message

channel_controller = ChannelController()

__all__ = [
    "ChannelPlugin",
    "ChannelConfig",
    "ChannelController",
    "channel_controller",
    "process_message",
]
