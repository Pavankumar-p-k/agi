"""assistant/wake_word.py
Two-stage wake word detection.
Stage 1: WebRTC VAD detects sustained voice in rolling buffer.
Stage 2: Faster-Whisper confirms phrase contains "hey jarvis" or "jarvis".
Runs confirmation in a separate thread so it never blocks the audio stream.
"""
import io
import threading
import time
import webrtcvad
import numpy as np
import sounddevice as sd
import soundfile as sf


SAMPLE_RATE = 16000
VAD_MODE = 3
ENERGY_THRESHOLD = 0.008
REQUIRE_SPEECH_SECONDS = 1.2


class RingBuffer:
    """Rolling float32 audio buffer. Keeps last N seconds."""

    def __init__(self, max_seconds: float, sr: int = SAMPLE_RATE):
        self.max_samples = int(sr * max_seconds)
        self.buffer = np.zeros(self.max_samples, dtype=np.float32)
        self.pos = 0
        self.filled = False

    def write(self, data: np.ndarray):
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

    def read(self) -> np.ndarray:
        if not self.filled:
            return self.buffer[:self.pos].copy()
        return np.concatenate([
            self.buffer[self.pos:],
            self.buffer[:self.pos]
        ])

    def energy(self) -> float:
        data = self.read()
        if len(data) == 0:
            return 0.0
        return float(np.sqrt(np.mean(data ** 2)))

    def clear(self):
        self.buffer.fill(0)
        self.pos = 0
        self.filled = False


class WakeWordDetector:
    """Two-stage wake word detector using VAD + Whisper.

    VAD runs in the audio callback thread (fast, non-blocking).
    Whisper confirmation runs in a worker thread (slow, but doesn't block audio).
    """

    COOLDOWN_ON_TRIGGER = 5.0
    COOLDOWN_ON_SKIP = 3.0

    def __init__(self, sensitivity: float = 0.5):
        self.vad = webrtcvad.Vad(VAD_MODE)
        self.is_running = False
        self._thread = None
        self._worker_thread = None
        self.on_wake_word_callback = None
        self._cooldown_until = 0.0
        self._ring = RingBuffer(max_seconds=4.0)
        self._pending_confirm = False
        self._speech_streak = 0

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
        while self.is_running:
            if self._pending_confirm:
                self._confirm_and_fire()
            time.sleep(0.1)

    def _confirm_and_fire(self):
        try:
            audio = self._ring.read()

            from assistant.stt import get_stt
            stt = get_stt()
            buf = io.BytesIO()
            sf.write(buf, audio, SAMPLE_RATE, format="WAV", subtype="PCM_16")
            text = stt.transcribe(buf.getvalue()).lower().strip()

            if text:
                print(f"[WakeWord] Heard: {text}")

            if text and self._is_wake_word(text):
                print(f"[WakeWord] Detected 'Hey Jarvis'!")
                self._cooldown_until = time.time() + self.COOLDOWN_ON_TRIGGER
                self._speech_streak = 0
                self._pending_confirm = False
                # Callback BEFORE clear so VoiceLoop can snapshot ring buffer
                if self.on_wake_word_callback:
                    self.on_wake_word_callback()
                self._ring.clear()
                return
            else:
                self._cooldown_until = time.time() + self.COOLDOWN_ON_SKIP
        except Exception as e:
            print(f"[WakeWord] Confirm error: {e}")
            self._cooldown_until = time.time() + self.COOLDOWN_ON_SKIP

        self._ring.clear()
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


def get_detector():
    return wake_word_detector


wake_word_detector = WakeWordDetector()
