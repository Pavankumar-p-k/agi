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
import os

from ..stt_protocol import STTProvider

logger = logging.getLogger(__name__)


class DeepgramProvider(STTProvider):
    """Deepgram — cloud STT with real-time streaming support."""

    @property
    def name(self) -> str:
        return "deepgram"

    def __init__(self):
        self._client = None
        self._healthy = False
        self._init()

    def _init(self):
        api_key = os.getenv("DEEPGRAM_API_KEY", "")
        if not api_key:
            logger.warning("[Deepgram] No DEEPGRAM_API_KEY set")
            return
        try:
            from deepgram import DeepgramClient
            self._client = DeepgramClient(api_key=api_key)
            self._healthy = True
            logger.info("[Deepgram] Provider ready")
        except Exception as e:
            logger.warning("[Deepgram] Init failed: %s", e)

    async def transcribe(self, audio_bytes: bytes, language: str | None = None) -> str:
        if not self._client:
            return ""
        try:
            options = {"model": "nova-3", "language": language or "en"}
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._client.listen.rest.v("1").transcribe_file(
                    {"buffer": audio_bytes}, options,
                ),
            )
            results = response.results
            if results and results.channels:
                return results.channels[0].alternatives[0].transcript
            return ""
        except Exception as e:
            logger.warning("[Deepgram] Transcription failed: %s", e)
            return ""

    async def health(self) -> bool:
        return self._healthy
