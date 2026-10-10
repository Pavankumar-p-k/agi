# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""assistant.voice_pipeline — STT → LLM → TTS bridge and voice loop.

Pinned contracts (``tests/unit/test_voice_pipeline.py``):

- ``VoicePipeline`` lazily loads ``stt``/``tts`` providers via module-level
  ``get_stt``/``get_tts`` (patchable).
- ``transcribe(audio)`` -> text; ``speak(text)`` -> wav bytes;
  ``think(text)`` -> ``llm_complete(text)`` (Ok Response).
- ``process_audio``: empty transcription falls back to speaking silence
  fallback audio; otherwise transcribe → think → speak.
- ``get_pipeline()`` module singleton; ``VoiceLoop`` runs the wake→pipeline
  cycle on a daemon thread with ``_stop_event`` + ``_wake_event`` and an
  ``_engine`` engine carrying ``_wake_word``/``_wake_preroll``.
"""
from __future__ import annotations

import threading
from typing import Any, Optional

__all__ = ["VoicePipeline", "VoiceLoop", "get_pipeline", "get_stt", "get_tts", "llm_complete"]


def get_stt() -> Any:
    """Speech-to-text provider (lazy import; patchable seam)."""
    from assistant.stt import get_stt as _get

    return _get()


def get_tts() -> Any:
    """Text-to-speech provider (lazy import; patchable seam)."""
    from assistant.tts import get_tts as _get

    return _get()


def llm_complete(text: str, **kwargs: Any) -> Any:
    """LLM completion via the canonical llm_core surface."""
    from core.file_agent import llm_complete as _complete

    return _complete(text, **kwargs)


class VoicePipeline:
    """STT → LLM → TTS pipeline with lazy provider loading."""

    def __init__(self) -> None:
        self._stt: Optional[Any] = None
        self._tts: Optional[Any] = None

    # -- lazy providers -----------------------------------------------------
    @property
    def stt(self) -> Any:
        if self._stt is None:
            self._stt = get_stt()
        return self._stt

    @property
    def tts(self) -> Any:
        if self._tts is None:
            self._tts = get_tts()
        return self._tts

    # -- stages ---------------------------------------------------------------
    async def transcribe(self, audio: bytes) -> str:
        return str(self.stt.transcribe(audio) or "")

    async def think(self, text: str) -> Any:
        return await llm_complete(text)

    async def speak(self, text: str) -> bytes:
        return bytes(self.tts.synthesize(text) or b"")

    async def process_audio(self, audio: bytes) -> bytes:
        """Full turn: transcribe → think → speak (fallback on empty text)."""
        text = await self.transcribe(audio)
        if not text.strip():
            return await self.speak("")
        response = await self.think(text)
        payload = getattr(response, "value", response)
        return await self.speak(str(payload or ""))


_pipeline_instance: Optional[VoicePipeline] = None
_pipeline_lock = threading.Lock()


def get_pipeline() -> VoicePipeline:
    """Module-level pipeline singleton."""
    global _pipeline_instance
    with _pipeline_lock:
        if _pipeline_instance is None:
            _pipeline_instance = VoicePipeline()
        return _pipeline_instance


# ═════════════════════════════ voice loop ═══════════════════════════════════
class _Engine:
    """Shared engine state between the loop and the wake-word detector."""

    def __init__(self) -> None:
        self._wake_word: Optional[Any] = None
        self._wake_preroll: bytes = b""


class VoiceLoop:
    """Wake-word → pipeline loop on a daemon thread."""

    def __init__(self) -> None:
        self._engine = _Engine()
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._loop_thread: Optional[threading.Thread] = None

    # -- wake plumbing --------------------------------------------------------
    def _on_wake(self) -> None:
        """Wake-word fired: capture preroll audio and flag the loop."""
        det = self._engine._wake_word
        if det is not None:
            try:
                self._engine._wake_preroll = det.get_recent_audio()
            except Exception:  # noqa: BLE001 — preroll is best-effort
                self._engine._wake_preroll = b""
        self._wake_event.set()

    def _cycle(self) -> None:
        """One wake → process turn (runs on the loop thread)."""
        det = self._engine._wake_word
        wake = det or getattr(self, "_detector", None)
        if wake is not None:
            wake.start()
        try:
            while not self._stop_event.is_set():
                check = getattr(wake, "check_detection", None)
                if callable(check) and check():
                    self._on_wake()
                    audio = self._engine._wake_preroll
                    self._wake_event.clear()
                    if audio:
                        import asyncio

                        try:
                            asyncio.run(get_pipeline().process_audio(audio))
                        except Exception:  # noqa: BLE001 — loop must survive
                            pass
                else:
                    self._stop_event.wait(0.1)
        finally:
            stop = getattr(wake, "stop", None)
            if callable(stop):
                stop()

    # -- lifecycle --------------------------------------------------------------
    def start(self) -> None:
        if self._loop_thread is not None and self._loop_thread.is_alive():
            return
        self._stop_event.clear()
        from assistant.wake_word import WakeWordDetector

        self._engine._wake_word = WakeWordDetector(callback=self._on_wake)
        self._loop_thread = threading.Thread(target=self._cycle, daemon=True)
        self._loop_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._wake_event.set()
        thread = self._loop_thread
        if thread is not None:
            thread.join(timeout=5.0)
            self._loop_thread = None
