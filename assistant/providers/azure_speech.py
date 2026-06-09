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

import logging
import os
import tempfile

from ..stt_protocol import STTProvider

logger = logging.getLogger(__name__)


class AzureSpeechProvider(STTProvider):
    """Azure Speech-to-Text — cloud STT with high accuracy."""

    @property
    def name(self) -> str:
        return "azure-speech"

    def __init__(self):
        self._key = os.getenv("AZURE_SPEECH_KEY", "")
        self._region = os.getenv("AZURE_SPEECH_REGION", "eastus")
        self._healthy = bool(self._key)

    async def transcribe(self, audio_bytes: bytes, language: str | None = None) -> str:
        if not self._healthy:
            return ""
        try:
            import azure.cognitiveservices.speech as speechsdk

            speech_config = speechsdk.SpeechConfig(subscription=self._key, region=self._region)
            if language:
                speech_config.speech_recognition_language = language

            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name

            try:
                audio_config = speechsdk.audio.AudioConfig(filename=tmp_path)
                recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
                future = recognizer.recognize_once_async()
                result = await future
                if result.reason == speechsdk.ResultReason.RecognizedSpeech:
                    return result.text
                elif result.reason == speechsdk.ResultReason.Canceled:
                    cancellation = speechsdk.CancellationDetails(result)
                    logger.warning("[Azure] Speech recognition canceled: %s", cancellation.reason)
                return ""
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
        except Exception as e:
            logger.warning("[AzureSpeech] Transcription failed: %s", e)
            return ""

    async def health(self) -> bool:
        return self._healthy
