"""Transport adapters.

Each adapter converts a transport-specific input to a canonical ``Request``,
calls ``process_message()``, and converts the ``Response`` back to the
transport's output format.

Adapters are the **only** code that should contain transport-specific logic
(message formatting, attachment handling, platform metadata, …).
"""
from core.pipeline.adapters.channel_adapter import channel_adapter
from core.pipeline.adapters.rest_adapter import rest_adapter
from core.pipeline.adapters.voice_adapter import voice_adapter
from core.pipeline.adapters.websocket_adapter import ws_adapter

__all__ = [
    "channel_adapter",
    "rest_adapter",
    "voice_adapter",
    "ws_adapter",
]
