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

import asyncio
import logging
import threading
from typing import Any

from core.plugins import VoicePlugin, PluginManifest

logger = logging.getLogger(__name__)


class Plugin(VoicePlugin):
    manifest: PluginManifest

    def __init__(self, manifest: PluginManifest):
        super().__init__(manifest)
        self._detector = None
        self._stt = None
        self._lock = threading.Lock()
        self._last_trigger = 0.0

    async def on_load(self, app_state: dict | None = None) -> None:
        await super().on_load(app_state)
        try:
            from assistant.wake_word import get_detector
            self._detector = get_detector()
            logger.info("[WakeWordPlugin] WakeWordDetector acquired")
        except Exception as e:
            logger.warning("[WakeWordPlugin] Could not acquire detector: %s", e)
        try:
            from assistant.stt import get_stt
            self._stt = get_stt()
            logger.info("[WakeWordPlugin] STT engine acquired")
        except Exception as e:
            logger.warning("[WakeWordPlugin] Could not acquire STT: %s", e)

    async def on_unload(self) -> None:
        if self._detector and self._detector.is_running:
            self._detector.stop()
        self._detector = None
        self._stt = None
        await super().on_unload()

    async def on_wake_word(self, audio_data: bytes) -> bool | None:
        if not self._detector:
            return None
        with self._lock:
            if self._detector.check_detection():
                import time
                self._last_trigger = time.time()
                return True
        return None

    async def on_stt(self, audio_data: bytes) -> str | None:
        if not self._stt or not audio_data:
            return None
        try:
            result = self._stt.transcribe(audio_data)
            if asyncio.iscoroutine(result):
                text = await result
            else:
                text = result
            if text:
                logger.info("[WakeWordPlugin] Transcribed: %.60s", text)
            return text
        except Exception as e:
            logger.warning("[WakeWordPlugin] STT transcription failed: %s", e)
            return None

    async def health_check(self) -> dict:
        base = await super().health_check()
        base["detector_running"] = self._detector.is_running if self._detector else False
        base["stt_ready"] = self._stt is not None
        return base
