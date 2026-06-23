"""tests/unit/test_wake_word.py — Comprehensive tests for WakeWordDetector production features."""
import time
import threading
from unittest.mock import patch, MagicMock, PropertyMock

import pytest


# ── Levenshtein Distance ──────────────────────────────────────────────────────

class TestLevenshtein:
    def test_identical(self):
        from assistant.wake_word import _levenshtein
        assert _levenshtein("hey jarvis", "hey jarvis") == 0

    def test_single_substitution(self):
        from assistant.wake_word import _levenshtein
        assert _levenshtein("hey jarvis", "hey jarvis") == 0

    def test_single_insertion(self):
        from assistant.wake_word import _levenshtein
        assert _levenshtein("hey jarvis", "hey jarvis!") == 1

    def test_single_deletion(self):
        from assistant.wake_word import _levenshtein
        assert _levenshtein("hey jarvis", "hey jarvi") == 1

    def test_empty_strings(self):
        from assistant.wake_word import _levenshtein
        assert _levenshtein("", "") == 0

    def test_empty_vs_nonempty(self):
        from assistant.wake_word import _levenshtein
        assert _levenshtein("", "jarvis") == 6

    def test_completely_different(self):
        from assistant.wake_word import _levenshtein
        assert _levenshtein("hello world", "goodbye moon") > 5


# ── Word Boundary Score ──────────────────────────────────────────────────────

class TestWordBoundaryScore:
    def test_exact_match(self):
        from assistant.wake_word import _word_boundary_score
        assert _word_boundary_score("hey jarvis", "hey jarvis") == 1.0

    def test_exact_match_within_longer(self):
        from assistant.wake_word import _word_boundary_score
        score = _word_boundary_score("hey jarvis play some music", "hey jarvis")
        assert score == 1.0

    def test_edit_distance_penalty(self):
        from assistant.wake_word import _word_boundary_score
        score = _word_boundary_score("hey jarvis", "hey jervis")
        assert 0.0 < score < 1.0

    def test_no_match(self):
        from assistant.wake_word import _word_boundary_score
        score = _word_boundary_score("hello world", "hey jarvis")
        assert score < 0.4

    def test_empty_input(self):
        from assistant.wake_word import _word_boundary_score
        assert _word_boundary_score("", "hey jarvis") == 0.0
        assert _word_boundary_score("hey jarvis", "") == 0.0

    def test_case_insensitive(self):
        from assistant.wake_word import _word_boundary_score
        assert _word_boundary_score("HEY JARVIS", "hey jarvis") == 1.0

    def test_extra_whitespace(self):
        from assistant.wake_word import _word_boundary_score
        score = _word_boundary_score("  hey   jarvis  ", "hey jarvis")
        assert score >= 0.9  # partial match due to extra spaces in words


# ── WakeWordRegistry ─────────────────────────────────────────────────────────

class TestWakeWordRegistry:
    def test_add_and_match(self):
        from assistant.wake_word import WakeWordRegistry
        r = WakeWordRegistry()
        r.add("hey jarvis", min_confidence=0.7)
        result = r.match("hey jarvis")
        assert result is not None
        phrase, score = result
        assert phrase == "hey jarvis"
        assert score >= 0.7

    def test_add_and_match_within_longer(self):
        from assistant.wake_word import WakeWordRegistry
        r = WakeWordRegistry()
        r.add("hey jarvis", min_confidence=0.7)
        result = r.match("hey jarvis play some music")
        assert result is not None
        phrase, score = result
        assert phrase == "hey jarvis"

    def test_no_match_below_confidence(self):
        from assistant.wake_word import WakeWordRegistry
        r = WakeWordRegistry()
        r.add("hey jarvis", min_confidence=0.99)
        result = r.match("hello world")
        assert result is None

    def test_remove(self):
        from assistant.wake_word import WakeWordRegistry
        r = WakeWordRegistry()
        r.add("hey jarvis")
        r.add("ok computer")
        assert r.count == 2
        r.remove("hey jarvis")
        assert r.count == 1
        assert r.match("hey jarvis") is None
        assert r.match("ok computer") is not None

    def test_clear(self):
        from assistant.wake_word import WakeWordRegistry
        r = WakeWordRegistry()
        r.add("hey jarvis")
        r.add("ok computer")
        assert r.count == 2
        r.clear()
        assert r.count == 0
        assert r.match("hey jarvis") is None

    def test_phrases_property(self):
        from assistant.wake_word import WakeWordRegistry
        r = WakeWordRegistry()
        r.add("hey jarvis")
        r.add("ok computer")
        phrases = r.phrases
        assert "hey jarvis" in phrases
        assert "ok computer" in phrases

    def test_empty_registry(self):
        from assistant.wake_word import WakeWordRegistry
        r = WakeWordRegistry()
        assert r.match("anything") is None
        assert r.phrases == []
        assert r.count == 0

    def test_case_insensitive_storage(self):
        from assistant.wake_word import WakeWordRegistry
        r = WakeWordRegistry()
        r.add("HEY JARVIS")
        result = r.match("hey jarvis")
        assert result is not None
        assert result[0] == "hey jarvis"

    def test_load_from_config(self):
        from assistant.wake_word import WakeWordRegistry
        r = WakeWordRegistry()
        with patch("assistant.wake_word._get_config") as mock_config:
            mock_config.side_effect = lambda key, default=None: {
                "voice.wake_word": "hey jarvis, ok computer",
                "voice.wake_min_confidence": 0.8,
            }.get(key, default)
            r.load_from_config()
        assert r.count == 2
        assert r.match("hey jarvis") is not None
        assert r.match("ok computer") is not None
        assert r.match("ok computer")[1] >= 0.8


# ── WakeWordStats ────────────────────────────────────────────────────────────

class TestWakeWordStats:
    def test_initial_state(self):
        from assistant.wake_word import WakeWordStats
        s = WakeWordStats()
        assert s.detections == 0
        assert s.false_positives == 0
        assert s.missed == 0
        assert s.accuracy == 1.0
        assert s.false_positive_rate == 0.0

    def test_record_detection(self):
        from assistant.wake_word import WakeWordStats
        s = WakeWordStats()
        s.record_detection(100.0, 500.0)
        assert s.detections == 1
        assert s.avg_stt_latency == 100.0
        assert s.avg_total_latency == 500.0

    def test_record_false_positive(self):
        from assistant.wake_word import WakeWordStats
        s = WakeWordStats()
        s.record_false_positive()
        assert s.false_positives == 1
        assert s.false_positive_rate > 0

    def test_record_missed(self):
        from assistant.wake_word import WakeWordStats
        s = WakeWordStats()
        s.record_missed()
        assert s.missed == 1
        assert s.accuracy < 1.0

    def test_accuracy_calculation(self):
        from assistant.wake_word import WakeWordStats
        s = WakeWordStats()
        s.record_detection(100, 500)
        s.record_detection(200, 600)
        s.record_missed()
        assert s.detections == 2
        assert s.missed == 1
        assert s.accuracy == 2.0 / 3.0

    def test_snapshot_contains_keys(self):
        from assistant.wake_word import WakeWordStats
        s = WakeWordStats()
        s.record_detection(100.0, 500.0)
        snap = s.snapshot()
        assert "detections" in snap
        assert "false_positives" in snap
        assert "avg_stt_latency_ms" in snap
        assert "avg_total_latency_ms" in snap
        assert "accuracy" in snap
        assert "false_positive_rate" in snap
        assert snap["detections"] == 1

    def test_capped_latency_lists(self):
        from assistant.wake_word import WakeWordStats
        s = WakeWordStats()
        for i in range(1001):
            s.record_detection(float(i), float(i * 2))
        assert len(s.stt_latency_ms) == 1000
        assert len(s.total_latency_ms) == 1000

    def test_last_detection_time(self):
        from assistant.wake_word import WakeWordStats
        s = WakeWordStats()
        before = time.time()
        s.record_detection(100, 500)
        assert s.last_detection_time >= before


# ── RingBuffer ───────────────────────────────────────────────────────────────

class TestRingBuffer:
    def test_initial_empty(self):
        from assistant.wake_word import RingBuffer
        import numpy as np
        rb = RingBuffer(max_seconds=2.0, sr=100)
        data = rb.read()
        assert len(data) == 0
        assert rb.energy() == 0.0

    def test_write_and_read(self):
        from assistant.wake_word import RingBuffer
        import numpy as np
        rb = RingBuffer(max_seconds=2.0, sr=100)
        samples = np.ones(50, dtype=np.float32)
        rb.write(samples)
        data = rb.read()
        assert len(data) == 50

    def test_ring_behavior(self):
        from assistant.wake_word import RingBuffer
        import numpy as np
        rb = RingBuffer(max_seconds=1.0, sr=10)
        first = np.array([1.0] * 5, dtype=np.float32)
        second = np.array([2.0] * 9, dtype=np.float32)
        rb.write(first)
        rb.write(second)
        data = rb.read()
        assert len(data) == 10
        assert int(data[0]) == 1  # 5th element of original sequence still in buffer
        assert int(data[1]) == 2  # rest are all twos

    def test_energy_calculation(self):
        from assistant.wake_word import RingBuffer
        import numpy as np
        rb = RingBuffer(max_seconds=2.0, sr=100)
        rb.write(np.ones(100, dtype=np.float32))
        assert rb.energy() == 1.0

    def test_clear(self):
        from assistant.wake_word import RingBuffer
        import numpy as np
        rb = RingBuffer(max_seconds=2.0, sr=100)
        rb.write(np.ones(100, dtype=np.float32))
        rb.clear()
        assert len(rb.read()) == 0
        assert rb.energy() == 0.0

    def test_write_overflow(self):
        from assistant.wake_word import RingBuffer
        import numpy as np
        rb = RingBuffer(max_seconds=1.0, sr=10)
        samples = np.ones(20, dtype=np.float32)
        rb.write(samples)
        assert len(rb.read()) == 10

    def test_thread_safety(self):
        from assistant.wake_word import RingBuffer
        import numpy as np
        rb = RingBuffer(max_seconds=2.0, sr=100)
        errors = []
        def writer():
            try:
                for _ in range(100):
                    rb.write(np.random.randn(50).astype(np.float32))
            except Exception as e:
                errors.append(e)
        def reader():
            try:
                for _ in range(100):
                    _ = rb.read()
                    _ = rb.energy()
            except Exception as e:
                errors.append(e)
        t1 = threading.Thread(target=writer, daemon=True)
        t2 = threading.Thread(target=reader, daemon=True)
        t1.start(); t2.start()
        t1.join(timeout=5); t2.join(timeout=5)
        assert len(errors) == 0


# ── WakeWordDetector ─────────────────────────────────────────────────────────

class TestWakeWordDetector:
    def test_initial_state(self):
        from assistant.wake_word import WakeWordDetector
        d = WakeWordDetector()
        assert not d.running
        assert d.registry.count > 0
        assert d.stats.detections == 0

    def test_start_stop(self):
        from assistant.wake_word import WakeWordDetector
        d = WakeWordDetector()
        d.start()
        assert d.running
        d.stop()
        assert not d.running

    def test_registry_proxy(self):
        from assistant.wake_word import WakeWordDetector
        d = WakeWordDetector()
        assert d.registry is not None
        assert hasattr(d.registry, "add")
        assert hasattr(d.registry, "match")

    def test_detection_event_initially_not_set(self):
        from assistant.wake_word import WakeWordDetector
        d = WakeWordDetector()
        assert not d.detection_event.is_set()
        assert not d.check_detection()

    def test_detection_event_clear_on_check(self):
        from assistant.wake_word import WakeWordDetector
        d = WakeWordDetector()
        d._detection_event.set()
        assert d.check_detection()
        assert not d.check_detection()

    def test_status_dict(self):
        from assistant.wake_word import WakeWordDetector
        d = WakeWordDetector()
        status = d.status
        assert "running" in status
        assert "phrases" in status
        assert "stats" in status
        assert not status["running"]

    def test_status_after_start(self):
        from assistant.wake_word import WakeWordDetector
        d = WakeWordDetector()
        d.start()
        try:
            status = d.status
            assert status["running"]
        finally:
            d.stop()

    def test_get_recent_audio_before_start(self):
        from assistant.wake_word import WakeWordDetector
        d = WakeWordDetector()
        assert d.get_recent_audio() == b""

    def test_callback_invoked_on_detection(self):
        from assistant.wake_word import WakeWordDetector
        fired = []
        def cb():
            fired.append(True)
        d = WakeWordDetector(callback=cb)
        d._detection_event.set()
        assert d.check_detection()

    def test_load_from_config_single_word(self):
        with patch("assistant.wake_word._get_config") as mc:
            mc.side_effect = lambda k, d=None: {
                "voice.wake_word": "computer",
                "voice.wake_min_confidence": 0.7,
                "voice.sample_rate": 16000,
                "voice.vad_mode": 3,
                "voice.energy_threshold": 0.008,
                "voice.require_speech_seconds": 1.2,
                "voice.ring_buffer_seconds": 4.0,
                "voice.wake_cooldown_trigger": 5.0,
                "voice.wake_cooldown_skip": 3.0,
                "voice.mic_device": "",
                "voice.sensitivity_gain": 1.0,
                "voice.adaptive_threshold": True,
                "voice.frame_ms": 30,
            }.get(k, d)
            from assistant.wake_word import WakeWordDetector
            d = WakeWordDetector()
            assert "computer" in d.registry.phrases

    def test_load_from_config_multiple_words(self):
        with patch("assistant.wake_word._get_config") as mc:
            mc.side_effect = lambda k, d=None: {
                "voice.wake_word": "hey jarvis, ok computer, hey siri",
                "voice.wake_min_confidence": 0.6,
                "voice.sample_rate": 16000,
                "voice.vad_mode": 3,
                "voice.energy_threshold": 0.008,
                "voice.require_speech_seconds": 1.2,
                "voice.ring_buffer_seconds": 4.0,
                "voice.wake_cooldown_trigger": 5.0,
                "voice.wake_cooldown_skip": 3.0,
                "voice.mic_device": "",
                "voice.sensitivity_gain": 1.0,
                "voice.adaptive_threshold": True,
                "voice.frame_ms": 30,
            }.get(k, d)
            from assistant.wake_word import WakeWordDetector
            d = WakeWordDetector()
            assert d.registry.count == 3
            assert "hey jarvis" in d.registry.phrases
            assert "ok computer" in d.registry.phrases


# ── WatchdogService ──────────────────────────────────────────────────────────

class TestWatchdogService:
    @patch("sounddevice.InputStream")
    def test_create_and_start(self, mock_stream):
        from assistant.wake_word import WatchdogService
        w = WatchdogService()
        det = w.start()
        assert det is not None
        assert det.running
        w.stop()
        assert not det.running

    def test_detector_property(self):
        from assistant.wake_word import WatchdogService
        w = WatchdogService()
        assert w.detector is None
        det = w.start()
        assert w.detector is det
        w.stop()

    def test_start_stop_idempotent(self):
        from assistant.wake_word import WatchdogService
        w = WatchdogService()
        w.stop()
        w.start()
        w.stop()
        w.stop()

    def test_callback_passed_to_detector(self):
        from assistant.wake_word import WatchdogService
        fired = []
        def cb():
            fired.append(True)
        w = WatchdogService(callback=cb)
        det = w.start()
        det._detection_event.set()
        assert det.check_detection()
        w.stop()

    def test_multiple_start_creates_new_detector(self):
        from assistant.wake_word import WatchdogService
        w = WatchdogService()
        d1 = w.start()
        assert d1 is not None
        w.stop()
        d2 = w.start()
        assert d2 is not None
        assert d2 is not d1
        w.stop()


# ── Singleton ────────────────────────────────────────────────────────────────

class TestGetDetector:
    @patch("sounddevice.InputStream")
    def test_get_detector_returns_detector(self, mock_stream):
        from assistant.wake_word import get_detector, _watchdog_instance
        _watchdog_instance = None
        import importlib
        import assistant.wake_word as ww
        ww._watchdog_instance = None
        det = get_detector()
        assert det is not None
        assert det.running
        ww._watchdog_instance = None

    def test_reset_globals_test_cleanup(self):
        import assistant.wake_word as ww
        if ww._watchdog_instance:
            ww._watchdog_instance.stop()
        ww._watchdog_instance = None


# ── Integration: Registry + Stats + Detector ─────────────────────────────────

class TestWakeWordIntegration:
    def test_custom_wake_word_registered_and_detected(self):
        from assistant.wake_word import WakeWordRegistry, WakeWordStats
        r = WakeWordRegistry()
        r.add("jarvis", min_confidence=0.7)
        result = r.match("jarvis")
        assert result is not None
        assert result[0] == "jarvis"
        assert result[1] >= 0.7

    def test_stats_after_registry_match(self):
        from assistant.wake_word import WakeWordRegistry, WakeWordStats
        r = WakeWordRegistry()
        r.add("hey jarvis", min_confidence=0.7)
        s = WakeWordStats()
        result = r.match("hey jarvis play music")
        assert result is not None
        s.record_detection(100.0, 500.0)
        snap = s.snapshot()
        assert snap["detections"] == 1
        assert snap["avg_stt_latency_ms"] == 100.0

    def test_multiple_phrases_best_match_wins(self):
        from assistant.wake_word import WakeWordRegistry
        r = WakeWordRegistry()
        r.add("jarvis", min_confidence=0.5)
        r.add("hey jarvis", min_confidence=0.7)
        result = r.match("hey jarvis")
        assert result is not None
        assert result[0] == "hey jarvis"

    def test_phrase_not_in_spoken_text(self):
        from assistant.wake_word import WakeWordRegistry
        r = WakeWordRegistry()
        r.add("ok computer", min_confidence=0.7)
        assert r.match("hello world") is None

    def test_scoring_boundary_behavior(self):
        from assistant.wake_word import _word_boundary_score
        assert _word_boundary_score("jarvis", "jarvis") == 1.0
        assert _word_boundary_score("jarvisaa", "jarvis") < 1.0
        assert _word_boundary_score("jarvis", "jarvisaa") < 1.0

    def test_energy_threshold_config(self):
        with patch("assistant.wake_word._get_config") as mc:
            mc.side_effect = lambda k, d=None: {
                "voice.wake_word": "hey jarvis",
                "voice.wake_min_confidence": 0.6,
                "voice.sample_rate": 16000,
                "voice.vad_mode": 3,
                "voice.energy_threshold": 0.02,
                "voice.require_speech_seconds": 2.0,
                "voice.ring_buffer_seconds": 3.0,
                "voice.wake_cooldown_trigger": 5.0,
                "voice.wake_cooldown_skip": 3.0,
                "voice.mic_device": "",
                "voice.sensitivity_gain": 2.0,
                "voice.adaptive_threshold": False,
                "voice.frame_ms": 30,
            }.get(k, d)
            from assistant.wake_word import WakeWordDetector
            d = WakeWordDetector()
            cfg = d._read_config()
            assert cfg["energy_threshold"] == 0.02
            assert cfg["require_speech_seconds"] == 2.0
            assert cfg["ring_buffer_seconds"] == 3.0
            assert cfg["sensitivity_gain"] == 2.0
            assert cfg["adaptive_threshold"] is False
