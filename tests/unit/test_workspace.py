from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestWindowDetector:
    @pytest.fixture
    def detector(self):
        from core.workspace.window_detector import WindowDetector
        d = WindowDetector()
        d._pygetwindow = None  # force lazy import
        return d

    def test_lazy_import_success(self, detector):
        assert detector._pygetwindow is None
        detector._lazy_import()
        # pygetwindow should be available in test env
        assert detector._pygetwindow is not False

    def test_list_windows(self, detector):
        windows = detector.list_windows()
        assert isinstance(windows, list)

    def test_get_active_window(self, detector):
        w = detector.get_active_window()
        if w is not None:
            assert hasattr(w, "title")
            assert hasattr(w, "left")
            assert hasattr(w, "top")
            assert hasattr(w, "width")
            assert hasattr(w, "height")


class TestClipboardManager:
    @pytest.fixture
    def clip(self):
        from core.workspace.clipboard_manager import ClipboardManager
        c = ClipboardManager()
        c._pyperclip = None
        return c

    def test_lazy_import_success(self, clip):
        clip._lazy_import()
        assert clip._pyperclip is not False

    def test_is_available(self, clip):
        clip._lazy_import()
        assert clip.is_available() == (clip._pyperclip is not False)

    def test_set_get_roundtrip(self, clip):
        clip._lazy_import()
        if not clip.is_available():
            pytest.skip("pyperclip not available")
        original = clip.get_text()
        clip.set_text("test_clipboard_value")
        assert clip.get_text() == "test_clipboard_value"
        clip.set_text(original)


class TestProcessMonitor:
    @pytest.fixture
    def monitor(self):
        from core.workspace.process_monitor import ProcessMonitor
        m = ProcessMonitor()
        m._psutil = None
        return m

    def test_lazy_import(self, monitor):
        monitor._lazy_import()
        assert monitor._psutil is not False

    def test_list_processes(self, monitor):
        procs = monitor.list_processes()
        assert isinstance(procs, list)

    def test_find_by_name(self, monitor):
        results = monitor.find_by_name("python")
        assert isinstance(results, list)

    def test_is_process_running(self, monitor):
        result = monitor.is_process_running("python")
        assert isinstance(result, bool)

    def test_get_system_stats(self, monitor):
        stats = monitor.get_system_stats()
        assert isinstance(stats, dict)


class TestBrowserContextAwareness:
    @pytest.fixture
    def awareness(self):
        from core.workspace.browser_context import BrowserContextAwareness
        return BrowserContextAwareness()

    @pytest.mark.asyncio
    async def test_get_active_state(self, awareness):
        state = await awareness.get_active_state()
        assert state.has_browser is False or isinstance(state.url, str)
        assert isinstance(state.tab_count, int)

    @pytest.mark.asyncio
    async def test_is_browser_active(self, awareness):
        result = await awareness.is_browser_active()
        assert isinstance(result, bool)


class TestDesktopState:
    @pytest.fixture
    def desktop(self):
        from core.workspace.desktop_state import DesktopState
        return DesktopState()

    @pytest.mark.asyncio
    async def test_snapshot(self, desktop):
        snap = await desktop.snapshot()
        assert hasattr(snap, "active_window")
        assert hasattr(snap, "windows")
        assert hasattr(snap, "browser")
        assert hasattr(snap, "clipboard_text")
        assert hasattr(snap, "processes")
        assert hasattr(snap, "system_stats")
