import os
import tempfile
import torch
from faster_whisper import WhisperModel

_stt_instance = None

class JarvisSTT:
    """
    Faster-Whisper STT integration for JARVIS.
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

    def transcribe(self, audio_bytes: bytes) -> str:
        """
        Transcribe audio bytes to text.
        """
        self._ensure_model()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        
        try:
            segments, info = self.model.transcribe(tmp_path, beam_size=5)
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
