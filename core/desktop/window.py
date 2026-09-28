"""WindowController — window enumeration, focus, maximize, close.

Two call styles are supported:
- agent style: list_windows() -> list[dict] with a "title" key;
- gate style:  focus(title) -> WindowActionResult (used by tests).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class WindowActionResult:
    success: bool
    action: str = ""
    reason: str = ""
    error: str = ""
    output: Any = None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "action": self.action,
            "reason": self.reason,
            "error": self.error,
            "output": self.output,
        }


class WindowController:
    """Window management with a lazy pygetwindow backend."""

    def __init__(self) -> None:
        self._pygetwindow = None

    def _lazy_import(self):
        if self._pygetwindow is None:
            try:
                import pygetwindow as gw
                self._pygetwindow = gw
            except ImportError:
                self._pygetwindow = False
        return self._pygetwindow

    # ── agent style ──────────────────────────────────────────────────
    def list_windows(self, filter: str = "") -> list:
        """Return [{'title': ...}, ...] of open windows, optionally filtered."""
        gw = self._lazy_import()
        windows: list = []
        if gw:
            try:
                raw = list(gw.getAllWindows())
                windows = [{"title": w.title} for w in raw
                           if getattr(w, "title", "")]
            except Exception:  # noqa: BLE001
                windows = []
        if not windows:
            # Fallback: Win32 enumeration without third-party deps.
            try:
                windows = self._win32_windows()
            except Exception:  # noqa: BLE001
                windows = []
        if filter:
            f = str(filter).lower()
            windows = [w for w in windows if f in str(w.get("title", "")).lower()]
        return windows

    @staticmethod
    def _win32_windows() -> list:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        titles: list = []

        CBENUMPROC = ctypes.WINFUNCTYPE(
            ctypes.c_int, wintypes.HWND, wintypes.LPARAM)

        def _callback(hwnd, _lparam):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    if buf.value.strip():
                        titles.append({"title": buf.value})
            return 1

        user32.EnumWindows(CBENUMPROC(_callback), 0)
        return [{"title": t["title"]} for t in titles]

    def maximize(self, title: str) -> WindowActionResult:
        gw = self._lazy_import()
        if not gw:
            return WindowActionResult(success=False, action="maximize",
                                      reason="no window backend",
                                      error="no window backend installed")
        for w in gw.getAllWindows():
            if w.title == title:
                try:
                    w.maximize()
                    return WindowActionResult(success=True, action="maximize",
                                              output=title)
                except Exception as exc:  # noqa: BLE001
                    return WindowActionResult(success=False, action="maximize",
                                              error=str(exc))
        return WindowActionResult(success=False, action="maximize",
                                  reason=f"window not found: {title}",
                                  error=f"window not found: {title}")

    def focus(self, title: str) -> WindowActionResult:
        gw = self._lazy_import()
        if not gw:
            return WindowActionResult(success=False, action="focus",
                                      reason="no window backend",
                                      error="no window backend installed")
        for w in gw.getAllWindows():
            if w.title == title:
                try:
                    w.activate()
                    return WindowActionResult(success=True, action="focus",
                                              output=title)
                except Exception as exc:  # noqa: BLE001
                    return WindowActionResult(success=False, action="focus",
                                              error=str(exc))
        return WindowActionResult(success=False, action="focus",
                                  reason=f"window not found: {title}",
                                  error=f"window not found: {title}")

    def close(self, title: str) -> WindowActionResult:
        gw = self._lazy_import()
        if not gw:
            return WindowActionResult(success=False, action="close",
                                      reason="no window backend",
                                      error="no window backend installed")
        for w in gw.getAllWindows():
            if w.title == title:
                try:
                    w.close()
                    return WindowActionResult(success=True, action="close",
                                              output=title)
                except Exception as exc:  # noqa: BLE001
                    return WindowActionResult(success=False, action="close",
                                              error=str(exc))
        return WindowActionResult(success=False, action="close",
                                  reason=f"window not found: {title}",
                                  error=f"window not found: {title}")


# Module-level singleton.
window_controller = WindowController()


__all__ = ["WindowActionResult", "WindowController", "window_controller"]
