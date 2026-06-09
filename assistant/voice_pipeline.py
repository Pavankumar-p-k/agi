"""assistant/voice_pipeline.py — Unified voice pipeline.
mic -> STT -> text -> llm_router -> response -> TTS -> speaker
"""
from __future__ import annotations
import asyncio
import io
import logging
import os
import sys
import threading
import time

logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from assistant.stt import get_stt
from assistant.tts import get_tts
from core.config_registry import config as _jarvis_config
from core.llm_router import complete as llm_complete
from core.settings.store import get_settings_store


SYSTEM_PROMPT = _jarvis_config.get("voice.system_prompt") or (
    "You are JARVIS, a personal AI assistant. "
    "Be concise and direct. Answer in 1-3 sentences. "
    "Tell the user what you actually did — do NOT invent details that didn't happen."
)

RECORD_SECONDS = _jarvis_config.get("voice.record_seconds", 5)
SAMPLE_RATE = _jarvis_config.get("voice.sample_rate", 16000)


def _record_audio(duration: int = RECORD_SECONDS, sr: int = SAMPLE_RATE) -> bytes:
    import sounddevice as sd
    import soundfile as sf
    recording = sd.rec(int(sr * duration), samplerate=sr, channels=1, dtype="float32")
    sd.wait()
    buf = io.BytesIO()
    sf.write(buf, recording, sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def _play_audio(wav_bytes: bytes):
    import sounddevice as sd
    import soundfile as sf
    data, sr = sf.read(io.BytesIO(wav_bytes))
    sd.play(data, sr)
    sd.wait()


class VoicePipeline:
    """Unified STT -> LLM -> TTS pipeline with lazy-loaded models."""

    def __init__(self):
        self._stt = None
        self._tts = None
        self._lock = threading.Lock()
        self._settings = get_settings_store()

    @property
    def stt(self):
        if self._stt is None:
            with self._lock:
                if self._stt is None:
                    self._stt = get_stt()
        return self._stt

    @property
    def tts(self):
        if self._tts is None:
            with self._lock:
                if self._tts is None:
                    self._tts = get_tts()
        return self._tts

    async def transcribe(self, audio_bytes: bytes) -> str:
        result = self.stt.transcribe(audio_bytes)
        if asyncio.iscoroutine(result):
            text = await result
        else:
            text = result
        return text

    async def think(self, text: str, emotion_context: dict | None = None) -> str:
        system = SYSTEM_PROMPT
        if emotion_context and emotion_context.get("emotion_guidance"):
            system = f"{system}\n\n{emotion_context['emotion_guidance']}"
        model = "cloud" if self._settings.get("groq_api_key") else "automation"
        try:
            reply = (await llm_complete(
                model_group=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": text},
                ],
                timeout=_jarvis_config.get("voice.think_timeout", 10),
            )).unwrap_or("")
            return reply
        except Exception:
            logger.exception("[VoicePipeline] Cloud LLM failed, falling back to local")
        try:
            reply = (await llm_complete(
                model_group="automation",
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": text},
                ],
                timeout=_jarvis_config.get("voice.think_timeout_fallback", 15),
            )).unwrap_or("")
            return reply
        except Exception as e:
            logger.exception("[VoicePipeline] Local LLM also failed: %s", e)
            return ""

    async def speak(self, text: str) -> bytes:
        loop = asyncio.get_running_loop()
        audio = await loop.run_in_executor(None, self.tts.synthesize, text)
        return audio

    async def process_audio(self, audio_bytes: bytes) -> bytes:
        emotion_context = {}
        try:
            import tempfile
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp.write(audio_bytes)
            tmp_path = tmp.name
            tmp.close()
            from core.audio_emotion import emotion_detector
            audio_ctx = await emotion_detector.analyze(tmp_path)
            emotion_context = audio_ctx.as_context_dict()
            if audio_ctx.is_urgent:
                logger.info("Voice: urgent emotion detected (%.2f confidence)", audio_ctx.confidence)
            os.unlink(tmp_path)
        except Exception as e:
            logger.exception("[VoicePipeline] process_audio emotion: %s", e)

        transcribed = await self.transcribe(audio_bytes)

        # Phase 3: Emit hook
        try:
            from core.plugins.events import PluginEventBus
            asyncio.create_task(PluginEventBus.instance().emit("on_voice_command", text=transcribed))
        except Exception as e:
            logger.warning("[assistant.voice_pipeline] process_voice_command failed: %s", e)

        if not transcribed:
            return await self.speak("Sorry, I didn't catch that. Could you please repeat?")
        response = await self.think(transcribed, emotion_context)
        if not response:
            return await self.speak("Sorry, I'm having trouble thinking right now.")
        audio_out = await self.speak(response)
        return audio_out


class VoiceLoop:
    def __init__(self):
        self.pipeline = get_pipeline()
        self._settings = get_settings_store()
        self._wake_word = None
        self._wake_event = threading.Event()
        self._stop_event = threading.Event()
        self._loop_thread = None
        self._wake_lock = threading.Lock()
        self._wake_preroll = b""

    def _on_wake(self):
        if self._wake_word:
            try:
                preroll = b""
                with self._wake_lock:
                    preroll = self._wake_word.get_recent_audio()
                self._wake_preroll = preroll
            except Exception as e:
                logger.exception("[VoicePipeline] _on_wake get_recent_audio: %s", e)
                self._wake_preroll = b""
        self._wake_event.set()

    def start(self):
        if not self._settings.get("voice.wake_word_enabled"):
            logger.info("[VoiceLoop] Wake word detector disabled in settings.")
            return
        from assistant.wake_word import WakeWordDetector
        self._wake_word = WakeWordDetector()
        self._wake_word.start(self._on_wake)
        self._loop_thread = threading.Thread(target=self._run_loop, daemon=True)
        self._loop_thread.start()
        print("[VoiceLoop] Started. Say 'Hey Jarvis' to activate.")

    def _run_loop(self):
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        try:
            while not self._stop_event.is_set():
                self._wake_event.wait()
                self._wake_event.clear()
                if self._stop_event.is_set():
                    break
                try:
                    preroll = self._wake_preroll
                    with self._wake_lock:
                        self._wake_preroll = b""
                    time.sleep(3)
                    tail = b""
                    if self._wake_word:
                        with self._wake_lock:
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
                        logger.warning("[VoiceLoop] No audio captured")
                        continue
                    logger.info("[VoiceLoop] Audio: %d bytes, transcribing...", len(audio))
                    audio_out = _loop.run_until_complete(self.pipeline.process_audio(audio))
                    if audio_out:
                        logger.info("[VoiceLoop] Got %d bytes, playing...", len(audio_out))
                        _play_audio(audio_out)
                        logger.info("[VoiceLoop] Response played")
                    else:
                        logger.warning("[VoiceLoop] No audio output from pipeline")
                except Exception as e:
                    logger.exception("[VoiceLoop] Error in cycle: %s", e)
        finally:
            _loop.close()

    def stop(self):
        self._stop_event.set()
        self._wake_event.set()
        if self._wake_word:
            self._wake_word.stop()


_pipeline_instance = None
_pipeline_lock = threading.Lock()


def get_pipeline() -> VoicePipeline:
    global _pipeline_instance
    if _pipeline_instance is None:
        with _pipeline_lock:
            if _pipeline_instance is None:
                _pipeline_instance = VoicePipeline()
    return _pipeline_instance
