# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Specialized plugin base classes (voice/automation/privacy/memory)."""
from __future__ import annotations

import logging
from typing import Any

from core.plugins.base import Plugin

logger = logging.getLogger(__name__)


class VoicePlugin(Plugin):
    """Base for voice-related plugins (wake word, STT/TTS hooks)."""

    async def on_stt(self, audio: bytes, *args: Any, **kwargs: Any) -> Any | None:
        return None

    async def on_tts(self, text: str, *args: Any, **kwargs: Any) -> Any | None:
        return None

    async def on_wake_word(self, audio: bytes, *args: Any, **kwargs: Any) -> bool | None:
        return None


class AutomationPlugin(Plugin):
    """Base for desktop/PC-automation plugins."""

    async def before_action(self, action: dict[str, Any], *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        return None

    async def after_action(self, action: dict[str, Any], result: Any, *args: Any, **kwargs: Any) -> Any:
        return result


class PrivacyPlugin(Plugin):
    """Base for privacy/PII routing plugins."""

    async def on_routing_decision(self, tier: str, text: str, metadata: dict[str, Any], *args: Any, **kwargs: Any) -> str | None:
        return None


class MemoryPlugin(Plugin):
    """Base for memory-related plugins."""

    async def on_memory_write(self, entry: dict[str, Any], *args: Any, **kwargs: Any) -> dict[str, Any]:
        return entry

    async def on_memory_query(self, query: str, *args: Any, **kwargs: Any) -> str | None:
        return None
