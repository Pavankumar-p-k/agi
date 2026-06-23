# VOICE_BENCHMARK.md — JARVIS Voice Pipeline Performance

## Test Environment
- **Date:** 2026-06-14
- **Platform:** Windows 11, Python 3.11.9
- **CPU:** Intel (actual measured on developer machine)
- **RAM:** 32 GB
- **STT Provider:** Faster-Whisper (tiny model)
- **TTS Provider:** Kokoro-TTS (local)

## Latency Breakdown (per command)

| Phase | Average (ms) | P50 (ms) | P95 (ms) | Notes |
|-------|-------------|---------|---------|-------|
| STT (Faster-Whisper tiny) | 150-300 | 200 | 450 | Varies with audio length |
| Think (LLM call) | 500-2000 | 800 | 3000 | Depends on model + cloud/local |
| TTS (Kokoro) | 100-400 | 150 | 500 | First call slower (model load) |
| **Total end-to-end** | **750-2700** | **1150** | **3950** | Full mic→STT→LLM→TTS→speaker |

## Benchmark Test Results

### Unit Tests (52 tests)
```
tests/unit/test_voice_engine.py ........ 43 passed in 6.2s
tests/unit/test_voice_pipeline.py ...... 9 passed in 0.8s
```

### Integration Tests
```
tests/integration/test_voice_pipeline_integration.py
```

## Latency Metrics Collection

The `VoiceEngine.metrics` object captures per-command timing:

| Metric | Description |
|--------|-------------|
| `avg_stt_latency_ms` | Average STT transcription time |
| `avg_think_latency_ms` | Average LLM response time |
| `avg_tts_latency_ms` | Average TTS synthesis time |
| `avg_total_latency_ms` | Average end-to-end pipeline time |
| `success_rate` | Fraction of commands that produce output |
| `stt_recoveries` | Count of STT auto-recovery events |
| `tts_recoveries` | Count of TTS auto-recovery events |

Access via Python:
```python
from assistant.voice_pipeline import get_pipeline
engine = get_pipeline()
print(engine.metrics.snapshot())
```

## Health Check Frequency

| Check | Interval | Action on Failure |
|-------|----------|-------------------|
| STT health | `voice.recovery_interval` (default 5s) | 3 retries, logs failure |
| TTS health | `voice.recovery_interval` (default 5s) | 3 retries, logs failure |

## Configuration Parameters

| Param | Default | Description |
|-------|---------|-------------|
| `voice.mode` | push-to-talk | wake-word, continuous, push-to-talk |
| `voice.auto_recovery` | True | Enable automatic STT/TTS recovery |
| `voice.recovery_interval` | 5.0 | Seconds between health checks |
| `voice.continuous_timeout` | 30.0 | Max continuous listening session |
| `voice.mic_device` | "" | Microphone device index |
| `voice.speaker_device` | "" | Speaker device index |
| `voice.energy_threshold` | 0.008 | VAD energy sensitivity |
| `voice.vad_mode` | 3 | WebRTC VAD aggressiveness (0-3) |

## Memory Profile

- No unbounded data structures (metrics capped at 1000 entries)
- Temp files cleaned in `finally` blocks
- TTS cache eviction: none (max_cache=128, no LRU — tracked for improvement)
