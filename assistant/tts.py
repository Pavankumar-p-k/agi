import os
import io
import time
import soundfile as sf
from kokoro import KPipeline
import torch

_tts_instance = None

class JarvisTTS:
    """
    Kokoro-TTS integration for JARVIS.
    """
    def __init__(self, voice: str = "af_heart"):
        self.voice = voice
        self.pipeline = None
        self.cache = {}

    def _ensure_model(self):
        if self.pipeline is None:
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
            return b""

        import numpy as np
        combined_audio = np.concatenate(audio_chunks)
        
        # Write to memory buffer as WAV
        buffer = io.BytesIO()
        sf.write(buffer, combined_audio, 24000, format='WAV')
        audio_bytes = buffer.getvalue()

        # Cache if synthesis was fast and text is short
        duration = time.time() - start_time
        if duration < 0.1 or len(text) < 50:
            self.cache[text] = audio_bytes

        return audio_bytes

def get_tts():
    global _tts_instance
    if _tts_instance is None:
        _tts_instance = JarvisTTS(voice=os.getenv("TTS_VOICE", "af_heart"))
    return _tts_instance
