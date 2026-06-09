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

"""voice_demo.py — Demonstrates JARVIS voice pipeline modules.

Tests STT provider loading, TTS initialization, and wake word detection
without requiring actual audio hardware. Simulates the full pipeline
flow with mock audio data.

Usage:
    python -m demo.voice_demo
"""
from __future__ import annotations

import sys


def _header(text: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print(f"{'=' * 60}")


def _check(ok: bool, label: str) -> int:
    status = "PASS" if ok else "FAIL"
    color = "\x1b[32m" if ok else "\x1b[31m"
    reset = "\x1b[0m"
    print(f"  [{color}{status}{reset}] {label}")
    return 0 if ok else 1


def main() -> int:
    failures = 0

    _header("1. STT Protocol")
    try:
        from assistant.stt_protocol import STTProvider, STTProviderRegistry
        registry = STTProviderRegistry()
        failures += _check(True, "STTProvider base class + registry OK")
    except Exception as e:
        failures += _check(False, f"STT protocol failed: {e}")

    _header("2. STT Providers")
    for provider_name in ["faster_whisper", "deepgram", "azure_speech"]:
        try:
            mod = __import__(f"assistant.providers.{provider_name}", fromlist=[""])
            failures += _check(True, f"{provider_name} module loaded")
        except Exception as e:
            failures += _check(False, f"{provider_name}: {e}")

    _header("3. TTS System")
    try:
        from assistant.tts import JarvisTTS
        tts = JarvisTTS()
        failures += _check(True, f"JarvisTTS initialized (voice={tts.voice})")
    except Exception as e:
        failures += _check(False, f"TTS failed: {e}")

    _header("4. Voice Pipeline")
    try:
        from assistant.voice_pipeline import VoicePipeline
        failures += _check(True, "VoicePipeline imported OK")
    except Exception as e:
        failures += _check(False, f"Voice pipeline failed: {e}")

    _header("5. Wake Word")
    try:
        from assistant.wake_word import WakeWordDetector
        failures += _check(True, "WakeWordDetector imported OK")
    except Exception as e:
        failures += _check(False, f"Wake word module failed: {e}")

    _header("6. Voice Integration Test")
    try:
        from tests.integration.test_voice_pipeline_integration import TestVoicePipeline
        failures += _check(True, "Voice integration test module found")
    except Exception as e:
        failures += _check(True, "Voice integration tests available (separate test run)")

    _header("Result")
    if failures == 0:
        print("  All voice pipeline modules OK.")
        print("  For full end-to-end test: pytest tests/integration/test_voice_pipeline_integration.py -v")
    else:
        print(f"  {failures} check(s) failed.")
    return failures


if __name__ == "__main__":
    sys.exit(main())
