"""assistant/wake_word.py — Two-stage wake word detection.
Stage 1: WebRTC VAD detects sustained voice in rolling 2s buffer.
Stage 2: Faster-Whisper confirms phrase contains "hey jarvis" or "jarvis".

No API keys, no accounts, fully offline.
"""
import io
import threading
import time
import webrtcvad
import numpy as np
import sounddevice as sd
import soundfile as sf


SAMPLE_RATE = 16000
CHUNK_SECONDS = 2
CHUNK_SIZE = int(SAMPLE_RATE * CHUNK_SECONDS)
VAD_MODE = 1


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
        """Return audio in chronological order (oldest first)."""
        if not self.filled:
            return self.buffer[:self.pos].copy()
        return np.concatenate([
            self.buffer[self.pos:],
            self.buffer[:self.pos]
        ])


class WakeWordDetector:
    """Two-stage wake word detector using VAD + Whisper."""

    def __init__(self, sensitivity: float = 0.5):
        self.vad = webrtcvad.Vad(VAD_MODE)
        self.is_running = False
        self._thread = None
        self.on_wake_word_callback = None
        self._cooldown_until = 0.0
        self._ring = RingBuffer(max_seconds=3.0)

    def start(self, callback):
        if self.is_running:
            return
        self.on_wake_word_callback = callback
        self.is_running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        print("[WakeWord] Listening for 'Hey Jarvis'...")
        frame_ms = 30
        frame_size = int(SAMPLE_RATE * frame_ms / 1000)
        speech_streak = 0

        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
            blocksize=frame_size,
        ) as stream:
            while self.is_running:
                chunk, _ = stream.read(frame_size)

                # Write to ring buffer (squeeze 2D -> 1D, convert to float32)
                self._ring.write(chunk.astype(np.float32).squeeze() / 32768.0)

                is_speech = self.vad.is_speech(chunk.tobytes(), SAMPLE_RATE)

                if is_speech:
                    speech_streak += 1
                else:
                    speech_streak = max(0, speech_streak - 1)

                # ~0.5s of sustained speech triggers confirmation
                if speech_streak > int(0.5 / frame_ms * 1000) and time.time() > self._cooldown_until:
                    speech_streak = 0
                    self._confirm_and_fire()

    def _confirm_and_fire(self):
        """Transcribe ring buffer and check for wake phrase."""
        try:
            audio = self._ring.read()

            from assistant.stt import get_stt
            stt = get_stt()
            buf = io.BytesIO()
            sf.write(buf, audio, SAMPLE_RATE, format="WAV", subtype="PCM_16")
            text = stt.transcribe(buf.getvalue()).lower().strip()

            if not text:
                return

            print(f"[WakeWord] Heard: {text}")

            if self._is_wake_word(text):
                print(f"[WakeWord] Detected 'Hey Jarvis'!")
                self._cooldown_until = time.time() + 2
                if self.on_wake_word_callback:
                    self.on_wake_word_callback()
            else:
                self._cooldown_until = time.time() + 1

        except Exception as e:
            print(f"[WakeWord] Confirm error: {e}")
            self._cooldown_until = time.time() + 1

    @staticmethod
    def _is_wake_word(text: str) -> bool:
        """Flexible wake word detection — handles common Whisper mis-transcriptions."""
        t = text.lower().strip()

        # Direct substring checks
        if "hey jarvis" in t:
            return True
        if t.startswith("jarvis"):
            return True

        # Normalize diacritics: "järvis" -> "jarvis"
        normalized = t.replace("ä", "a").replace("ë", "e").replace("ï", "i").replace("ü", "u")
        if "jarvis" in normalized:
            return True
        if normalized.startswith("jarvis"):
            return True
        if "hey jarvis" in normalized:
            return True

        # Common Whisper hallucination patterns for "hey jarvis"
        fuzzy_patterns = [
            "hey jar", "jar v", "jar wi", "jarvish",
            "re jarvis", "rey jarvis", "rey jar",
            "jarvis", "jarvis",
        ]
        for pat in fuzzy_patterns:
            if pat in normalized:
                return True

        # Character-level: at least "jar" present and some vowel proximity
        if "jar" in normalized and ("vi" in normalized or "wa" in normalized):
            return True

        return False

    def stop(self):
        self.is_running = False


wake_word_detector = WakeWordDetector()
