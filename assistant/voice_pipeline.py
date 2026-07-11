"""assistant/voice_pipeline.py — Production-grade Voice Engine.
mic -> STT -> text -> llm_router -> response -> TTS -> speaker

Features:
- Auto-recovery for STT/TTS failures with configurable retry
- Device discovery and microphone/speaker switching
- Three modes: wake-word, continuous, push-to-talk
- Voice activity detection (VAD) for continuous mode
- Per-phase latency metrics
- Health checks with periodic status
- Thread-safe, memory-safe, no leaks
"""
from __future__ import annotations
import asyncio
import io
import logging
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from assistant.stt import get_stt, init_stt_providers, stt_registry
from assistant.tts import get_tts
from core.config_registry import config as _jarvis_config
from core.settings.store import get_settings_store


SYSTEM_PROMPT = _jarvis_config.get("voice.system_prompt") or (
    "You are JARVIS, a personal AI assistant. "
    "Be concise and direct. Answer in 1-3 sentences. "
    "Tell the user what you actually did — do NOT invent details that didn't happen."
)

SAMPLE_RATE = _jarvis_config.get("voice.sample_rate", 16000)


# ─── Metrics ────────────────────────────────────────────────────────────────

@dataclass
class VoiceMetrics:
    total_commands: int = 0
    successful_commands: int = 0
    failed_commands: int = 0
    stt_latency_ms: list[float] = field(default_factory=list)
    think_latency_ms: list[float] = field(default_factory=list)
    tts_latency_ms: list[float] = field(default_factory=list)
    total_latency_ms: list[float] = field(default_factory=list)
    stt_recoveries: int = 0
    tts_recoveries: int = 0
    stt_failures: int = 0
    tts_failures: int = 0
    vad_trigger_count: int = 0
    wake_word_count: int = 0

    def record_metrics(self, stt_ms: float, think_ms: float, tts_ms: float, total_ms: float) -> None:
        self.total_commands += 1
        self.successful_commands += 1
        self.stt_latency_ms.append(stt_ms)
        self.think_latency_ms.append(think_ms)
        self.tts_latency_ms.append(tts_ms)
        self.total_latency_ms.append(total_ms)
        if len(self.stt_latency_ms) > 1000:
            self.stt_latency_ms.pop(0)
            self.think_latency_ms.pop(0)
            self.tts_latency_ms.pop(0)
            self.total_latency_ms.pop(0)

    @property
    def avg_stt_latency(self) -> float:
        return sum(self.stt_latency_ms) / max(len(self.stt_latency_ms), 1)

    @property
    def avg_think_latency(self) -> float:
        return sum(self.think_latency_ms) / max(len(self.think_latency_ms), 1)

    @property
    def avg_tts_latency(self) -> float:
        return sum(self.tts_latency_ms) / max(len(self.tts_latency_ms), 1)

    @property
    def avg_total_latency(self) -> float:
        return sum(self.total_latency_ms) / max(len(self.total_latency_ms), 1)

    @property
    def success_rate(self) -> float:
        if self.total_commands == 0:
            return 1.0
        return self.successful_commands / max(self.total_commands, 1)

    def snapshot(self) -> dict[str, Any]:
        return {
            "total_commands": self.total_commands,
            "successful_commands": self.successful_commands,
            "failed_commands": self.failed_commands,
            "avg_stt_latency_ms": round(self.avg_stt_latency, 1),
            "avg_think_latency_ms": round(self.avg_think_latency, 1),
            "avg_tts_latency_ms": round(self.avg_tts_latency, 1),
            "avg_total_latency_ms": round(self.avg_total_latency, 1),
            "success_rate": round(self.success_rate, 3),
            "stt_recoveries": self.stt_recoveries,
            "tts_recoveries": self.tts_recoveries,
            "stt_failures": self.stt_failures,
            "tts_failures": self.tts_failures,
            "vad_trigger_count": self.vad_trigger_count,
            "wake_word_count": self.wake_word_count,
        }


# ─── Audio Device Manager ───────────────────────────────────────────────────

class AudioDeviceManager:
    """Discover and manage audio input/output devices."""

    @staticmethod
    def list_input_devices() -> list[dict[str, Any]]:
        try:
            import sounddevice as sd
            devices = []
            for i, dev in enumerate(sd.query_devices()):
                if dev["max_input_channels"] > 0:
                    devices.append({
                        "index": i,
                        "name": dev["name"],
                        "channels": dev["max_input_channels"],
                        "default_samplerate": dev["default_samplerate"],
                    })
            return devices
        except Exception as e:
            logger.warning("[AudioDevice] Failed to list input devices: %s", e)
            return []

    @staticmethod
    def list_output_devices() -> list[dict[str, Any]]:
        try:
            import sounddevice as sd
            devices = []
            for i, dev in enumerate(sd.query_devices()):
                if dev["max_output_channels"] > 0:
                    devices.append({
                        "index": i,
                        "name": dev["name"],
                        "channels": dev["max_output_channels"],
                        "default_samplerate": dev["default_samplerate"],
                    })
            return devices
        except Exception as e:
            logger.warning("[AudioDevice] Failed to list output devices: %s", e)
            return []

    @staticmethod
    def get_default_input() -> dict[str, Any] | None:
        try:
            import sounddevice as sd
            dev = sd.query_devices(kind="input")
            if dev is not None:
                return {"index": sd.default.device[0] if isinstance(sd.default.device, tuple) else sd.default.device, "name": dev["name"]}
            return None
        except Exception:
            return None

    @staticmethod
    def get_default_output() -> dict[str, Any] | None:
        try:
            import sounddevice as sd
            dev = sd.query_devices(kind="output")
            if dev is not None:
                return {"index": sd.default.device[1] if isinstance(sd.default.device, tuple) else sd.default.device, "name": dev["name"]}
            return None
        except Exception:
            return None

    @staticmethod
    def set_input_device(device_index: int) -> None:
        try:
            import sounddevice as sd
            current = sd.default.device
            if isinstance(current, tuple):
                sd.default.device = (device_index, current[1])
            else:
                sd.default.device = device_index
            _jarvis_config.set("voice.mic_device", str(device_index))
            logger.info("[AudioDevice] Input device set to index %d", device_index)
        except Exception as e:
            logger.warning("[AudioDevice] Failed to set input device: %s", e)
            raise

    @staticmethod
    def set_output_device(device_index: int) -> None:
        try:
            import sounddevice as sd
            current = sd.default.device
            if isinstance(current, tuple):
                sd.default.device = (current[0], device_index)
            else:
                sd.default.device = device_index
            _jarvis_config.set("voice.speaker_device", str(device_index))
            logger.info("[AudioDevice] Output device set to index %d", device_index)
        except Exception as e:
            logger.warning("[AudioDevice] Failed to set output device: %s", e)
            raise


# ─── Latency Tracker ────────────────────────────────────────────────────────

class LatencyTracker:
    """Track per-phase latency for voice processing."""

    def __init__(self):
        self._start: float = 0.0
        self._marks: dict[str, float] = {}

    def start(self) -> None:
        self._start = time.perf_counter()
        self._marks = {}

    def mark(self, name: str) -> float:
        now = time.perf_counter()
        self._marks[name] = now
        return now - self._start

    def elapsed(self, name: str) -> float:
        if name not in self._marks:
            return 0.0
        start = self._marks.get("start", self._start)
        return (self._marks[name] - start) * 1000

    def phase_ms(self, phase: str) -> float:
        phases = ["start", "stt_done", "think_done", "tts_done"]
        if phase not in self._marks:
            return 0.0
        idx = phases.index(phase) if phase in phases else -1
        if idx <= 0:
            return (self._marks[phase] - self._start) * 1000
        prev = phases[idx - 1]
        prev_time = self._marks.get(prev, self._start)
        return (self._marks[phase] - prev_time) * 1000


# ─── Health Monitor ─────────────────────────────────────────────────────────

class VoiceHealthMonitor:
    """Periodic health checks for STT and TTS providers."""

    def __init__(self, engine: "VoiceEngine"):
        self._engine = engine
        self._task: asyncio.Task | None = None
        self._interval = _jarvis_config.get("voice.recovery_interval", 5.0)
        self._last_checks: dict[str, dict[str, Any]] = {}
        self._healthy: dict[str, bool] = {"stt": False, "tts": False}

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        while True:
            try:
                await self._check_all()
            except Exception as e:
                logger.warning("[VoiceHealth] Check cycle failed: %s", e)
            await asyncio.sleep(self._interval)

    async def _check_all(self) -> None:
        stt_ok = await self._engine._check_stt_health()
        tts_ok = await self._engine._check_tts_health()
        old_stt = self._healthy.get("stt", False)
        old_tts = self._healthy.get("tts", False)
        self._healthy["stt"] = stt_ok
        self._healthy["tts"] = tts_ok

        if not stt_ok and old_stt:
            logger.warning("[VoiceHealth] STT became unhealthy — attempting recovery")
            asyncio.create_task(self._engine._recover_stt())
        if not tts_ok and old_tts:
            logger.warning("[VoiceHealth] TTS became unhealthy — attempting recovery")
            asyncio.create_task(self._engine._recover_tts())
        if stt_ok and not old_stt:
            logger.info("[VoiceHealth] STT recovered")
        if tts_ok and not old_tts:
            logger.info("[VoiceHealth] TTS recovered")

    @property
    def status(self) -> dict[str, Any]:
        return {
            "healthy": self._healthy,
            "last_checks": self._last_checks,
            "interval": self._interval,
        }


# ─── Voice Engine ───────────────────────────────────────────────────────────

class VoiceEngine:
    """Production-grade voice engine with auto-recovery, device management,
    multiple listening modes, VAD, latency metrics, and health checks."""

    MODE_WAKE_WORD = "wake-word"
    MODE_CONTINUOUS = "continuous"
    MODE_PUSH_TO_TALK = "push-to-talk"

    def __init__(self):
        self._stt = None
        self._tts = None
        self._lock = threading.Lock()
        self._settings = get_settings_store()
        self.metrics = VoiceMetrics()
        self.latency = LatencyTracker()
        self.health = VoiceHealthMonitor(self)
        self.devices = AudioDeviceManager()
        self._mode = _jarvis_config.get("voice.mode", self.MODE_PUSH_TO_TALK)
        self._wake_word = None
        self._wake_event = threading.Event()
        self._stop_event = threading.Event()
        self._loop_thread = None
        self._wake_lock = threading.Lock()
        self._wake_preroll = b""
        self._vad: Any = None
        self._push_to_talk_trigger: threading.Event | None = None
        self._continuous_listening: bool = False
        self._running: bool = False

    # ── Provider lazy loading ────────────────────────────────────────────

    @property
    def stt(self):
        if self._stt is None:
            with self._lock:
                if self._stt is None:
                    try:
                        if not stt_registry.list():
                            init_stt_providers()
                        self._stt = get_stt()
                    except Exception as e:
                        logger.warning("[VoiceEngine] STT init failed: %s", e)
                        raise
        return self._stt

    @stt.setter
    def stt(self, val):
        self._stt = val

    @property
    def tts(self):
        if self._tts is None:
            with self._lock:
                if self._tts is None:
                    try:
                        self._tts = get_tts()
                    except Exception as e:
                        logger.warning("[VoiceEngine] TTS init failed: %s", e)
                        raise
        return self._tts

    @tts.setter
    def tts(self, val):
        self._tts = val

    # ── Mode management ──────────────────────────────────────────────────

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> str:
        if mode not in (self.MODE_WAKE_WORD, self.MODE_CONTINUOUS, self.MODE_PUSH_TO_TALK):
            return f"Invalid mode: {mode}. Choose from: wake-word, continuous, push-to-talk"
        old = self._mode
        self._mode = mode
        _jarvis_config.set("voice.mode", mode)
        logger.info("[VoiceEngine] Mode changed: %s -> %s", old, mode)
        return f"Switched to {mode} mode"

    def set_mode_from_string(self, mode_str: str) -> str:
        return self.set_mode(mode_str.lower().strip())

    # ── Transcribe ───────────────────────────────────────────────────────

    async def transcribe(self, audio_bytes: bytes) -> str:
        stt = self.stt
        result = stt.transcribe(audio_bytes)
        if asyncio.iscoroutine(result):
            text = await result
        else:
            text = result
        return text

    # ── Think ─────────────────────────────────────────────────────────────

    async def think(self, text: str, emotion_context: dict | None = None) -> str:
        from core.pipeline.adapters.voice_adapter import voice_adapter
        reply = await voice_adapter(
            text=text,
            user_id=self._settings.get("user_id", "voice_user"),
            metadata={"emotion_context": emotion_context or {}},
        )
        return reply or ""

    # ── Speak ─────────────────────────────────────────────────────────────

    async def speak(self, text: str) -> bytes:
        loop = asyncio.get_running_loop()
        audio = await loop.run_in_executor(None, self.tts.synthesize, text)
        return audio

    # ── Audio Processing Pipeline ─────────────────────────────────────────

    async def process_audio(self, audio_bytes: bytes) -> bytes:
        self.latency.start()

        emotion_context = await self._detect_emotion(audio_bytes)
        self.latency.mark("stt_done")

        transcribed = await self.transcribe(audio_bytes)
        stt_ms = self.latency.phase_ms("stt_done")

        try:
            from brain.events import PluginEventBus
            asyncio.create_task(PluginEventBus.instance().emit("on_voice_command", text=transcribed))
        except Exception as e:
            logger.warning("[VoiceEngine] Plugin event failed: %s", e)

        if not transcribed:
            self.metrics.failed_commands += 1
            return await self.speak("Sorry, I didn't catch that. Could you please repeat?")

        response = await self.think(transcribed, emotion_context)
        self.latency.mark("think_done")
        think_ms = self.latency.phase_ms("think_done")

        if not response:
            self.metrics.failed_commands += 1
            return await self.speak("Sorry, I'm having trouble thinking right now.")

        audio_out = await self.speak(response)
        self.latency.mark("tts_done")
        tts_ms = self.latency.phase_ms("tts_done")
        total_ms = self.latency.elapsed("tts_done")

        self.metrics.record_metrics(stt_ms, think_ms, tts_ms, total_ms)
        return audio_out

    async def _detect_emotion(self, audio_bytes: bytes) -> dict:
        tmp_path = None
        try:
            import tempfile
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp.write(audio_bytes)
            tmp_path = tmp.name
            tmp.close()
            from core.audio_emotion import emotion_detector
            audio_ctx = await emotion_detector.analyze(tmp_path)
            result = audio_ctx.as_context_dict()
            if audio_ctx.is_urgent:
                logger.info("[VoiceEngine] Urgent emotion (%.2f confidence)", audio_ctx.confidence)
            return result
        except Exception as e:
            logger.warning("[VoiceEngine] Emotion detection: %s", e)
            return {}
        finally:
            if tmp_path:
                try:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                except PermissionError:
                    logger.warning("[VoiceEngine] Temp file in use: %s", tmp_path)
                except Exception as e:
                    logger.warning("[VoiceEngine] Temp file cleanup: %s", e)

    # ── Recording ─────────────────────────────────────────────────────────

    def record_audio(self, duration: int | None = None, sr: int | None = None) -> bytes:
        import sounddevice as sd
        import soundfile as sf
        sr = sr or SAMPLE_RATE
        duration = duration or _jarvis_config.get("voice.record_seconds", 5)
        device = self._get_mic_device()
        kwargs: dict[str, Any] = dict(samplerate=sr, channels=1, dtype="float32")
        if device is not None:
            kwargs["device"] = device
        recording = sd.rec(int(sr * duration), **kwargs)
        sd.wait()
        buf = io.BytesIO()
        sf.write(buf, recording, sr, format="WAV", subtype="PCM_16")
        return buf.getvalue()

    def _get_mic_device(self) -> int | None:
        dev_str = _jarvis_config.get("voice.mic_device", "")
        if dev_str:
            try:
                return int(dev_str)
            except (ValueError, TypeError):
                pass
        try:
            import sounddevice as sd
            for i, dev in enumerate(sd.query_devices()):
                if dev["max_input_channels"] > 0:
                    try:
                        with sd.InputStream(device=i, samplerate=16000, channels=min(dev["max_input_channels"], 1), dtype="int16", blocksize=480) as test:
                            test.read(480)
                        return i
                    except Exception:
                        continue
        except Exception:
            pass
        return None

    def _get_speaker_device(self) -> int | None:
        dev_str = _jarvis_config.get("voice.speaker_device", "")
        if dev_str:
            try:
                return int(dev_str)
            except (ValueError, TypeError):
                pass
        return None

    def play_audio(self, wav_bytes: bytes) -> None:
        import sounddevice as sd
        import soundfile as sf
        data, sr = sf.read(io.BytesIO(wav_bytes))
        device = self._get_speaker_device()
        kwargs: dict[str, Any] = {}
        if device is not None:
            kwargs["device"] = device
        sd.play(data, sr, **kwargs)
        sd.wait()

    def play_audio_async(self, wav_bytes: bytes) -> None:
        threading.Thread(target=self.play_audio, args=(wav_bytes,), daemon=True).start()

    # ── Auto-Recovery ─────────────────────────────────────────────────────

    async def _check_stt_health(self) -> bool:
        try:
            if self._stt is None:
                return False
            stt = self._stt
            if hasattr(stt, "health"):
                result = stt.health()
                if asyncio.iscoroutine(result):
                    return await result
                return bool(result)
            return True
        except Exception as e:
            logger.warning("[VoiceEngine] STT health check failed: %s", e)
            return False

    async def _check_tts_health(self) -> bool:
        try:
            if self._tts is None:
                return False
            tts = self._tts
            if hasattr(tts, "pipeline") and tts.pipeline is not None:
                return True
            return True
        except Exception as e:
            logger.warning("[VoiceEngine] TTS health check failed: %s", e)
            return False

    async def _recover_stt(self) -> bool:
        logger.info("[VoiceEngine] Attempting STT recovery...")
        for attempt in range(3):
            try:
                with self._lock:
                    try:
                        if not stt_registry.list():
                            init_stt_providers()
                        self._stt = get_stt()
                    except Exception:
                        self._stt = None
                if self._stt is not None:
                    stt = self._stt
                    if hasattr(stt, "health"):
                        result = stt.health()
                        if asyncio.iscoroutine(result):
                            ok = await result
                        else:
                            ok = bool(result)
                        if ok:
                            self.metrics.stt_recoveries += 1
                            logger.info("[VoiceEngine] STT recovered after attempt %d", attempt + 1)
                            return True
                await asyncio.sleep(1.0 * (attempt + 1))
            except Exception as e:
                logger.warning("[VoiceEngine] STT recovery attempt %d failed: %s", attempt + 1, e)
                await asyncio.sleep(1.0 * (attempt + 1))
        logger.error("[VoiceEngine] STT recovery failed after 3 attempts")
        self.metrics.stt_failures += 1
        return False

    async def _recover_tts(self) -> bool:
        logger.info("[VoiceEngine] Attempting TTS recovery...")
        for attempt in range(3):
            try:
                with self._lock:
                    try:
                        self._tts = get_tts()
                    except Exception:
                        self._tts = None
                if self._tts is not None:
                    self.metrics.tts_recoveries += 1
                    logger.info("[VoiceEngine] TTS recovered after attempt %d", attempt + 1)
                    return True
                await asyncio.sleep(1.0 * (attempt + 1))
            except Exception as e:
                logger.warning("[VoiceEngine] TTS recovery attempt %d failed: %s", attempt + 1, e)
                await asyncio.sleep(1.0 * (attempt + 1))
        logger.error("[VoiceEngine] TTS recovery failed after 3 attempts")
        self.metrics.tts_failures += 1
        return False

    async def check_and_recover(self) -> dict[str, bool]:
        stt_ok = await self._check_stt_health()
        tts_ok = await self._check_tts_health()
        if not stt_ok:
            stt_ok = await self._recover_stt()
        if not tts_ok:
            tts_ok = await self._recover_tts()
        return {"stt": stt_ok, "tts": tts_ok}

    # ── VAD for Continuous Mode ───────────────────────────────────────────

    def _init_vad(self) -> Any:
        try:
            import webrtcvad
            vad_mode = _jarvis_config.get("voice.vad_mode", 3)
            return webrtcvad.Vad(vad_mode)
        except Exception as e:
            logger.warning("[VoiceEngine] Failed to init VAD: %s", e)
            return None

    # ── Wake Word ─────────────────────────────────────────────────────────

    def _on_wake(self):
        if self._wake_word:
            try:
                with self._wake_lock:
                    preroll = self._wake_word.get_recent_audio()
                self._wake_preroll = preroll
            except Exception as e:
                logger.warning("[VoiceEngine] _on_wake failed: %s", e)
                self._wake_preroll = b""
        self.metrics.wake_word_count += 1
        self._wake_event.set()

    # ── Main Loop ─────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._stop_event.clear()

        if self._mode == self.MODE_WAKE_WORD:
            self._start_wake_word()
        elif self._mode == self.MODE_CONTINUOUS:
            self._start_continuous()
        elif self._mode == self.MODE_PUSH_TO_TALK:
            logger.info("[VoiceEngine] Push-to-talk mode — trigger via trigger_push_to_talk()")
            return

        self._loop_thread = threading.Thread(target=self._run_engine_loop, daemon=True)
        self._loop_thread.start()
        logger.info("[VoiceEngine] Started in %s mode", self._mode)

    def _start_wake_word(self) -> None:
        from assistant.wake_word import WakeWordDetector
        self._wake_word = WakeWordDetector()
        self._wake_word.start(self._on_wake)

    def _start_continuous(self) -> None:
        self._continuous_listening = True
        self._vad = self._init_vad()

    def _run_engine_loop(self) -> None:
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        try:
            _loop.run_until_complete(self._health_check_loop())
        finally:
            _loop.close()

    async def _health_check_loop(self) -> None:
        await self.health.start()
        consecutive_errors = 0
        try:
            while not self._stop_event.is_set():
                if self._mode == self.MODE_WAKE_WORD:
                    await self._wait_and_process_wake()
                elif self._mode == self.MODE_CONTINUOUS:
                    try:
                        await self._continuous_listen_cycle()
                    except Exception as e:
                        consecutive_errors += 1
                        if consecutive_errors >= 5:
                            logger.error("[VoiceEngine] Continuous mode failed after %d attempts, falling back to push-to-talk", consecutive_errors)
                            self._mode = self.MODE_PUSH_TO_TALK
                            continue
                        delay = min(consecutive_errors * 5, 60)
                        logger.warning("[VoiceEngine] Continuous listen cycle error (attempt %d): %s — retrying in %ds", consecutive_errors, e, delay)
                        await asyncio.sleep(delay)
                        continue
                else:
                    await asyncio.sleep(0.5)
                consecutive_errors = 0
        finally:
            await self.health.stop()

    async def _wait_and_process_wake(self) -> None:
        while not self._stop_event.is_set():
            self._wake_event.wait(timeout=1.0)
            if not self._wake_event.is_set():
                continue
            self._wake_event.clear()
            if self._stop_event.is_set():
                break
            try:
                preroll = self._wake_preroll
                with self._wake_lock:
                    self._wake_preroll = b""
                await asyncio.sleep(_jarvis_config.get("voice.post_wake_delay", 1.0))
                tail = b""
                if self._wake_word:
                    with self._wake_lock:
                        tail = self._wake_word.get_recent_audio()
                audio = self._combine_audio(preroll, tail)
                if not audio:
                    logger.warning("[VoiceEngine] No audio captured after wake")
                    continue
                logger.info("[VoiceEngine] Wake audio: %d bytes", len(audio))
                audio_out = await self.process_audio(audio)
                if audio_out:
                    self.play_audio_async(audio_out)
            except Exception as e:
                logger.warning("[VoiceEngine] Wake cycle error: %s", e)

    async def _continuous_listen_cycle(self) -> None:
        import sounddevice as sd
        import numpy as np
        continuous_timeout = _jarvis_config.get("voice.continuous_timeout", 30.0)
        frame_ms = 30
        frame_size = int(SAMPLE_RATE * frame_ms / 1000)
        energy_threshold = _jarvis_config.get("voice.energy_threshold", 0.008)
        require_speech_seconds = _jarvis_config.get("voice.require_speech_seconds", 1.2)
        require_frames = int(require_speech_seconds / frame_ms * 1000)

        device = self._get_mic_device()
        stream_kwargs: dict[str, Any] = dict(samplerate=SAMPLE_RATE, dtype="int16", blocksize=frame_size)
        if device is not None:
            stream_kwargs["device"] = device
            try:
                dev_info = sd.query_devices(device)
                stream_kwargs["channels"] = min(dev_info["max_input_channels"], 1)
            except Exception:
                stream_kwargs["channels"] = 1
        else:
            stream_kwargs["channels"] = 1

        try:
            with sd.InputStream(**stream_kwargs) as stream:
                speech_frames = 0
                silence_frames = 0
                audio_buffer: list[np.ndarray] = []
                recording = False
                last_speech_time = time.time()
                max_silence_frames = int(2.0 / frame_ms * 1000)

                while self._continuous_listening and not self._stop_event.is_set():
                    chunk, _ = stream.read(frame_size)
                    chunk_float = chunk.astype(np.float32).squeeze() / 32768.0
                    energy = float(np.sqrt(np.mean(chunk_float ** 2)))
                    is_speech = energy > energy_threshold

                    if self._vad is not None:
                        try:
                            is_speech = is_speech and self._vad.is_speech(chunk.tobytes(), SAMPLE_RATE)
                        except Exception:
                            pass

                    if is_speech:
                        speech_frames += 1
                        silence_frames = 0
                        audio_buffer.append(chunk_float)
                        last_speech_time = time.time()
                        if not recording and speech_frames >= require_frames:
                            recording = True
                            self.metrics.vad_trigger_count += 1
                            logger.info("[VoiceEngine] Continuous: speech started")
                    else:
                        silence_frames += 1
                        if recording:
                            audio_buffer.append(chunk_float)
                        if recording and silence_frames >= max_silence_frames:
                            recording = False
                            speech_frames = 0
                            silence_frames = 0
                            audio_data = np.concatenate(audio_buffer) if audio_buffer else np.array([], dtype=np.float32)
                            audio_buffer = []
                            if len(audio_data) > SAMPLE_RATE * 0.3:
                                await self._process_continuous_chunk(audio_data)
                        elif not recording:
                            speech_frames = max(0, speech_frames - 1)
                            audio_buffer = []

                    if time.time() - last_speech_time > continuous_timeout:
                        logger.info("[VoiceEngine] Continuous timeout reached")
                        break
        except Exception as e:
            logger.warning("[VoiceEngine] Continuous listen error: %s", e)
            raise

    async def _process_continuous_chunk(self, audio_data) -> None:
        buf = io.BytesIO()
        import soundfile as sf
        sf.write(buf, audio_data, SAMPLE_RATE, format="WAV", subtype="PCM_16")
        audio_bytes = buf.getvalue()
        logger.info("[VoiceEngine] Continuous audio: %d bytes", len(audio_bytes))
        try:
            audio_out = await self.process_audio(audio_bytes)
            if audio_out:
                self.play_audio_async(audio_out)
        except Exception as e:
            logger.warning("[VoiceEngine] Continuous processing failed: %s", e)

    def _combine_audio(self, preroll: bytes, tail: bytes) -> bytes:
        import soundfile as sf
        import numpy as np
        if preroll and tail:
            p_data, _ = sf.read(io.BytesIO(preroll))
            t_data, _ = sf.read(io.BytesIO(tail))
            combined = np.concatenate([p_data, t_data])
            buf = io.BytesIO()
            sf.write(buf, combined, SAMPLE_RATE, format="WAV", subtype="PCM_16")
            return buf.getvalue()
        elif preroll:
            return preroll
        elif tail:
            return tail
        return b""

    # ── Push-to-Talk ──────────────────────────────────────────────────────

    def trigger_push_to_talk(self) -> bytes:
        """Record and process a single utterance. Returns response audio bytes."""
        audio = self.record_audio()
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        try:
            result = _loop.run_until_complete(self.process_audio(audio))
            return result
        finally:
            _loop.close()

    async def trigger_push_to_talk_async(self) -> bytes:
        audio = await asyncio.to_thread(self.record_audio)
        return await self.process_audio(audio)

    async def record_and_process(self, duration: int | None = None) -> bytes:
        audio = await asyncio.to_thread(self.record_audio, duration)
        return await self.process_audio(audio)

    # ── Stop ──────────────────────────────────────────────────────────────

    def stop(self) -> None:
        self._running = False
        self._stop_event.set()
        self._wake_event.set()
        self._continuous_listening = False
        if self._wake_word:
            self._wake_word.stop()
            self._wake_word = None

    # ── Status ────────────────────────────────────────────────────────────

    @property
    def status(self) -> dict[str, Any]:
        return {
            "mode": self._mode,
            "running": self._running,
            "stt_loaded": self._stt is not None,
            "tts_loaded": self._tts is not None,
            "metrics": self.metrics.snapshot(),
            "health": self.health.status,
            "mic_device": self._get_mic_device(),
            "speaker_device": self._get_speaker_device(),
        }

    def health_report(self) -> dict[str, Any]:
        return self.status


# ── Backward Compatibility ───────────────────────────────────────────────────

class VoicePipeline(VoiceEngine):
    """Backward-compatible alias for VoiceEngine."""
    pass


class VoiceLoop:
    """Backward-compatible wrapper using VoiceEngine."""

    def __init__(self):
        self._engine = get_pipeline()
        self._wake_event = threading.Event()
        self._stop_event = threading.Event()
        self._loop_thread = None

    @property
    def pipeline(self):
        return self._engine

    def _on_wake(self):
        if self._engine._wake_word:
            try:
                with self._engine._wake_lock:
                    preroll = self._engine._wake_word.get_recent_audio()
                self._engine._wake_preroll = preroll
            except Exception as e:
                logger.warning("[VoiceLoop] _on_wake failed: %s", e)
        self._wake_event.set()

    def start(self):
        if not _jarvis_config.get("voice.wake_word_enabled", True):
            logger.info("[VoiceLoop] Wake word disabled in config.")
            return
        self._engine._wake_event = self._wake_event
        self._engine.start()
        self._loop_thread = threading.Thread(target=self._run_legacy_loop, daemon=True)
        self._loop_thread.start()
        print("[VoiceLoop] Started (legacy compat mode).")

    def _run_legacy_loop(self):
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        try:
            while not self._stop_event.is_set():
                self._wake_event.wait()
                self._wake_event.clear()
                if self._stop_event.is_set():
                    break
                try:
                    audio = self._engine.record_audio(duration=_jarvis_config.get("voice.record_seconds", 5))
                    if not audio:
                        continue
                    audio_out = _loop.run_until_complete(self._engine.process_audio(audio))
                    if audio_out:
                        self._engine.play_audio(audio_out)
                except Exception as e:
                    logger.warning("[VoiceLoop] Cycle error: %s", e)
        finally:
            _loop.close()

    def stop(self):
        self._stop_event.set()
        self._wake_event.set()
        self._engine.stop()


# ── Singleton ────────────────────────────────────────────────────────────────

_engine_instance: VoiceEngine | None = None
_engine_lock = threading.Lock()


def get_pipeline() -> VoiceEngine:
    global _engine_instance
    if _engine_instance is None:
        with _engine_lock:
            if _engine_instance is None:
                _engine_instance = VoiceEngine()
    return _engine_instance
