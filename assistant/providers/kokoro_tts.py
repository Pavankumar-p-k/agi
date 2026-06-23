"""assistant/providers/kokoro_tts.py
Kokoro-TTS provider wrapping the existing JarvisTTS.
"""
from __future__ import annotations

import logging

from assistant.tts_protocol import TTSProvider, TTSResult

logger = logging.getLogger(__name__)


class KokoroTTSProvider(TTSProvider):
    name = "kokoro"

    async def synthesize(self, text: str, **kwargs) -> TTSResult:
        from assistant.tts import get_tts as _get_tts
        tts = _get_tts()
        audio = tts.synthesize(text)
        return TTSResult(
            audio_data=audio,
            format="wav",
            sample_rate=24000,
            duration_sec=len(audio) / (24000 * 2) if audio else 0.0,
        )

    async def health(self) -> bool:
        try:
            from assistant.tts import get_tts as _get_tts
            tts = _get_tts()
            return tts is not None
        except Exception as e:
            logger.warning("[KokoroTTS] health check failed: %s", e)
            return False
