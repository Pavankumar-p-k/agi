"""assistant/wake_word.py — Production-grade wake word detection.

Architecture:
  Stage 1: WebRTC VAD + energy threshold in audio thread (non-blocking, 30ms frames)
  Stage 2: Faster-Whisper confirmation in worker thread (never blocks audio)
  Watchdog: Auto-restarts detector on crash with exponential backoff

Features:
  - Custom wake words via WakeWordRegistry
  - False-positive filtering (word boundaries, confidence scoring, Levenshtein distance)
  - CPU optimization (adaptive sleep: 1s idle -> 10ms active)
  - Sensitivity tuning (gain + adaptive energy threshold)
  - Multi-microphone (configurable device index)
  - Auto-restart on crash (3 retries with exponential backoff)
  - Per-detection latency and accuracy statistics
"""
from __future__ import annotations
import asyncio
import io
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ── Config Helper ───────────────────────────────────────────────────────────

def _get_config(key: str, default: Any = None) -> Any:
    try:
        from core.config_registry import config as _c
        return _c.get(key, default)
    except Exception:
        return default


def _get_wake_phrases() -> list[str]:
    raw = _get_config("voice.wake_word", "hey jarvis")
    if isinstance(raw, str):
        return [p.strip().lower() for p in raw.split(",") if p.strip()]
    return list(raw) if isinstance(raw, (list, tuple)) else ["hey jarvis"]


# ── Levenshtein Distance ─────────────────────────────────────────────────────

def _levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            cost = 0 if ca == cb else 1
            curr.append(min(curr[j] + 1, prev[j + 1] + 1, prev[j] + cost))
        prev = curr
    return prev[-1]


def _word_boundary_score(text: str, phrase: str) -> float:
    text_lower = text.lower().strip()
    phrase_lower = phrase.lower().strip()
    if not text_lower or not phrase_lower:
        return 0.0

    words = text_lower.split()
    phrase_words = phrase_lower.split()
    p_len = len(phrase_words)

    best = 0.0
    for i in range(len(words) - p_len + 1):
        window = " ".join(words[i:i + p_len])
        dist = _levenshtein(window, phrase_lower)
        max_len = max(len(window), len(phrase_lower))
        if max_len == 0:
            score = 1.0
        else:
            score = 1.0 - (dist / max_len)
        if score > best:
            best = score
    return best


# ── Wake Word Registry ───────────────────────────────────────────────────────

class WakeWordRegistry:
    """Manages wake word phrases with phonetic-aware matching and confidence scoring."""

    def __init__(self):
        self._phrases: dict[str, float] = {}
        self._lock = threading.Lock()

    def add(self, phrase: str, min_confidence: float = 0.7) -> None:
        with self._lock:
            self._phrases[phrase.lower().strip()] = min_confidence

    def remove(self, phrase: str) -> None:
        with self._lock:
            self._phrases.pop(phrase.lower().strip(), None)

    def clear(self) -> None:
        with self._lock:
            self._phrases.clear()

    def load_from_config(self) -> None:
        phrases = _get_wake_phrases()
        min_conf = _get_config("voice.wake_min_confidence", 0.6)
        with self._lock:
            self._phrases.clear()
            for p in phrases:
                self._phrases[p] = min_conf

    def match(self, text: str) -> tuple[str, float] | None:
        """Returns (matched_phrase, confidence) or None if no match."""
        if not text:
            return None
        with self._lock:
            if not self._phrases:
                return None
            best_phrase = None
            best_score = 0.0
            for phrase, min_conf in self._phrases.items():
                score = _word_boundary_score(text, phrase)
                if score > best_score or (score == best_score and len(phrase) > len(best_phrase or "")):
                    best_score = score
                    best_phrase = phrase
            if best_phrase and best_score >= self._phrases[best_phrase]:
                return (best_phrase, best_score)
        return None

    @property
    def phrases(self) -> list[str]:
        with self._lock:
            return list(self._phrases.keys())

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._phrases)


# ── Ring Buffer ──────────────────────────────────────────────────────────────

class RingBuffer:
    """Rolling float32 audio buffer. Keeps last N seconds. Thread-safe."""

    def __init__(self, max_seconds: float, sr: int = 16000):
        import numpy as np
        self.max_samples = int(sr * max_seconds)
        self.buffer = np.zeros(max(self.max_samples, 1), dtype=np.float32)
        self.pos = 0
        self.filled = False
        self._lock = threading.Lock()

    def write(self, data):
        import numpy as np
        with self._lock:
            n = len(data)
            if n > self.max_samples:
                data = data[-self.max_samples:]
                n = self.max_samples
            if self.pos + n <= self.max_samples:
                self.buffer[self.pos:self.pos + n] = data
                if self.pos + n == self.max_samples:
                    self.filled = True
            else:
                first = self.max_samples - self.pos
                self.buffer[self.pos:] = data[:first]
                self.buffer[:n - first] = data[first:]
                self.filled = True
            self.pos = (self.pos + n) % self.max_samples

    def read(self):
        import numpy as np
        with self._lock:
            if not self.filled:
                return self.buffer[:self.pos].copy()
            return np.concatenate([
                self.buffer[self.pos:],
                self.buffer[:self.pos]
            ])

    def energy(self) -> float:
        import numpy as np
        data = self.read()
        if len(data) == 0:
            return 0.0
        return float(np.sqrt(np.mean(data ** 2)))

    def clear(self):
        with self._lock:
            self.buffer.fill(0)
            self.pos = 0
            self.filled = False


# ── Statistics ───────────────────────────────────────────────────────────────

@dataclass
class WakeWordStats:
    detections: int = 0
    false_positives: int = 0
    missed: int = 0
    stt_latency_ms: list[float] = field(default_factory=list)
    total_latency_ms: list[float] = field(default_factory=list)
    last_detection_time: float = 0.0

    def record_detection(self, stt_ms: float, total_ms: float) -> None:
        self.detections += 1
        self.last_detection_time = time.time()
        self.stt_latency_ms.append(stt_ms)
        self.total_latency_ms.append(total_ms)
        if len(self.stt_latency_ms) > 1000:
            self.stt_latency_ms.pop(0)
            self.total_latency_ms.pop(0)

    def record_false_positive(self) -> None:
        self.false_positives += 1

    def record_missed(self) -> None:
        self.missed += 1

    @property
    def avg_stt_latency(self) -> float:
        return sum(self.stt_latency_ms) / max(len(self.stt_latency_ms), 1)

    @property
    def avg_total_latency(self) -> float:
        return sum(self.total_latency_ms) / max(len(self.total_latency_ms), 1)

    @property
    def accuracy(self) -> float:
        total = self.detections + self.missed
        if total == 0:
            return 1.0
        return self.detections / total

    @property
    def false_positive_rate(self) -> float:
        total = self.detections + self.false_positives
        if total == 0:
            return 0.0
        return self.false_positives / total

    def snapshot(self) -> dict[str, Any]:
        return {
            "detections": self.detections,
            "false_positives": self.false_positives,
            "missed": self.missed,
            "avg_stt_latency_ms": round(self.avg_stt_latency, 1),
            "avg_total_latency_ms": round(self.avg_total_latency, 1),
            "accuracy": round(self.accuracy, 4),
            "false_positive_rate": round(self.false_positive_rate, 4),
            "last_detection_ago": (time.time() - self.last_detection_time) if self.last_detection_time else -1,
        }


# ── Wake Word Detector ──────────────────────────────────────────────────────

class WakeWordDetector:
    """Two-stage wake word detector with VAD + Whisper confirmation.

    Stage 1: WebRTC VAD + energy threshold runs in audio callback thread.
    Stage 2: Faster-Whisper confirmation runs in a separate worker thread.

    Features:
      - Custom wake words via WakeWordRegistry
      - Configurable sensitivity (gain + dynamic threshold)
      - Multi-microphone support via voice.mic_device
      - Adaptive sleep for CPU optimization
      - False-positive filtering via word boundary + confidence scoring
      - Per-detection latency and accuracy stats
    """

    def __init__(self, callback: Callable[[], None] | None = None):
        self.callback = callback
        self.is_running = False
        self._thread: threading.Thread | None = None
        self._worker_thread: threading.Thread | None = None
        self._state_lock = threading.Lock()
        self._cooldown_until = 0.0
        self._ring: RingBuffer | None = None
        self._pending_confirm = False
        self._speech_streak = 0
        self._noise_floor = 0.001
        self._noise_samples = 0
        self._vad = None
        self.registry = WakeWordRegistry()
        self.stats = WakeWordStats()
        self.registry.load_from_config()
        self._detection_event = threading.Event()

    def get_recent_audio(self) -> bytes:
        import soundfile as sf
        if self._ring is None:
            return b""
        audio = self._ring.read()
        if len(audio) == 0:
            return b""
        buf = io.BytesIO()
        sr = _get_config("voice.sample_rate", 16000)
        sf.write(buf, audio, sr, format="WAV", subtype="PCM_16")
        return buf.getvalue()

    def start(self, callback: Callable[[], None] | None = None) -> None:
        if self.is_running:
            return
        if callback is not None:
            self.callback = callback
        self.is_running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()

    def _read_config(self) -> dict:
        return {
            "sr": _get_config("voice.sample_rate", 16000),
            "vad_mode": _get_config("voice.vad_mode", 3),
            "energy_threshold": _get_config("voice.energy_threshold", 0.008),
            "require_speech_seconds": _get_config("voice.require_speech_seconds", 1.2),
            "ring_buffer_seconds": _get_config("voice.ring_buffer_seconds", 4.0),
            "cooldown_trigger": _get_config("voice.wake_cooldown_trigger", 5.0),
            "cooldown_skip": _get_config("voice.wake_cooldown_skip", 3.0),
            "mic_device": _get_config("voice.mic_device", ""),
            "sensitivity_gain": _get_config("voice.sensitivity_gain", 1.0),
            "adaptive_threshold": _get_config("voice.adaptive_threshold", True),
            "frame_ms": _get_config("voice.frame_ms", 30),
        }

    def _run(self):
        import numpy as np
        import sounddevice as sd
        import webrtcvad

        cfg = self._read_config()
        sr = cfg["sr"]
        if sr not in (8000, 16000, 32000, 48000):
            logger.warning("[WakeWord] Sample rate %d not supported by WebRTC VAD, using 16000", sr)
            sr = 16000
        frame_ms = cfg["frame_ms"]
        frame_size = int(sr * frame_ms / 1000)
        require_frames = int(cfg["require_speech_seconds"] / frame_ms * 1000)
        energy_threshold = cfg["energy_threshold"]
        sensitivity_gain = cfg["sensitivity_gain"]
        adaptive = cfg["adaptive_threshold"]

        self._vad = webrtcvad.Vad(cfg["vad_mode"])
        ring_seconds = cfg["ring_buffer_seconds"]
        self._ring = RingBuffer(max_seconds=ring_seconds, sr=sr)
        
        device = self._parse_device(cfg["mic_device"])
        if device is None:
            device = self._auto_detect_input_device()
        stream_kw = dict(samplerate=sr, dtype="int16", blocksize=frame_size)
        if device is not None:
            stream_kw["device"] = device
            try:
                import sounddevice as sd
                dev_info = sd.query_devices(device)
                stream_kw["channels"] = min(dev_info["max_input_channels"], 1)
            except Exception:
                stream_kw["channels"] = 1
        else:
            stream_kw["channels"] = 1

        wake_phrases_str = ", ".join(self.registry.phrases) or "jarvis"
        logger.info("[WakeWord] Listening for: %s (device=%s, sr=%d, gain=%.2f, channels=%d)",
                     wake_phrases_str, device or "default", sr, sensitivity_gain, stream_kw["channels"])

        try:
            with sd.InputStream(**stream_kw) as stream:
                while self.is_running:
                    self._run_frame(stream, frame_size, sr, energy_threshold,
                                    sensitivity_gain, adaptive, require_frames)
        except Exception as e:
            logger.warning("[WakeWord] Stream failed: %s", e)
            self.is_running = False

    def _auto_detect_input_device(self) -> int | None:
        try:
            import sounddevice as sd
            for i, dev in enumerate(sd.query_devices()):
                if dev["max_input_channels"] > 0:
                    try:
                        with sd.InputStream(device=i, samplerate=16000, channels=min(dev["max_input_channels"], 1), dtype="int16", blocksize=480) as test:
                            test.read(480)
                        logger.info("[WakeWord] Auto-selected input device %d: %s (%d ch)", i, dev["name"], dev["max_input_channels"])
                        return i
                    except Exception:
                        continue
        except Exception as e:
            logger.warning("[WakeWord] No input device found: %s", e)
        return None

    def _parse_device(self, dev_str: str) -> int | None:
        if dev_str:
            try:
                return int(dev_str)
            except (ValueError, TypeError):
                try:
                    import sounddevice as sd
                    devices = sd.query_devices()
                    for i, d in enumerate(devices):
                        if dev_str.lower() in d["name"].lower() and d["max_input_channels"] > 0:
                            return i
                except Exception:
                    pass
        return None

    def _run_frame(self, stream, frame_size, sr, energy_threshold, gain, adaptive, require_frames):
        import numpy as np
        chunk, _ = stream.read(frame_size)
        chunk_float = chunk.astype(np.float32).squeeze() / 32768.0

        if gain != 1.0:
            chunk_float = np.clip(chunk_float * gain, -1.0, 1.0)

        if self._ring is not None:
            self._ring.write(chunk_float)

        energy = float(np.sqrt(np.mean(chunk_float ** 2)))

        if adaptive:
            self._update_noise_floor(energy)
            dynamic_threshold = max(energy_threshold, self._noise_floor * 3.0)
        else:
            dynamic_threshold = energy_threshold

        has_energy = energy > dynamic_threshold

        try:
            is_speech = has_energy and self._vad.is_speech(chunk.tobytes(), sr)
        except Exception:
            is_speech = has_energy

        with self._state_lock:
            if self._pending_confirm:
                self._speech_streak = 0
            elif is_speech:
                self._speech_streak += 1
            else:
                self._speech_streak = max(0, self._speech_streak - 1)

            if (self._speech_streak > require_frames
                    and time.time() > self._cooldown_until
                    and not self._pending_confirm):
                self._speech_streak = 0
                self._pending_confirm = True

    def _update_noise_floor(self, energy: float) -> None:
        alpha = 0.01
        if energy < self._noise_floor * 1.5:
            self._noise_floor = (1 - alpha) * self._noise_floor + alpha * energy
            self._noise_samples += 1
        elif self._noise_samples < 50:
            self._noise_floor = (1 - alpha) * self._noise_floor + alpha * energy
            self._noise_samples += 1

    def _worker_loop(self):
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        try:
            last_activity = time.time()
            while self.is_running:
                with self._state_lock:
                    pending = self._pending_confirm
                if pending:
                    _loop.run_until_complete(self._confirm_and_fire())
                    last_activity = time.time()
                    sleep_time = 0.01
                else:
                    idle_time = time.time() - last_activity
                    if idle_time > 30:
                        sleep_time = 1.0
                    elif idle_time > 10:
                        sleep_time = 0.5
                    elif idle_time > 5:
                        sleep_time = 0.2
                    else:
                        sleep_time = 0.05
                time.sleep(sleep_time)
        finally:
            _loop.close()

    async def _confirm_and_fire(self):
        import soundfile as sf
        cfg = self._read_config()
        sr = cfg["sr"]
        start_time = time.time()

        try:
            audio = self._ring.read()
            buf = io.BytesIO()
            sf.write(buf, audio, sr, format="WAV", subtype="PCM_16")
            audio_bytes = buf.getvalue()

            stt_start = time.time()
            from assistant.stt import get_stt
            stt = get_stt()
            text = (await stt.transcribe(audio_bytes)).lower().strip()
            stt_ms = (time.time() - stt_start) * 1000

            if text:
                logger.info("[WakeWord] Heard: %.80s", text)

            if text:
                match = self.registry.match(text)
                if match:
                    phrase, score = match
                    total_ms = (time.time() - start_time) * 1000
                    self.stats.record_detection(stt_ms, total_ms)
                    logger.info("[WakeWord] Detected '%s' (score=%.2f, stt=%.0fms, total=%.0fms)",
                                phrase, score, stt_ms, total_ms)
                    with self._state_lock:
                        self._cooldown_until = time.time() + cfg["cooldown_trigger"]
                        self._speech_streak = 0
                        self._pending_confirm = False
                    self._ring.clear()
                    self._detection_event.set()
                    if self.callback:
                        self.callback()
                    return
                else:
                    logger.debug("[WakeWord] No match for: %.60s", text)
                    self.stats.record_false_positive()

            with self._state_lock:
                self._cooldown_until = time.time() + cfg["cooldown_skip"]

        except Exception as e:
            logger.exception("[WakeWord] Confirm error: %s", e)
            with self._state_lock:
                self._cooldown_until = time.time() + cfg["cooldown_skip"]

        self._ring.clear()
        with self._state_lock:
            self._speech_streak = 0
            self._pending_confirm = False

    def stop(self):
        self.is_running = False

    @property
    def running(self) -> bool:
        return self.is_running

    @property
    def status(self) -> dict[str, Any]:
        return {
            "running": self.is_running,
            "phrases": self.registry.phrases,
            "stats": self.stats.snapshot(),
        }

    def check_detection(self) -> bool:
        """Non-blocking check if a wake word was detected since last call."""
        if self._detection_event.is_set():
            self._detection_event.clear()
            return True
        return False

    @property
    def detection_event(self) -> threading.Event:
        return self._detection_event


# ── Watchdog Service ─────────────────────────────────────────────────────────

class WatchdogService:
    """Auto-restarts WakeWordDetector on crash with exponential backoff."""

    def __init__(self, callback: Callable[[], None] | None = None):
        self._callback = callback
        self._detector: WakeWordDetector | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._max_retries = _get_config("voice.wake_max_retries", 3)
        self._base_delay = _get_config("voice.wake_retry_delay", 1.0)

    def start(self) -> WakeWordDetector:
        self._stop_event.clear()
        self._detector = WakeWordDetector(callback=self._callback)
        self._detector.start()
        self._thread = threading.Thread(target=self._watchdog_loop, daemon=True)
        self._thread.start()
        logger.info("[Watchdog] Wake word detector started")
        return self._detector

    def _watchdog_loop(self):
        attempts = 0
        while not self._stop_event.is_set():
            if self._detector and not self._detector.is_running:
                attempts += 1
                if attempts > self._max_retries:
                    logger.error("[Watchdog] Max retries (%d) reached, giving up wake word detection", self._max_retries)
                    break
                delay = self._base_delay * (2 ** (attempts - 1))
                logger.warning("[Watchdog] Detector died (attempt %d/%d), restarting in %.1fs",
                               attempts, self._max_retries, delay)
                self._stop_event.wait(timeout=delay)
                if self._stop_event.is_set():
                    break
                try:
                    new_detector = WakeWordDetector(callback=self._callback)
                    new_detector.start()
                    self._detector = new_detector
                    logger.info("[Watchdog] Detector restarted (attempt %d)", attempts)
                except Exception as e:
                    logger.exception("[Watchdog] Restart failed: %s", e)
            else:
                self._stop_event.wait(timeout=1.0)

    def stop(self):
        self._stop_event.set()
        if self._detector:
            self._detector.stop()

    @property
    def detector(self) -> WakeWordDetector | None:
        return self._detector


# ── Backward-Compatible Singleton ────────────────────────────────────────────

_watchdog_instance: WatchdogService | None = None
_watchdog_lock = threading.Lock()


def get_detector() -> WakeWordDetector:
    """Get or create the wake word detector via watchdog service."""
    global _watchdog_instance
    if _watchdog_instance is None:
        with _watchdog_lock:
            if _watchdog_instance is None:
                _watchdog_instance = WatchdogService()
                _watchdog_instance.start()
    return _watchdog_instance.detector
