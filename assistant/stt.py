import os
import tempfile
import torch
from faster_whisper import WhisperModel

class JarvisSTT:
    """
    Faster-Whisper STT integration for JARVIS.
    """
    def __init__(self, model_size: str = "base"):
        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if device == "cuda" else "int8"
        
        print(f"[STT] Initializing Faster-Whisper ({model_size}) on {device}...")
        self.model = WhisperModel(model_size, device=device, compute_type=compute_type)

    def transcribe(self, audio_bytes: bytes) -> str:
        """
        Transcribe audio bytes to text.
        """
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

# Singleton instance
stt = JarvisSTT(model_size=os.getenv("STT_MODEL", "base"))
