import io
import os
import tempfile
import numpy as np
import torch
import soundfile as sf
from faster_whisper import WhisperModel

_stt_instance = None

class JarvisSTT:
    """
    Faster-Whisper STT integration for JARVIS with audio normalization.
    """
    def __init__(self, model_size: str = "base"):
        self.model_size = model_size
        self.model = None

    def _ensure_model(self):
        if self.model is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            compute_type = "float16" if device == "cuda" else "int8"
            print(f"[STT] Initializing Faster-Whisper ({self.model_size}) on {device}...")
            self.model = WhisperModel(self.model_size, device=device, compute_type=compute_type)

    def _normalize_audio(self, wav_bytes: bytes) -> bytes:
        """Normalize audio volume + reduce DC offset."""
        try:
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
        except Exception:
            return wav_bytes

    def transcribe(self, audio_bytes: bytes, language: str = None) -> str:
        """
        Transcribe audio bytes to text with normalization.
        """
        self._ensure_model()
        audio_bytes = self._normalize_audio(audio_bytes)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        
        kwargs = dict(beam_size=5, vad_filter=True,
                      vad_parameters=dict(min_silence_duration_ms=500))
        if language:
            kwargs["language"] = language
        try:
            segments, info = self.model.transcribe(tmp_path, **kwargs)
            text = " ".join([seg.text for seg in segments])
            return text.strip()
        except Exception as e:
            print(f"[STT] Transcription error: {e}")
            return ""
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

def get_stt():
    global _stt_instance
    if _stt_instance is None:
        _stt_instance = JarvisSTT(model_size=os.getenv("STT_MODEL", "base"))
    return _stt_instance
