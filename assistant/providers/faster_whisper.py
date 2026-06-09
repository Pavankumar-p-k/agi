from __future__ import annotations

import asyncio
import io
import logging
import os
import tempfile

from ..stt_protocol import STTProvider

logger = logging.getLogger(__name__)


class FasterWhisperProvider(STTProvider):
    """Faster-Whisper — local, free, private. The default JARVIS provider."""

    @property
    def name(self) -> str:
        return "faster-whisper"

    def __init__(self, model_size: str | None = None):
        self._model_size = model_size or os.getenv("STT_MODEL", "base")
        self._model = None
        self._healthy = False
        self._init_lock = asyncio.Lock()

    async def _ensure(self):
        if self._model is not None:
            return
        async with self._init_lock:
            if self._model is not None:
                return
            import torch
            from faster_whisper import WhisperModel
            device = "cuda" if torch.cuda.is_available() else "cpu"
            compute = "float16" if device == "cuda" else "int8"
            logger.info("[STT] Loading Faster-Whisper %s on %s", self._model_size, device)
            loop = asyncio.get_running_loop()
            self._model = await loop.run_in_executor(
                None, lambda: WhisperModel(self._model_size, device=device, compute_type=compute))
            self._healthy = True

    async def _normalize(self, wav_bytes: bytes) -> bytes:
        try:
            import numpy as np
            import soundfile as sf
            data, sr = sf.read(io.BytesIO(wav_bytes))
            if len(data) == 0:
                return wav_bytes
            data = data.astype(np.float32)
            data -= np.mean(data)
            peak = np.max(np.abs(data))
            if peak > 0:
                data = data / peak * 0.95
            buf = io.BytesIO()
            sf.write(buf, data, sr, format="WAV", subtype="PCM_16")
            return buf.getvalue()
        except Exception as e:
            logger.warning("[STT] Normalization failed: %s", e)
            return wav_bytes

    async def transcribe(self, audio_bytes: bytes, language: str | None = None) -> str:
        await self._ensure()
        audio_bytes = await self._normalize(audio_bytes)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        try:
            kwargs = dict(beam_size=5, vad_filter=True,
                          vad_parameters=dict(min_silence_duration_ms=500))
            if language:
                kwargs["language"] = language
            segments, _ = self._model.transcribe(tmp_path, **kwargs)
            text = " ".join(seg.text for seg in segments)
            return text.strip()
        except Exception as e:
            logger.warning("[STT] transcribe failed: %s", e)
            return ""
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    async def health(self) -> bool:
        try:
            await self._ensure()
            return self._healthy
        except Exception as e:
            logger.warning("[STT] health check failed: %s", e)
            return False
