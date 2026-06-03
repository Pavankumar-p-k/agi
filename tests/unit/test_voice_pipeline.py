"""tests/test_voice_pipeline.py — Tests for assistant/voice_pipeline.py."""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestVoicePipelineProperties:
    @pytest.fixture
    def pipeline(self):
        from assistant.voice_pipeline import VoicePipeline
        return VoicePipeline()

    def test_stt_lazy_loads(self, pipeline):
        assert pipeline._stt is None
        with patch("assistant.voice_pipeline.get_stt", return_value=MagicMock()):
            stt = pipeline.stt
            assert stt is not None
            assert pipeline._stt is not None

    def test_tts_lazy_loads(self, pipeline):
        assert pipeline._tts is None
        with patch("assistant.voice_pipeline.get_tts", return_value=MagicMock()):
            tts = pipeline.tts
            assert tts is not None
            assert pipeline._tts is not None


@pytest.mark.asyncio
async def test_transcribe():
    from assistant.voice_pipeline import VoicePipeline
    p = VoicePipeline()
    mock_stt = MagicMock()
    mock_stt.transcribe = MagicMock(return_value="hello world")
    p._stt = mock_stt
    result = await p.transcribe(b"audio data")
    assert result == "hello world"


@pytest.mark.asyncio
async def test_think():
    from assistant.voice_pipeline import VoicePipeline
    p = VoicePipeline()
    from core.result import Ok
    mock_llm = AsyncMock(return_value=Ok("response text"))
    with patch("assistant.voice_pipeline.llm_complete", mock_llm):
        result = await p.think("hello")
        assert result is not None


@pytest.mark.asyncio
async def test_speak():
    from assistant.voice_pipeline import VoicePipeline
    p = VoicePipeline()
    mock_tts = MagicMock()
    mock_tts.synthesize = MagicMock(return_value=b"wav audio")
    p._tts = mock_tts
    result = await p.speak("hello")
    assert result == b"wav audio"


@pytest.mark.asyncio
async def test_process_audio_empty_transcription():
    from assistant.voice_pipeline import VoicePipeline
    p = VoicePipeline()
    mock_stt = MagicMock()
    mock_stt.transcribe = MagicMock(return_value="")
    p._stt = mock_stt
    mock_tts = MagicMock()
    mock_tts.synthesize = MagicMock(return_value=b"fallback audio")
    p._tts = mock_tts
    result = await p.process_audio(b"audio")
    assert result == b"fallback audio"


class TestVoiceLoop:
    def test_get_pipeline_singleton(self):
        from assistant.voice_pipeline import get_pipeline
        p1 = get_pipeline()
        p2 = get_pipeline()
        assert p1 is p2

    def test_start_stop(self):
        from assistant.voice_pipeline import VoiceLoop
        loop = VoiceLoop()
        with patch("assistant.wake_word.WakeWordDetector") as mock_ww:
            mock_ww_instance = MagicMock()
            mock_ww.return_value = mock_ww_instance
            loop.start()
            assert loop._loop_thread is not None
            assert loop._loop_thread.is_alive()
            loop.stop()
            assert loop._stop_event.is_set()

    def test_on_wake(self):
        from assistant.voice_pipeline import VoiceLoop
        loop = VoiceLoop()
        mock_ww = MagicMock()
        mock_ww.get_recent_audio.return_value = b"preroll"
        loop._wake_word = mock_ww
        loop._on_wake()
        assert loop._wake_preroll == b"preroll"
        assert loop._wake_event.is_set()
