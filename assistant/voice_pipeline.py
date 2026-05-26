"""assistant/voice_pipeline.py — Unified voice pipeline.
mic -> STT -> text -> llm_router -> response -> TTS -> speaker
"""
import asyncio
import io
import os
import sys
import threading
import time

import numpy as np
import sounddevice as sd
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from assistant.stt import get_stt
from assistant.tts import get_tts
from core.llm_router import complete as llm_complete


SYSTEM_PROMPT = (
    "You are JARVIS, a personal AI assistant. "
    "Be concise and direct. Answer in 1-3 sentences. "
    "Tell the user what you actually did — do NOT invent details that didn't happen."
)

RECORD_SECONDS = 5
SAMPLE_RATE = 16000


def _record_audio(duration: int = RECORD_SECONDS, sr: int = SAMPLE_RATE) -> bytes:
    """Record from default mic, return WAV bytes."""
    recording = sd.rec(int(sr * duration), samplerate=sr, channels=1, dtype="float32")
    sd.wait()
    buf = io.BytesIO()
    sf.write(buf, recording, sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def _play_audio(wav_bytes: bytes):
    """Play WAV audio bytes through default speaker."""
    data, sr = sf.read(io.BytesIO(wav_bytes))
    sd.play(data, sr)
    sd.wait()


class VoicePipeline:
    """Unified STT -> LLM -> TTS pipeline with lazy-loaded models."""

    def __init__(self):
        self._stt = None
        self._tts = None

    @property
    def stt(self):
        if self._stt is None:
            self._stt = get_stt()
        return self._stt

    @property
    def tts(self):
        if self._tts is None:
            self._tts = get_tts()
        return self._tts

    async def transcribe(self, audio_bytes: bytes) -> str:
        """Transcribe audio bytes to text using Faster-Whisper."""
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(None, self.stt.transcribe, audio_bytes)
        return text

    async def think(self, text: str) -> str:
        """Get LLM response — tries cloud (Groq) for speed, falls back to local qwen3:4b."""
        import os
        model = "cloud" if os.getenv("GROQ_API_KEY") else "automation"
        try:
            reply = await llm_complete(
                model_group=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
                timeout=10,
            )
            return reply
        except Exception:
            # Fallback to fast local model
            reply = await llm_complete(
                model_group="automation",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
                timeout=15,
            )
            return reply

    async def speak(self, text: str) -> bytes:
        """Synthesize text to WAV audio bytes using Kokoro."""
        loop = asyncio.get_event_loop()
        audio = await loop.run_in_executor(None, self.tts.synthesize, text)
        return audio

    async def process_audio(self, audio_bytes: bytes) -> bytes:
        """Full pipeline: audio in -> audio out."""
        transcribed = await self.transcribe(audio_bytes)
        if not transcribed:
            return await self.speak("Sorry, I didn't catch that. Could you please repeat?")
        response = await self.think(transcribed)
        audio_out = await self.speak(response)
        return audio_out


class VoiceLoop:
    """Continuous voice loop: wake word -> record -> process -> respond -> repeat."""

    def __init__(self):
        self.pipeline = get_pipeline()
        self._wake_word = None
        self._wake_event = threading.Event()
        self._stop_event = threading.Event()
        self._loop_thread = None
        self._wake_preroll = b""

    def _on_wake(self):
        """Called by WakeWordDetector when 'Hey Jarvis' is heard. Snap preroll BEFORE buffer clears."""
        if self._wake_word:
            try:
                self._wake_preroll = self._wake_word.get_recent_audio()
            except Exception:
                self._wake_preroll = b""
        self._wake_event.set()

    def start(self):
        """Start the voice loop in a background thread."""
        from assistant.wake_word import WakeWordDetector
        self._wake_word = WakeWordDetector()
        self._wake_word.start(self._on_wake)
        self._loop_thread = threading.Thread(target=self._run_loop, daemon=True)
        self._loop_thread.start()
        print("[VoiceLoop] Started. Say 'Hey Jarvis' to activate.")

    def _run_loop(self):
        """Main loop: wait for wake -> combine preroll + ring buffer -> process -> play.
        No fresh recording — avoids dual-mic conflict with wake word InputStream."""
        while not self._stop_event.is_set():
            self._wake_event.wait()
            self._wake_event.clear()
            if self._stop_event.is_set():
                break
            try:
                preroll = self._wake_preroll
                self._wake_preroll = b""
                # Let user finish speaking, then read ring buffer (fresh audio after clear)
                time.sleep(3)
                tail = b""
                if self._wake_word:
                    tail = self._wake_word.get_recent_audio()
                import io, soundfile as sf, numpy as np
                if preroll and tail:
                    p_data, _ = sf.read(io.BytesIO(preroll))
                    t_data, _ = sf.read(io.BytesIO(tail))
                    combined = np.concatenate([p_data, t_data])
                    buf = io.BytesIO()
                    sf.write(buf, combined, SAMPLE_RATE, format="WAV", subtype="PCM_16")
                    audio = buf.getvalue()
                elif preroll:
                    audio = preroll
                elif tail:
                    audio = tail
                else:
                    print("[VoiceLoop] No audio captured")
                    continue
                print(f"[VoiceLoop] Audio: {len(audio)} bytes, transcribing...")
                audio_out = asyncio.run(self.pipeline.process_audio(audio))
                if audio_out:
                    print(f"[VoiceLoop] Got {len(audio_out)} bytes, playing...")
                    _play_audio(audio_out)
                    print("[VoiceLoop] Response played")
                else:
                    print("[VoiceLoop] No audio output from pipeline")
            except Exception as e:
                print(f"[VoiceLoop] Error in cycle: {e}")
                # Don't die — resume listening for next wake word

    def stop(self):
        """Stop the voice loop."""
        self._stop_event.set()
        self._wake_event.set()
        if self._wake_word:
            self._wake_word.stop()


_pipeline_instance = None


def get_pipeline() -> VoicePipeline:
    global _pipeline_instance
    if _pipeline_instance is None:
        _pipeline_instance = VoicePipeline()
    return _pipeline_instance
