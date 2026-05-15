# voice_loop.py
# THE REAL JARVIS VOICE LOOP
# Run: python voice_loop.py
# Speak -> JARVIS hears -> thinks -> speaks back
# Ctrl+C to stop

import sounddevice as sd
import numpy as np
import httpx
import json
import re
import io
import sys
import time
import tempfile
import os

# Fix Windows encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ─── CONFIG ───────────────────────────────────────────
MIC_DEVICE    = 1          # Realtek Array — change if wrong mic
SAMPLE_RATE   = 16000      # Whisper needs 16kHz
RECORD_SECS   = 5          # How long to listen each time
OLLAMA_URL    = "http://localhost:11434/api/chat"
OLLAMA_MODEL  = "qwen3:4b"
SPEAKERS      = None       # None = default speaker
# ──────────────────────────────────────────────────────

print("=" * 50)
print("JARVIS VOICE LOOP")
print("=" * 50)

# ─── LOAD STT ─────────────────────────────────────────
print("[1/3] Loading faster-whisper STT...")
try:
    from faster_whisper import WhisperModel
    stt = WhisperModel("base", device="cuda", compute_type="float16")
    print("[OK] STT loaded on GPU")
except Exception:
    try:
        stt = WhisperModel("base", device="cpu", compute_type="int8")
        print("[OK] STT loaded on CPU")
    except Exception as e:
        print("[FAIL] STT failed: " + str(e))
        sys.exit(1)

# ─── LOAD TTS ─────────────────────────────────────────
print("[2/3] Loading Kokoro TTS...")
try:
    from kokoro import KPipeline
    tts = KPipeline(lang_code="a")  # English
    print("[OK] TTS loaded")
except Exception as e:
    print("[FAIL] TTS failed: " + str(e))
    print("Continuing without TTS - will print response only")
    tts = None

# ─── CHECK OLLAMA ──────────────────────────────────────
print("[3/3] Checking Ollama...")
try:
    r = httpx.get("http://localhost:11434/api/tags", timeout=3)
    if r.status_code == 200:
        print("[OK] Ollama running")
    else:
        print("[FAIL] Ollama returned: " + str(r.status_code))
        sys.exit(1)
except Exception as e:
    print("[FAIL] Ollama not running. Start with: ollama serve")
    sys.exit(1)

print()
print("=" * 50)
print("JARVIS is ready. Speak after the beep.")
print("Press Ctrl+C to stop.")
print("=" * 50)

# ─── HELPER: SPEAK ────────────────────────────────────
def speak(text):
    if tts is None:
        print("JARVIS: " + text)
        return
    try:
        # Generate audio
        samples = []
        for _, _, audio in tts(text, voice="af_heart"):
            samples.append(audio)
        if samples:
            audio_data = np.concatenate(samples)
            # Play audio
            sd.play(audio_data, samplerate=24000, device=SPEAKERS)
            sd.wait()
        print("JARVIS: " + text)
    except Exception as e:
        print("JARVIS (TTS failed, text only): " + text)
        print("TTS error: " + str(e))

# ─── HELPER: LISTEN ───────────────────────────────────
def listen():
    print("\n[Listening for " + str(RECORD_SECS) + " seconds...]")
    try:
        audio = sd.rec(
            int(RECORD_SECS * SAMPLE_RATE),
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            device=MIC_DEVICE
        )
        sd.wait()
        return audio.flatten()
    except Exception as e:
        print("[ERROR] Recording failed: " + str(e))
        print("Try changing MIC_DEVICE number at top of file")
        return None

# ─── HELPER: TRANSCRIBE ───────────────────────────────
def transcribe(audio_array):
    try:
        # Save to temp WAV file (faster-whisper needs a file)
        import scipy.io.wavfile as wav
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        wav.write(tmp.name, SAMPLE_RATE, (audio_array * 32767).astype(np.int16))
        tmp.close()

        segments, _ = stt.transcribe(tmp.name, beam_size=5)
        text = " ".join([s.text for s in segments]).strip()
        os.unlink(tmp.name)
        return text
    except Exception as e:
        print("[ERROR] Transcription failed: " + str(e))
        return ""

# ─── HELPER: THINK ────────────────────────────────────
def think(text, history):
    try:
        history.append({"role": "user", "content": text})
        messages = [
            {"role": "system", "content": "You are JARVIS, a personal AI assistant. Be concise and direct. Max 2 sentences."}
        ] + history[-6:]  # keep last 3 turns

        r = httpx.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "messages": messages,
                "stream": False,
                "options": {"temperature": 0.7}
            },
            timeout=60
        )
        reply = r.json()["message"]["content"]
        # Strip thinking tags
        reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL).strip()
        history.append({"role": "assistant", "content": reply})
        return reply, history
    except Exception as e:
        return "Sorry, I had trouble thinking. Error: " + str(e), history

# ─── MAIN LOOP ────────────────────────────────────────
def main():
    history = []
    speak("JARVIS online. How can I help you?")

    while True:
        try:
            # Record
            audio = listen()
            if audio is None:
                continue

            # Check if audio has sound (silence detection)
            volume = np.abs(audio).mean()
            if volume < 0.001:
                print("[Silence detected - speak louder or check mic]")
                continue

            # Transcribe
            print("[Transcribing...]")
            text = transcribe(audio)

            if not text or len(text.strip()) < 2:
                print("[Could not hear clearly - try again]")
                continue

            print("You: " + text)

            # Stop command
            if any(w in text.lower() for w in ["stop", "exit", "quit", "shutdown"]):
                speak("Goodbye.")
                break

            # Think
            print("[Thinking...]")
            reply, history = think(text, history)

            # Speak
            speak(reply)

        except KeyboardInterrupt:
            print("\nStopping JARVIS...")
            speak("Shutting down.")
            break
        except Exception as e:
            print("[ERROR] " + str(e))
            continue

if __name__ == "__main__":
    # Install scipy if needed
    try:
        import scipy
    except ImportError:
        import subprocess
        print("Installing scipy...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "scipy"])

    main()
