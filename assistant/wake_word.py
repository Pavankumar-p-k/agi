# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""assistant/wake_word.py
Two-stage wake word detection.
Stage 1: WebRTC VAD detects sustained voice in rolling buffer.
Stage 2: Faster-Whisper confirms phrase contains "hey jarvis" or "jarvis".
Runs confirmation in a separate thread so it never blocks the audio stream.
"""
from __future__ import annotations
import asyncio
import io
import threading
import time
import webrtcvad

from core.config_registry import config as _jarvis_config


SAMPLE_RATE = _jarvis_config.get("voice.sample_rate", 16000)
VAD_MODE = _jarvis_config.get("voice.vad_mode", 3)
ENERGY_THRESHOLD = _jarvis_config.get("voice.energy_threshold", 0.008)
REQUIRE_SPEECH_SECONDS = _jarvis_config.get("voice.require_speech_seconds", 1.2)


class RingBuffer:
    """Rolling float32 audio buffer. Keeps last N seconds. Thread-safe."""

    def __init__(self, max_seconds: float, sr: int = SAMPLE_RATE):
        import numpy as np
        self.max_samples = int(sr * max_seconds)
        self.buffer = np.zeros(self.max_samples, dtype=np.float32)
        self.pos = 0
        self.filled = False
        self._lock = threading.Lock()

    def write(self, data: np.ndarray):
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


class WakeWordDetector:
    """Two-stage wake word detector using VAD + Whisper.

    VAD runs in the audio callback thread (fast, non-blocking).
    Whisper confirmation runs in a worker thread (slow, but doesn't block audio).
    """

    COOLDOWN_ON_TRIGGER = _jarvis_config.get("voice.wake_cooldown_trigger", 5.0)
    COOLDOWN_ON_SKIP = _jarvis_config.get("voice.wake_cooldown_skip", 3.0)

    def __init__(self, sensitivity: float = 0.5):
        self.vad = webrtcvad.Vad(VAD_MODE)
        self.is_running = False
        self._thread = None
        self._worker_thread = None
        self.on_wake_word_callback = None
        self._state_lock = threading.Lock()
        self._cooldown_until = 0.0
        self._ring = RingBuffer(max_seconds=_jarvis_config.get("voice.ring_buffer_seconds", 4.0))
        self._pending_confirm = False
        self._speech_streak = 0
        self._async_loop = None
        # Sensitivity kept for future tuning and to avoid static-analysis false positives
        self.sensitivity = float(sensitivity)

    def get_recent_audio(self) -> bytes:
        """Return the ring buffer contents as WAV bytes (pre-roll for recording)."""
        import io, soundfile as sf
        audio = self._ring.read()
        if len(audio) == 0:
            return b""
        buf = io.BytesIO()
        sf.write(buf, audio, SAMPLE_RATE, format="WAV", subtype="PCM_16")
        return buf.getvalue()

    def snapshot_ring(self) -> bytes:
        """Snap ring buffer BEFORE clearing — call before clear() for preroll."""
        snap = self.get_recent_audio()
        self._ring.clear()
        return snap

    def start(self, callback):
        if self.is_running:
            return
        self.on_wake_word_callback = callback
        self.is_running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()

    def _run(self):
        import sounddevice as sd
        import numpy as np
        print("[WakeWord] Listening for 'Hey Jarvis'...")
        frame_ms = 30
        frame_size = int(SAMPLE_RATE * frame_ms / 1000)
        require_frames = int(REQUIRE_SPEECH_SECONDS / frame_ms * 1000)

        try:
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="int16",
                blocksize=frame_size,
            ) as stream:
                while self.is_running:
                    chunk, _ = stream.read(frame_size)
                    self._ring.write(chunk.astype(np.float32).squeeze() / 32768.0)

                    energy = float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))
                    has_energy = energy > ENERGY_THRESHOLD * 32768.0

                    is_speech = has_energy and self.vad.is_speech(chunk.tobytes(), SAMPLE_RATE)

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
        except Exception as e:
            print(f"[WakeWord] Stream error: {e}")
            self.is_running = False

    def _worker_loop(self):
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        self._async_loop = _loop
        try:
            while self.is_running:
                with self._state_lock:
                    pending = self._pending_confirm
                if pending:
                    _loop.run_until_complete(self._confirm_and_fire())
                time.sleep(0.1)
        finally:
            _loop.close()

    async def _confirm_and_fire(self):
        try:
            import soundfile as sf
            audio = self._ring.read()

            from assistant.stt import get_stt
            stt = get_stt()
            buf = io.BytesIO()
            sf.write(buf, audio, SAMPLE_RATE, format="WAV", subtype="PCM_16")
            text = (await stt.transcribe(buf.getvalue())).lower().strip()

            if text:
                print(f"[WakeWord] Heard: {text}")

            if text and self._is_wake_word(text):
                print(f"[WakeWord] Detected 'Hey Jarvis'!")
                with self._state_lock:
                    self._cooldown_until = time.time() + self.COOLDOWN_ON_TRIGGER
                    self._speech_streak = 0
                    self._pending_confirm = False
                if self.on_wake_word_callback:
                    self.on_wake_word_callback()
                self._ring.clear()
                return
            else:
                with self._state_lock:
                    self._cooldown_until = time.time() + self.COOLDOWN_ON_SKIP
        except Exception as e:
            print(f"[WakeWord] Confirm error: {e}")
            with self._state_lock:
                self._cooldown_until = time.time() + self.COOLDOWN_ON_SKIP

        self._ring.clear()
        with self._state_lock:
            self._speech_streak = 0
            self._pending_confirm = False

    @staticmethod
    def _is_wake_word(text: str) -> bool:
        t = text.lower().strip()
        exact = t.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
        if "hey jarvis" in exact:
            return True
        if exact.startswith("jarvis"):
            return True
        if "jarvis" in exact:
            return True
        for pat in ["hey jarvis", "hey jarvi", "jarvis", "jar wi"]:
            if pat in exact:
                return True
        return False

    def stop(self):
        self.is_running = False


_detector_instance = None
_detector_lock = threading.Lock()


def get_detector():
    global _detector_instance
    if _detector_instance is None:
        with _detector_lock:
            if _detector_instance is None:
                _detector_instance = WakeWordDetector()
    return _detector_instance
