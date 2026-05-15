"""Record from mic -> send to /voice -> play back response.

Run this while the server is running (python -m core.main).

TEST MODES:
  1. python test_voice.py          — Record 5s, send to /voice, play response
  2. python test_voice.py --wake   — Record 2s, check if "hey jarvis" is heard

For full wake word test: start server, say "Hey Jarvis" near mic, then "what is two plus two".
"""
import asyncio
import sounddevice as sd
import soundfile as sf
import numpy as np
import io
import websockets
import sys

SAMPLE_RATE = 16000
RECORD_SECONDS = 5


async def _test_wake_word_transcribe():
    """Record 2s and transcribe — same as WakeWordDetector._confirm_and_fire."""
    duration = 2
    print("=" * 50)
    print("WAKE WORD TRANSCRIBE TEST")
    print(f"Recording for {duration}s starting NOW... say 'Hey Jarvis'")
    print("=" * 50)
    recording = sd.rec(int(SAMPLE_RATE * duration), samplerate=SAMPLE_RATE, channels=1, dtype="float32")
    sd.wait()
    print("Done recording.")

    peak = np.abs(recording).max()
    if peak < 0.01:
        print("Too quiet, try speaking louder.")
        return

    from assistant.stt import get_stt
    stt = get_stt()
    buf = io.BytesIO()
    sf.write(buf, recording, SAMPLE_RATE, format="WAV", subtype="PCM_16")
    text = stt.transcribe(buf.getvalue()).lower().strip()
    print(f"\nTranscribed: '{text}'")

    from assistant.wake_word import WakeWordDetector
    if WakeWordDetector._is_wake_word(text):
        print("\n*** WAKE WORD DETECTED ***")
    else:
        print("\nNo wake word detected.")
    print()


async def _test_voice_pipeline():
    """Record -> /voice WebSocket -> play response."""
    print("=" * 50)
    print("VOICE PIPELINE TEST (STT -> LLM -> TTS)")
    print(f"Recording for {RECORD_SECONDS}s starting NOW...")
    print("=" * 50)
    recording = sd.rec(
        int(SAMPLE_RATE * RECORD_SECONDS),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
    )
    sd.wait()
    print("Done recording.")

    peak = np.abs(recording).max()
    if peak < 0.01:
        print("Too quiet, try speaking louder.")
        return

    buf = io.BytesIO()
    sf.write(buf, recording, SAMPLE_RATE, format="WAV", subtype="PCM_16")
    audio_bytes = buf.getvalue()
    print(f"Sending {len(audio_bytes)} bytes to /voice...")

    async with websockets.connect("ws://localhost:8000/voice") as ws:
        await ws.send(audio_bytes)
        print("Waiting for response...")
        resp = await asyncio.wait_for(ws.recv(), timeout=120)
        print(f"Got {len(resp)} bytes, playing...")

        data, sr = sf.read(io.BytesIO(resp))
        sd.play(data, sr)
        sd.wait()
        print("Done!")


async def main():
    if "--wake" in sys.argv:
        await _test_wake_word_transcribe()
    else:
        await _test_voice_pipeline()

if __name__ == "__main__":
    asyncio.run(main())
