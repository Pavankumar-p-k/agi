import os
import threading
import pvporcupine
from pvrecorder import PvRecorder

class WakeWordDetector:
    """
    Wake word detection using Porcupine.
    """
    def __init__(self, access_key: str = None, sensitivity: float = 0.5):
        self.access_key = access_key or os.getenv("PVPORCUPINE_ACCESS_KEY")
        self.sensitivity = sensitivity
        self.porcupine = None
        self.recorder = None
        self.is_running = False
        self._thread = None
        self.on_wake_word_callback = None

    def start(self, callback):
        """
        Start listening for the wake word in a background thread.
        """
        if self.is_running:
            return

        if not self.access_key:
            print("[WakeWord] No AccessKey provided. Wake word detection disabled.")
            return

        self.on_wake_word_callback = callback
        self.is_running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        try:
            self.porcupine = pvporcupine.create(
                access_key=self.access_key,
                keywords=['hey jarvis']
            )
            self.recorder = PvRecorder(device_index=-1, frame_length=self.porcupine.frame_length)
            self.recorder.start()

            print("[WakeWord] Listening for 'Hey Jarvis'...")

            while self.is_running:
                pcm = self.recorder.read()
                result = self.porcupine.process(pcm)
                if result >= 0:
                    print("[WakeWord] Detected 'Hey Jarvis'!")
                    if self.on_wake_word_callback:
                        self.on_wake_word_callback()

        except Exception as e:
            print(f"[WakeWord] Error: {e}")
        finally:
            self.stop()

    def stop(self):
        self.is_running = False
        if self.recorder:
            self.recorder.stop()
            self.recorder.delete()
            self.recorder = None
        if self.porcupine:
            self.porcupine.delete()
            self.porcupine = None

# Instance
wake_word_detector = WakeWordDetector()
