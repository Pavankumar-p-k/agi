"""Transport adapters.

Each adapter converts a transport-specific input to a canonical ``Request``,
calls ``process_message()``, and converts the ``Response`` back to the
transport's output format.

Adapters are the **only** code that should contain transport-specific logic
(message formatting, attachment handling, platform metadata, …).
"""
from core.pipeline.adapters.channel_adapter import channel_adapter

__all__ = [
    "channel_adapter",
]
