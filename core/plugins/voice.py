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
from __future__ import annotations

import inspect
import logging

from core.plugins.base import Plugin, PluginManifest

logger = logging.getLogger(__name__)


class VoicePlugin(Plugin):
    manifest: PluginManifest

    def __init__(self, manifest: PluginManifest):
        super().__init__(manifest)
        self._stt_hooks: list = []
        self._tts_hooks: list = []
        self._wake_word_hooks: list = []

    async def on_load(self, app_state: dict | None = None) -> None:
        await super().on_load(app_state)
        logger.info("[VoicePlugin] %s registered: %d hooks", self.manifest.name, self._hook_count())

    async def on_unload(self) -> None:
        self._stt_hooks.clear()
        self._tts_hooks.clear()
        self._wake_word_hooks.clear()
        await super().on_unload()

    def _hook_count(self) -> int:
        return len(self._stt_hooks) + len(self._tts_hooks) + len(self._wake_word_hooks)

    def register_stt_hook(self, hook: callable) -> None:
        self._stt_hooks.append(hook)

    def register_tts_hook(self, hook: callable) -> None:
        self._tts_hooks.append(hook)

    def register_wake_word_hook(self, hook: callable) -> None:
        self._wake_word_hooks.append(hook)

    async def on_stt(self, audio_data: bytes) -> bytes | None:
        for hook in self._stt_hooks:
            try:
                result = await hook(audio_data) if inspect.iscoroutinefunction(hook) else hook(audio_data)
                if result is not None:
                    return result
            except Exception as e:
                logger.exception("[VoicePlugin] STT hook failed: %s", e)
        return None

    async def on_tts(self, text: str) -> str | None:
        for hook in self._tts_hooks:
            try:
                result = await hook(text) if inspect.iscoroutinefunction(hook) else hook(text)
                if result is not None:
                    return result
            except Exception as e:
                logger.exception("[VoicePlugin] TTS hook failed: %s", e)
        return None

    async def on_wake_word(self, audio_data: bytes) -> bool | None:
        for hook in self._wake_word_hooks:
            try:
                result = await hook(audio_data) if inspect.iscoroutinefunction(hook) else hook(audio_data)
                if result is not None:
                    return result
            except Exception as e:
                logger.exception("[VoicePlugin] Wake-word hook failed: %s", e)
        return None

    async def health_check(self) -> dict:
        base = await super().health_check()
        base["stt_hooks"] = len(self._stt_hooks)
        base["tts_hooks"] = len(self._tts_hooks)
        base["wake_word_hooks"] = len(self._wake_word_hooks)
        return base
