"""Messaging channels — plugin contract, controller and integrations.

Each integration is an optional dependency: import the module you need rather
than pulling every vendor SDK through the package root.
"""
from __future__ import annotations

from channels.base import ChannelConfig, ChannelPlugin
from channels.controller import ChannelController, channel_controller

__all__ = [
    "ChannelConfig",
    "ChannelPlugin",
    "ChannelController",
    "channel_controller",
]
