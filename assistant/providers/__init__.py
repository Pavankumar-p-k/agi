"""assistant/providers/__init__.py
STT and TTS provider implementations.
"""
from assistant.providers.faster_whisper import FasterWhisperProvider
from assistant.providers.deepgram import DeepgramProvider
from assistant.providers.azure_speech import AzureSpeechProvider
from assistant.providers.kokoro_tts import KokoroTTSProvider
from assistant.providers.edge_tts_provider import EdgeTTSProvider


def _register_tts_providers():
    from assistant.tts_protocol import get_tts_registry
    registry = get_tts_registry()
    registry.register("kokoro", KokoroTTSProvider, default=True)
    registry.register("edge-tts", EdgeTTSProvider)

_register_tts_providers()

__all__ = [
    "FasterWhisperProvider", "DeepgramProvider", "AzureSpeechProvider",
    "KokoroTTSProvider", "EdgeTTSProvider",
]
