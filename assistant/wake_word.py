# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""assistant.wake_word — local wake-word detection stack.

Rebuilt from the committed contracts in ``tests/unit/test_wake_word.py`` and
``tests/unit/test_phase5_reliability.py``:

- ``_levenshtein(a, b)`` classic edit distance scorer.
- ``_word_boundary_score(spoken, phrase)`` — 1.0 on exact match / containment,
  edit-distance penalized otherwise.
- ``WakeWordRegistry`` — phrase store with per-phrase ``min_confidence``;
  ``match(text)`` -> (best_phrase, best_score) when the best clears its
  threshold; ``count`` / ``phrases`` / ``remove`` / ``clear`` /
  ``load_from_config()`` (comma-separated ``voice.wake_word`` config key).
- ``WakeWordStats`` — detections/false-positives/missed counters plus capped
  latency samples (1000) and ``snapshot()`` reporting keys
  ``avg_stt_latency_ms`` / ``avg_total_latency_ms``; precision/recall derived
  ``accuracy`` and ``false_positive_rate``.
- ``RingBuffer`` — thread-safe fixed-length numpy float32 ring with ``write`/
  ``read``/``energy``/``clear``.
- ``WakeWordDetector`` — registry+stats+event; ``start()``/``stop()`` flip
  ``running``; ``check_detection()`` pops a set ``_detection_event``;
  ``status`` dict exposes running/phrases/stats; the audio/mic side degrades
  gracefully when ``sounddevice`` is unavailable.
- ``WatchdogService`` — owns one detector; restart-per-start semantics
  (``multiple_start_creates_new_detector``).
- ``get_detector()`` module singleton; ``get_existing_detector()`` returns the
  running watchdog's detector WITHOUT creating one (health-check contract).
"""
from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import numpy as np


def _get_config(key: str, default: Any = None) -> Any:
    """Config access seam — patched by tests; falls back to environment."""
    try:
        from core.configuration import configuration

        if configuration.get(key) is not None:
            return configuration.get(key)
    except Exception:  # noqa: BLE001 — config must never break detection
        pass
    import os

    return os.environ.get(key.upper().replace(".", "_"), default)


# ═════════════════════════════ string scoring ═══════════════════════════════
def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1,      # deletion
                           cur[j - 1] + 1,   # insertion
                           prev[j - 1] + (ca != cb)))  # substitution
        prev = cur
    return prev[-1]


def _word_boundary_score(spoken: str, phrase: str) -> float:
    """Match likelihood of *spoken* against the registered *phrase*.

    1.0 only for whole-word-boundary containment; otherwise lev-distance
    similarity discounted by length mismatch. "jarvis" does NOT match inside
    "jarvisaa" (no boundary at the tail).
    """
    s = re.sub(r"\s+", " ", (spoken or "").strip().lower())
    p = re.sub(r"\s+", " ", (phrase or "").strip().lower())
    if not s or not p:
        return 0.0
    if re.search(rf"\b{re.escape(p)}\b", s):
        return 1.0
    lev = _levenshtein(s, p)
    window = max(1, len(s) - len(p) + 1)
    best = min(_levenshtein(s[i:i + len(p)], p) for i in range(window))
    sim = 1.0 - best / max(len(p), 1)
    return max(0.0, min(0.99, sim))


# ═════════════════════════════ registry ════════════════════════════════════
class WakeWordRegistry:
    """Wake phrase store; strings compared lowercase, whitespace-normalized."""

    def __init__(self) -> None:
        self._phrases: dict[str, float] = {}

    # -- mutation ----------------------------------------------------------
    def add(self, phrase: str, min_confidence: float = 0.7) -> None:
        key = re.sub(r"\s+", " ", (phrase or "").strip().lower())
        if key:
            self._phrases[key] = float(min_confidence)

    def remove(self, phrase: str) -> None:
        self._phrases.pop(re.sub(r"\s+", " ", (phrase or "").strip().lower()), None)

    def clear(self) -> None:
        self._phrases.clear()

    def load_from_config(self) -> None:
        raw = _get_config("voice.wake_word", "") or ""
        confidence = float(_get_config("voice.wake_min_confidence", 0.7) or 0.7)
        for phrase in str(raw).split(","):
            self.add(phrase, min_confidence=confidence)

    # -- queries ------------------------------------------------------------
    @property
    def count(self) -> int:
        return len(self._phrases)

    @property
    def phrases(self) -> list[str]:
        return list(self._phrases)

    def match(self, spoken: str) -> Optional[tuple[str, float]]:
        best: Optional[tuple[str, float]] = None
        for phrase, threshold in self._phrases.items():
            score = _word_boundary_score(spoken, phrase)
            if score >= threshold and (
                best is None
                # tie-break on specificity: longer registered phrase wins
                or len(phrase) > len(best[0])
                or (len(phrase) == len(best[0]) and score > best[1])
            ):
                best = (phrase, score)
        return best


# ═════════════════════════════ stats ═══════════════════════════════════════
_MAX_LATENCY_SAMPLES = 1000


class WakeWordStats:
    """Detection quality counters with capped latency sample history."""

    def __init__(self) -> None:
        self.detections = 0
        self.false_positives = 0
        self.missed = 0
        self.stt_latency_ms: list[float] = []
        self.total_latency_ms: list[float] = []
        self.last_detection_time = 0.0

    def record_detection(self, stt_latency_ms: float, total_latency_ms: float) -> None:
        self.detections += 1
        self._push(self.stt_latency_ms, stt_latency_ms)
        self._push(self.total_latency_ms, total_latency_ms)
        self.last_detection_time = time.time()

    @staticmethod
    def _push(samples: list[float], value: float) -> None:
        samples.append(value)
        if len(samples) > _MAX_LATENCY_SAMPLES:
            del samples[: len(samples) - _MAX_LATENCY_SAMPLES]

    def record_false_positive(self) -> None:
        self.false_positives += 1

    def record_missed(self) -> None:
        self.missed += 1

    @property
    def avg_stt_latency(self) -> float:
        return sum(self.stt_latency_ms) / len(self.stt_latency_ms) if self.stt_latency_ms else 0.0

    @property
    def avg_total_latency(self) -> float:
        return sum(self.total_latency_ms) / len(self.total_latency_ms) if self.total_latency_ms else 0.0

    @property
    def accuracy(self) -> float:
        total = self.detections + self.missed
        return self.detections / total if total else 1.0

    @property
    def false_positive_rate(self) -> float:
        total = self.detections + self.false_positives + self.missed
        return self.false_positives / total if total else 0.0

    def snapshot(self) -> dict[str, Any]:
        return {
            "detections": self.detections,
            "false_positives": self.false_positives,
            "missed": self.missed,
            "avg_stt_latency_ms": self.avg_stt_latency,
            "avg_total_latency_ms": self.avg_total_latency,
            "accuracy": self.accuracy,
            "false_positive_rate": self.false_positive_rate,
            "last_detection_time": self.last_detection_time,
        }


# ═════════════════════════════ ring buffer ═════════════════════════════════
class RingBuffer:
    """Thread-safe fixed-duration float32 audio ring."""

    def __init__(self, max_seconds: float, sr: int) -> None:
        self._capacity = int(max_seconds * sr)
        self._buf = np.zeros(0, dtype=np.float32)
        self._lock = threading.Lock()

    def write(self, samples: np.ndarray) -> None:
        if not isinstance(samples, np.ndarray):
            samples = np.asarray(samples, dtype=np.float32)
        with self._lock:
            if self._buf.size:
                self._buf = np.concatenate([self._buf, samples.astype(np.float32)])
            else:
                self._buf = samples.astype(np.float32)
            if self._capacity and self._buf.size > self._capacity:
                self._buf = self._buf[-self._capacity:]

    def read(self) -> np.ndarray:
        with self._lock:
            out = self._buf
            self._buf = np.zeros(0, dtype=np.float32)
            return out.copy()

    def clear(self) -> None:
        with self._lock:
            self._buf = np.zeros(0, dtype=np.float32)

    def energy(self) -> float:
        with self._lock:
            if self._buf.size == 0:
                return 0.0
            return float(np.sqrt(np.mean(self._buf.astype(np.float64) ** 2)))

    def __len__(self) -> int:
        with self._lock:
            return self._buf.size


# ═════════════════════════════ detector ════════════════════════════════════
_DEFAULTS = {
    "voice.sample_rate": 16000,
    "voice.energy_threshold": 0.008,
    "voice.require_speech_seconds": 1.2,
    "voice.ring_buffer_seconds": 4.0,
    "voice.wake_cooldown_trigger": 5.0,
    "voice.wake_cooldown_skip": 3.0,
    "voice.mic_device": "",
    "voice.sensitivity_gain": 1.0,
    "voice.adaptive_threshold": True,
    "voice.frame_ms": 30,
    "voice.wake_min_confidence": 0.7,
    "voice.wake_word": "hey jarvis",
}


class WakeWordDetector:
    """Detects registered wake phrases; degrades without an audio backend."""

    def __init__(self, callback: Optional[Callable[[], None]] = None) -> None:
        self.registry = WakeWordRegistry()
        self.stats = WakeWordStats()
        self.callback = callback
        self.running = False
        self.detection_event = threading.Event()
        self._detection_event = self.detection_event  # internal alias (tests)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._ring: Optional[RingBuffer] = None
        self._load_from_config()

    # -- configuration ------------------------------------------------------
    def _load_from_config(self) -> None:
        raw = str(_get_config("voice.wake_word", "hey jarvis") or "hey jarvis")
        confidence = float(_get_config("voice.wake_min_confidence", 0.7) or 0.7)
        for phrase in raw.split(","):
            self.registry.add(phrase, min_confidence=confidence)

    def _read_config(self) -> dict[str, Any]:
        return {
            key.split(".", 1)[-1]: _get_config(key, dflt)
            for key, dflt in _DEFAULTS.items()
        }

    # -- lifecycle ------------------------------------------------------------
    def start(self) -> None:
        if self.running:
            return
        self._stop_event.clear()
        self.running = True
        try:
            from assistant.wake_word import _mic_loop_reader  # noqa: F401  (declared below)
        except ImportError:
            pass
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self.running = False

    def _run(self) -> None:
        # Audio capture is optional: degrade to idle when no sounddevice.
        try:
            import sounddevice  # noqa: F401

            available = True
        except Exception:  # noqa: BLE001
            available = False
        if not available:
            return
        self._listen_loop()

    def _listen_loop(self) -> None:
        cfg = self._read_config()
        sr = int(cfg.get("voice.sample_rate", 16000) or 16000)
        self._ring = RingBuffer(max_seconds=float(cfg.get("voice.ring_buffer_seconds", 4.0) or 4.0), sr=sr)
        import sounddevice as sd

        def _indata(indata, frames, _t, _status) -> None:
            if self._ring is not None:
                self._ring.write(indata[:, 0])

        with sd.InputStream(samplerate=sr, channels=1, dtype="float32", callback=_indata):
            while not self._stop_event.is_set():
                if self._ring is not None and self._ring.energy() > float(cfg.get("voice.energy_threshold", 0.008) or 0.008):
                    audio = self._ring.read()
                    try:
                        from assistant.stt import get_stt

                        text = get_stt().transcribe(audio.tobytes())
                    except Exception:  # noqa: BLE001 — detection must never crash
                        text = ""
                    if text and self.registry.match(text):
                        self._detection_event.set()
                        if self.callback:
                            try:
                                self.callback()
                            except Exception:  # noqa: BLE001
                                pass
                        time.sleep(float(cfg.get("voice.wake_cooldown_trigger", 5.0) or 5.0))
                time.sleep(0.05)

    # -- detection surface ------------------------------------------------------
    def check_detection(self) -> bool:
        if self._detection_event.is_set():
            self._detection_event.clear()
            return True
        return False

    @property
    def status(self) -> dict[str, Any]:
        return {
            "running": bool(self.running),
            "phrases": self.registry.phrases,
            "stats": self.stats.snapshot(),
        }

    def get_recent_audio(self) -> bytes:
        if self._ring is None:
            return b""
        return self._ring.read().tobytes()


# ═════════════════════════════ watchdog ════════════════════════════════════
class WatchdogService:
    """Owns a detector; each start() creates a fresh one (restart-safe)."""

    def __init__(self, callback: Optional[Callable[[], None]] = None) -> None:
        self._callback = callback
        self._detector: Optional[WakeWordDetector] = None
        self._lock = threading.Lock()

    @property
    def detector(self) -> Optional[WakeWordDetector]:
        return self._detector

    def start(self) -> WakeWordDetector:
        with self._lock:
            self.stop_locked()
            det = WakeWordDetector(callback=self._callback)
            det.start()
            self._detector = det
            return det

    def stop_locked(self) -> None:
        if self._detector is not None:
            self._detector.stop()
            self._detector = None

    def stop(self) -> None:
        with self._lock:
            self.stop_locked()


# ═════════════════════════ singleton surface ═══════════════════════════════
_watchdog_instance: Optional[WatchdogService] = None
_watchdog_lock = threading.Lock()


def get_detector(callback: Optional[Callable[[], None]] = None) -> WakeWordDetector:
    """Module-level detector singleton (creates + starts on first call)."""
    global _watchdog_instance
    with _watchdog_lock:
        if _watchdog_instance is None:
            _watchdog_instance = WatchdogService(callback=callback)
        return _watchdog_instance.start()


def get_existing_detector() -> Optional[WakeWordDetector]:
    """Currently-running detector or None — never constructs one."""
    watchdog = _watchdog_instance
    if watchdog is None:
        return None
    det = watchdog.detector
    if det is not None and det.running:
        return det
    return None


def reset_detector() -> None:
    """Test/global cleanup seam."""
    global _watchdog_instance
    with _watchdog_lock:
        if _watchdog_instance is not None:
            _watchdog_instance.stop()
        _watchdog_instance = None


__all__ = [
    "WakeWordRegistry", "WakeWordStats", "RingBuffer", "WakeWordDetector",
    "WatchdogService", "get_detector", "get_existing_detector",
    "reset_detector", "_levenshtein", "_word_boundary_score", "_get_config",
    "_watchdog_instance",
]
