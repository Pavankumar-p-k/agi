from __future__ import annotations

from .faster_whisper import FasterWhisperProvider
from .deepgram import DeepgramProvider
from .azure_speech import AzureSpeechProvider

__all__ = ["FasterWhisperProvider", "DeepgramProvider", "AzureSpeechProvider"]
