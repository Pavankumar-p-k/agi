"""assistant/providers/edge_tts_provider.py
EdgeTTS provider wrapping the existing EdgeTTS module.
"""
from __future__ import annotations

import logging

from assistant.tts_protocol import TTSProvider, TTSResult

logger = logging.getLogger(__name__)


class EdgeTTSProvider(TTSProvider):
    name = "edge-tts"

    async def synthesize(self, text: str, **kwargs) -> TTSResult:
        from assistant.edge_tts_module import EdgeTTS
        tts = EdgeTTS()
        audio = await tts.synthesize(text)
        return TTSResult(
            audio_data=audio if isinstance(audio, bytes) else audio.encode(),
            format="mp3",
            sample_rate=24000,
        )

    async def health(self) -> bool:
        try:
            from assistant.edge_tts_module import EdgeTTS
            tts = EdgeTTS()
            return tts is not None
        except Exception as e:
            logger.warning("[EdgeTTS] health check failed: %s", e)
            return False
