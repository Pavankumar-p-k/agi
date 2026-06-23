"""tests/unit/test_voice_engine.py — Comprehensive tests for VoiceEngine production features."""
import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock, PropertyMock


@pytest.fixture
def engine():
    from core.config_registry import config as _cfg
    old_mode = _cfg.get("voice.mode", "push-to-talk")
    from assistant.voice_pipeline import VoiceEngine
    eng = VoiceEngine()
    eng._mode = "push-to-talk"
    yield eng
    eng.stop()


class TestVoiceMode:
    def test_default_mode_is_push_to_talk(self, engine):
        assert engine.mode == "push-to-talk"

    def test_set_mode_valid(self, engine):
        for mode in ["wake-word", "continuous", "push-to-talk"]:
            result = engine.set_mode(mode)
            assert engine.mode == mode
            assert "Switched" in result

    def test_set_mode_invalid(self, engine):
        result = engine.set_mode("invalid")
        assert engine.mode == "push-to-talk"
        assert "Invalid" in result

    def test_set_mode_from_string(self, engine):
        engine.set_mode_from_string("  WAKE-WORD  ")
        assert engine.mode == "wake-word"


class TestVoiceMetrics:
    def test_initial_metrics(self):
        from assistant.voice_pipeline import VoiceMetrics
        m = VoiceMetrics()
        assert m.total_commands == 0
        assert m.success_rate == 1.0

    def test_record_metrics_accumulates(self):
        from assistant.voice_pipeline import VoiceMetrics
        m = VoiceMetrics()
        m.record_metrics(100.0, 500.0, 300.0, 900.0)
        assert m.total_commands == 1
        assert m.successful_commands == 1
        assert m.avg_stt_latency == 100.0
        assert m.avg_think_latency == 500.0
        assert m.avg_tts_latency == 300.0
        assert m.avg_total_latency == 900.0

    def test_record_metrics_caps_at_1000(self):
        from assistant.voice_pipeline import VoiceMetrics
        m = VoiceMetrics()
        for i in range(1001):
            m.record_metrics(1.0, 2.0, 3.0, 6.0)
        assert len(m.stt_latency_ms) == 1000

    def test_snapshot_format(self):
        from assistant.voice_pipeline import VoiceMetrics
        m = VoiceMetrics()
        m.record_metrics(100.0, 500.0, 300.0, 900.0)
        s = m.snapshot()
        assert s["total_commands"] == 1
        assert "avg_stt_latency_ms" in s
        assert "avg_total_latency_ms" in s
        assert "success_rate" in s
        assert "stt_recoveries" in s
        assert "tts_recoveries" in s
        assert "stt_failures" in s
        assert "tts_failures" in s
        assert "vad_trigger_count" in s
        assert "wake_word_count" in s

    def test_empty_snapshot(self):
        from assistant.voice_pipeline import VoiceMetrics
        m = VoiceMetrics()
        s = m.snapshot()
        assert s["total_commands"] == 0
        assert s["avg_stt_latency_ms"] == 0.0


class TestAudioDeviceManager:
    def test_list_input_devices_calls_sd(self, engine):
        import sounddevice as sd
        original = sd.query_devices
        try:
            sd.query_devices = MagicMock(return_value=[
                {"name": "Mic", "max_input_channels": 1, "max_output_channels": 0, "default_samplerate": 16000},
                {"name": "Speaker", "max_input_channels": 0, "max_output_channels": 2, "default_samplerate": 48000},
            ])
            inputs = engine.devices.list_input_devices()
            assert len(inputs) == 1
            assert inputs[0]["name"] == "Mic"
        finally:
            sd.query_devices = original

    def test_list_output_devices_calls_sd(self, engine):
        import sounddevice as sd
        original = sd.query_devices
        try:
            sd.query_devices = MagicMock(return_value=[
                {"name": "Mic", "max_input_channels": 1, "max_output_channels": 0, "default_samplerate": 16000},
                {"name": "Speaker", "max_input_channels": 0, "max_output_channels": 2, "default_samplerate": 48000},
            ])
            outputs = engine.devices.list_output_devices()
            assert len(outputs) == 1
            assert outputs[0]["name"] == "Speaker"
        finally:
            sd.query_devices = original

    def test_set_input_device(self, engine):
        import sounddevice as sd
        old = sd.default.device
        try:
            sd.default.device = (0, 0)
            engine.devices.set_input_device(2)
        finally:
            sd.default.device = old

    def test_set_output_device(self, engine):
        import sounddevice as sd
        old = sd.default.device
        try:
            sd.default.device = (0, 0)
            engine.devices.set_output_device(3)
        finally:
            sd.default.device = old


class TestAutoRecovery:
    @pytest.mark.asyncio
    async def test_check_stt_health_when_none(self, engine):
        engine._stt = None
        result = await engine._check_stt_health()
        assert result is False

    @pytest.mark.asyncio
    async def test_check_stt_health_when_healthy(self, engine):
        mock = MagicMock()
        mock.health.return_value = True
        engine._stt = mock
        result = await engine._check_stt_health()
        assert result is True

    @pytest.mark.asyncio
    async def test_check_stt_health_async(self, engine):
        mock = MagicMock()
        mock.health = AsyncMock(return_value=True)
        engine._stt = mock
        result = await engine._check_stt_health()
        assert result is True

    @pytest.mark.asyncio
    async def test_check_tts_health_when_none(self, engine):
        engine._tts = None
        result = await engine._check_tts_health()
        assert result is False

    @pytest.mark.asyncio
    async def test_check_tts_health_when_ok(self, engine):
        mock = MagicMock()
        type(mock).pipeline = PropertyMock(return_value=MagicMock())
        engine._tts = mock
        result = await engine._check_tts_health()
        assert result is True

    @pytest.mark.asyncio
    async def test_recover_stt_failure(self, engine):
        engine.metrics.stt_failures = 0
        with patch.object(engine, "_stt", None):
            with patch.object(engine, "_check_stt_health", return_value=False):
                with patch.object(engine, "_recover_stt", return_value=False):
                    result = await engine._recover_stt()
                    assert result is False

    @pytest.mark.asyncio
    async def test_recover_tts_failure(self, engine):
        engine.metrics.tts_failures = 0
        with patch.object(engine, "_tts", None):
            with patch.object(engine, "_check_tts_health", return_value=False):
                with patch.object(engine, "_recover_tts", return_value=False):
                    result = await engine._recover_tts()
                    assert result is False

    @pytest.mark.asyncio
    async def test_recover_stt_success(self, engine):
        engine.metrics.stt_recoveries = 0
        with patch.object(engine, "_stt", MagicMock()):
            with patch.object(engine, "_check_stt_health", return_value=True):
                with patch.object(engine, "_recover_stt", return_value=True):
                    result = await engine._recover_stt()
                    assert result is True

    @pytest.mark.asyncio
    async def test_check_and_recover(self, engine):
        engine.metrics.stt_recoveries = 0
        with patch.object(engine, "_recover_stt", return_value=True):
            with patch.object(engine, "_recover_tts", return_value=False):
                with patch.object(engine, "_check_stt_health", return_value=False):
                    with patch.object(engine, "_check_tts_health", return_value=False):
                        result = await engine.check_and_recover()
                        assert result == {"stt": True, "tts": False}

    @pytest.mark.asyncio
    async def test_check_and_recover_all_good(self, engine):
        with patch.object(engine, "_check_stt_health", return_value=True):
            with patch.object(engine, "_check_tts_health", return_value=True):
                result = await engine.check_and_recover()
                assert result == {"stt": True, "tts": True}

    @pytest.mark.asyncio
    async def test_check_and_recover(self, engine):
        with patch.object(engine, "_check_stt_health", return_value=False):
            with patch.object(engine, "_check_tts_health", return_value=False):
                with patch.object(engine, "_recover_stt", return_value=True):
                    with patch.object(engine, "_recover_tts", return_value=False):
                        result = await engine.check_and_recover()
                        assert result == {"stt": True, "tts": False}


class TestLatencyTracker:
    def test_start_sets_timer(self):
        from assistant.voice_pipeline import LatencyTracker
        lt = LatencyTracker()
        lt.start()
        assert lt._start > 0

    def test_mark_records_lap(self):
        from assistant.voice_pipeline import LatencyTracker
        lt = LatencyTracker()
        lt.start()
        elapsed = lt.mark("test")
        assert elapsed >= 0
        assert "test" in lt._marks

    def test_phase_ms(self):
        from assistant.voice_pipeline import LatencyTracker
        lt = LatencyTracker()
        lt.start()
        lt.mark("stt_done")
        lt.mark("think_done")
        lt.mark("tts_done")
        assert lt.phase_ms("stt_done") >= 0
        assert lt.phase_ms("think_done") >= 0
        assert lt.phase_ms("tts_done") >= 0

    def test_phase_ms_unknown(self):
        from assistant.voice_pipeline import LatencyTracker
        lt = LatencyTracker()
        assert lt.phase_ms("nonexistent") == 0.0


class TestVoiceHealthMonitor:
    @pytest.mark.asyncio
    async def test_start_stop(self):
        from assistant.voice_pipeline import VoiceHealthMonitor, VoiceEngine
        eng = VoiceEngine()
        hm = VoiceHealthMonitor(eng)
        await hm.start()
        assert hm._task is not None
        await hm.stop()
        assert hm._task is None

    def test_initial_status(self):
        from assistant.voice_pipeline import VoiceHealthMonitor, VoiceEngine
        eng = VoiceEngine()
        hm = VoiceHealthMonitor(eng)
        status = hm.status
        assert "healthy" in status
        assert "last_checks" in status
        assert "interval" in status
        assert hm._healthy == {"stt": False, "tts": False}


class TestTranscribe:
    @pytest.mark.asyncio
    async def test_transcribe_sync(self, engine):
        mock_stt = MagicMock()
        mock_stt.transcribe = MagicMock(return_value="hello")
        engine._stt = mock_stt
        result = await engine.transcribe(b"audio")
        assert result == "hello"

    @pytest.mark.asyncio
    async def test_transcribe_async(self, engine):
        mock_stt = MagicMock()
        mock_stt.transcribe = AsyncMock(return_value="hello")
        engine._stt = mock_stt
        result = await engine.transcribe(b"audio")
        assert result == "hello"


class TestThink:
    @pytest.mark.asyncio
    async def test_think_cloud_success(self, engine):
        from core.result import Ok
        mock_llm = AsyncMock(return_value=Ok("response"))
        with patch("assistant.voice_pipeline.llm_complete", mock_llm):
            result = await engine.think("hello")
            assert result == "response"

    @pytest.mark.asyncio
    async def test_think_with_emotion_context(self, engine):
        from core.result import Ok
        mock_llm = AsyncMock(return_value=Ok("response"))
        with patch("assistant.voice_pipeline.llm_complete", mock_llm):
            result = await engine.think("hello", {"emotion_guidance": "be calm"})
            assert result == "response"

    @pytest.mark.asyncio
    async def test_think_fallback_on_failure(self, engine):
        from core.result import Ok
        mock_llm = AsyncMock(side_effect=[Exception("fail"), Ok("fallback")])
        with patch("assistant.voice_pipeline.llm_complete", mock_llm):
            result = await engine.think("hello")
            assert result == "fallback"


class TestSpeak:
    @pytest.mark.asyncio
    async def test_speak(self, engine):
        mock_tts = MagicMock()
        mock_tts.synthesize = MagicMock(return_value=b"wav")
        engine._tts = mock_tts
        result = await engine.speak("hello")
        assert result == b"wav"


class TestProcessAudio:
    @pytest.mark.asyncio
    async def test_process_audio_empty_transcription(self, engine):
        mock_stt = MagicMock()
        mock_stt.transcribe = MagicMock(return_value="")
        engine._stt = mock_stt
        mock_tts = MagicMock()
        mock_tts.synthesize = MagicMock(return_value=b"fallback")
        engine._tts = mock_tts
        result = await engine.process_audio(b"audio")
        assert result == b"fallback"
        assert engine.metrics.failed_commands == 1

    @pytest.mark.asyncio
    async def test_process_audio_happy_path(self, engine):
        mock_stt = MagicMock()
        mock_stt.transcribe = MagicMock(return_value="hello")
        engine._stt = mock_stt
        mock_tts = MagicMock()
        mock_tts.synthesize = MagicMock(return_value=b"response audio")
        engine._tts = mock_tts
        from core.result import Ok
        with patch("assistant.voice_pipeline.llm_complete", AsyncMock(return_value=Ok("hello to you"))):
            result = await engine.process_audio(b"audio")
            assert result == b"response audio"
            assert engine.metrics.total_commands == 1
            assert engine.metrics.successful_commands == 1


class TestEngineStatus:
    def test_status_contains_all_fields(self, engine):
        status = engine.status
        assert "mode" in status
        assert "running" in status
        assert "stt_loaded" in status
        assert "tts_loaded" in status
        assert "metrics" in status
        assert "health" in status
        assert "mic_device" in status
        assert "speaker_device" in status

    def test_health_report_returns_status(self, engine):
        assert engine.health_report() == engine.status

    def test_stop_sets_flags(self, engine):
        engine.start()
        engine.stop()
        assert engine._running is False
        assert engine._stop_event.is_set()

    def test_set_mode_persists(self, engine):
        engine.set_mode("continuous")
        from core.config_registry import config as _cfg
        assert _cfg.get("voice.mode") == "continuous"


class TestGetPipeline:
    def test_singleton(self):
        from assistant.voice_pipeline import get_pipeline
        p1 = get_pipeline()
        p2 = get_pipeline()
        assert p1 is p2

    def test_pipeline_is_voiceengine(self):
        from assistant.voice_pipeline import get_pipeline, VoiceEngine
        assert isinstance(get_pipeline(), VoiceEngine)
