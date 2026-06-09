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

from __future__ import annotations

import logging
import os

from .stt_protocol import STTProvider, stt_registry
from .providers import FasterWhisperProvider, DeepgramProvider, AzureSpeechProvider

logger = logging.getLogger(__name__)


def init_stt_providers():
    """Register all STT providers at startup."""
    stt_registry.register(FasterWhisperProvider(), make_default=True)

    deepgram = DeepgramProvider()
    if await_deepgram_health(deepgram):
        stt_registry.register(deepgram)

    azure = AzureSpeechProvider()
    if azure._healthy:
        stt_registry.register(azure)


def await_deepgram_health(dg) -> bool:
    try:
        import asyncio
        loop = asyncio.get_running_loop()
        future = asyncio.run_coroutine_threadsafe(dg.health(), loop)
        return future.result(timeout=10)
    except RuntimeError:
        return asyncio.run(dg.health())
    except Exception as e:
        logger.warning("[STT] Deepgram health check failed: %s", e)
        return False


def get_stt(provider: str | None = None) -> STTProvider:
    """Get STT provider by name (or default). Backward-compatible with existing code."""
    if not stt_registry.list():
        init_stt_providers()
    return stt_registry.get(provider)


# Backward-compatible singleton for existing code that does `from assistant.stt import get_stt`
