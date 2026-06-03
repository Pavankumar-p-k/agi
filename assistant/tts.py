import os
import io
import time
import threading
import logging

logger = logging.getLogger(__name__)

_tts_instance = None
_tts_lock = threading.Lock()

class JarvisTTS:
    """
    Kokoro-TTS integration for JARVIS.
    """
    def __init__(self, voice: str = "af_heart", max_cache: int = 128):
        self.voice = voice
        self.pipeline = None
        self.cache: dict[str, bytes] = {}
        self._max_cache = max_cache

    def _ensure_model(self):
        if self.pipeline is None:
            import torch
            from kokoro import KPipeline
            device = "cuda" if torch.cuda.is_available() else "cpu"
            print(f"[TTS] Initializing Kokoro-TTS on {device}...")
            self.pipeline = KPipeline(lang_code='a', device=device)

    def synthesize(self, text: str) -> bytes:
        """
        Synthesize text to WAV audio bytes.
        """
        if text in self.cache:
            return self.cache[text]

        self._ensure_model()
        start_time = time.time()
        
        generator = self.pipeline(
            text, voice=self.voice,
            speed=1, split_pattern=r'\n+'
        )

        audio_chunks = []
        for i, (gs, ps, audio) in enumerate(generator):
            audio_chunks.append(audio)

        if not audio_chunks:
            logger.warning("[TTS] synthesize produced no audio chunks for text: %s", text[:50])
            return b""

        import numpy as np
        combined_audio = np.concatenate(audio_chunks)

        # Write to memory buffer as WAV
        import soundfile as sf
        buffer = io.BytesIO()
        sf.write(buffer, combined_audio, 24000, format='WAV')
        audio_bytes = buffer.getvalue()

        duration = time.time() - start_time
        max_len = self._max_cache
        if (duration < 0.1 or len(text) < 50) and len(self.cache) < max_len:
            self.cache[text] = audio_bytes

        return audio_bytes

def get_tts():
    global _tts_instance
    if _tts_instance is None:
        with _tts_lock:
            if _tts_instance is None:
                _tts_instance = JarvisTTS(voice=os.getenv("TTS_VOICE", "af_heart"))
    return _tts_instance
