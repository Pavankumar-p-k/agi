# Voice Guide — JARVIS Voice System

## Architecture

```
Wake Word (OpenWakeWord)
    → VAD Detection (WebRTC)
    → Audio Buffer (RingBuffer)
    → Speech-to-Text (Faster-Whisper)
    → Emotion Analysis (librosa)
    → Intent Routing
    → LLM Execution
    → Text-to-Speech (Kokoro / EdgeTTS)
    → Audio Output
```

## Components

### Wake Word Detection
- **File:** `assistant/wake_word.py`
- **Method:** Two-stage VAD + Whisper confirmation
- **Config:** `voice.wake_word`, `voice.wake_word_enabled`, `voice.wake_cooldown_trigger`
- **Status:** ✅ Stable

### Speech-to-Text
- **File:** `assistant/stt.py`, `assistant/providers/faster_whisper.py`
- **Providers:** Faster-Whisper (local, default), Deepgram (cloud), Azure Speech (cloud)
- **Config:** `voice.stt_provider`, `voice.stt_model`
- **Status:** ✅ Stable

### Text-to-Speech
- **File:** `assistant/tts.py`, `assistant/providers/kokoro_tts.py`, `assistant/providers/edge_tts_provider.py`
- **Providers:** Kokoro-TTS (local), EdgeTTS (cloud)
- **Config:** `voice.tts_provider`, `voice.tts_voice`
- **Status:** 🟡 Beta (TTS provider abstraction added)

### Voice Pipeline
- **File:** `assistant/voice_pipeline.py`
- Orchestrates emotion → STT → LLM → TTS
- Supports cloud-first with local fallback
- **Status:** ✅ Stable

### Audio Emotion Detection
- **File:** `core/audio_emotion.py`
- Detection of CALM, URGENT, FRUSTRATED, EXCITED, NEUTRAL, SAD
- **Status:** ✅ Stable

## Modes

| Mode | Description | Config |
|------|-------------|--------|
| Wake Word | "Hey JARVIS" triggers listening | `voice.wake_word_enabled=true` |
| Continuous | Always listening | Via VoiceLoop |
| Push-to-Talk | Button/key triggers recording | Via WebSocket |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/stt` | POST | Upload file → transcription |
| `/stt/base64` | POST | Base64 audio → transcription |
| `/tts` | POST | Text → speech audio |
| `/tts/stream` | WebSocket | Stream text → audio |
| `/voice` | WebSocket | Full duplex voice |

## Configuration

All voice settings are in `core/config_registry.py` under the `voice.` namespace:
- `voice.tts_provider`, `voice.stt_provider`, `voice.stt_model`
- `voice.wake_word`, `voice.wake_word_enabled`
- `voice.mic_device`, `voice.sample_rate`
- `voice.vad_threshold`, `voice.vad_mode`
- 19 total settings
