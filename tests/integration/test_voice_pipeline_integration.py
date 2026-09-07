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

"""Integration tests for voice pipeline orchestration (mocked external deps)."""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from core.result import Ok


@pytest.mark.asyncio
async def test_process_audio_full_flow():
    """Full pipeline: audio -> transcribe -> think -> speak -> audio out."""
    from assistant.voice_pipeline import VoicePipeline
    p = VoicePipeline()

    mock_stt = MagicMock()
    mock_stt.transcribe = MagicMock(return_value="what is the weather")
    p._stt = mock_stt

    mock_tts = MagicMock()
    mock_tts.synthesize = MagicMock(return_value=b"wav response audio")
    p._tts = mock_tts

    with patch("core.audio_emotion.emotion_detector") as mock_emotion:
        mock_emotion.analyze = AsyncMock()
        ctx = MagicMock()
        ctx.as_context_dict.return_value = {}
        ctx.is_urgent = False
        mock_emotion.analyze.return_value = ctx

        with patch("assistant.voice_pipeline.llm_complete", AsyncMock(return_value=Ok("The weather is sunny"))):
            result = await p.process_audio(b"fake audio bytes")

    assert result == b"wav response audio"
    mock_stt.transcribe.assert_called_once_with(b"fake audio bytes")
    mock_tts.synthesize.assert_called_once()


@pytest.mark.asyncio
async def test_process_audio_empty_transcription_triggers_fallback():
    """Empty STT result triggers fallback speak."""
    from assistant.voice_pipeline import VoicePipeline
    p = VoicePipeline()

    mock_stt = MagicMock()
    mock_stt.transcribe = MagicMock(return_value="")
    p._stt = mock_stt

    mock_tts = MagicMock()
    mock_tts.synthesize = MagicMock(return_value=b"fallback wav")
    p._tts = mock_tts

    with patch("core.audio_emotion.emotion_detector") as mock_emotion:
        mock_emotion.analyze = AsyncMock()
        ctx = MagicMock()
        ctx.as_context_dict.return_value = {}
        ctx.is_urgent = False
        mock_emotion.analyze.return_value = ctx

        with patch("assistant.voice_pipeline.llm_complete", AsyncMock(return_value=Ok("should not be called"))):
            result = await p.process_audio(b"silence audio")

    assert result == b"fallback wav"
    mock_stt.transcribe.assert_called_once()


@pytest.mark.asyncio
async def test_process_audio_empty_llm_response_triggers_fallback():
    """Empty LLM response triggers fallback speak."""
    from assistant.voice_pipeline import VoicePipeline
    p = VoicePipeline()

    mock_stt = MagicMock()
    mock_stt.transcribe = MagicMock(return_value="hello")
    p._stt = mock_stt

    mock_tts = MagicMock()
    mock_tts.synthesize = MagicMock(return_value=b"error wav")
    p._tts = mock_tts

    with patch("core.audio_emotion.emotion_detector") as mock_emotion:
        mock_emotion.analyze = AsyncMock()
        ctx = MagicMock()
        ctx.as_context_dict.return_value = {}
        ctx.is_urgent = False
        mock_emotion.analyze.return_value = ctx

        with patch("assistant.voice_pipeline.llm_complete", AsyncMock(return_value=Ok(""))):
            result = await p.process_audio(b"test audio")

    assert result == b"error wav"


@pytest.mark.asyncio
async def test_think_falls_back_to_local():
    """When cloud LLM fails, think falls back to local model."""
    from assistant.voice_pipeline import VoicePipeline
    p = VoicePipeline()

    with patch("assistant.voice_pipeline.llm_complete") as mock_complete:
        mock_complete.side_effect = [
            Exception("cloud failed"),
            Ok("local response"),
        ]

        result = await p.think("hello")

    assert result == "local response"
    assert mock_complete.call_count == 2


@pytest.mark.asyncio
async def test_both_llms_fail_returns_empty():
    """When both cloud and local LLMs fail, think returns empty string."""
    from assistant.voice_pipeline import VoicePipeline
    p = VoicePipeline()

    with patch("assistant.voice_pipeline.llm_complete", side_effect=Exception("no LLM")):
        result = await p.think("hello")

    assert result == ""


@pytest.mark.asyncio
async def test_stt_async_compatible():
    """STT transcribe may return coroutine; pipeline handles both sync and async."""
    from assistant.voice_pipeline import VoicePipeline
    p = VoicePipeline()

    async def async_transcribe(_audio):
        return "async result"

    mock_stt = MagicMock()
    mock_stt.transcribe = AsyncMock(side_effect=async_transcribe)
    p._stt = mock_stt

    result = await p.transcribe(b"data")
    assert result == "async result"


@pytest.mark.asyncio
async def test_process_audio_passes_emotion_context():
    """Emotion context is extracted and passed to think."""
    from assistant.voice_pipeline import VoicePipeline
    p = VoicePipeline()

    mock_stt = MagicMock()
    mock_stt.transcribe = MagicMock(return_value="hello")
    p._stt = mock_stt

    mock_tts = MagicMock()
    mock_tts.synthesize = MagicMock(return_value=b"audio")
    p._tts = mock_tts

    with patch("core.audio_emotion.emotion_detector") as mock_emotion:
        mock_emotion.analyze = AsyncMock()
        ctx = MagicMock()
        ctx.as_context_dict.return_value = {"emotion_guidance": "Respond with urgency"}
        ctx.is_urgent = True
        ctx.confidence = 0.95
        mock_emotion.analyze.return_value = ctx

        with patch("assistant.voice_pipeline.llm_complete", AsyncMock(return_value=Ok("ok"))) as mock_llm:
            await p.process_audio(b"audio")

    mock_llm.assert_called_once()
    messages = mock_llm.call_args[1]["messages"]
    system_msg = messages[0]["content"]
    assert "Respond with urgency" in system_msg
    assert mock_emotion.analyze.called
