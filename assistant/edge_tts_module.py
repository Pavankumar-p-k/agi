from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


class EdgeTTS:
    def __init__(self, voice: str | None = None):
        from core.config_registry import config as _c
        self.voice = voice or _c.get("voice.tts_voice")

    async def synthesize(self, text: str) -> bytes:
        try:
            import edge_tts
            communicate = edge_tts.Communicate(text, self.voice)
            audio_bytes = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_bytes += chunk["data"]
            return audio_bytes
        except ImportError:
            logger.warning("edge_tts not installed — install with: pip install edge-tts")
            return b""
        except Exception as e:
            logger.exception("[EdgeTTS] synthesize failed: %s", e)
            return b""
