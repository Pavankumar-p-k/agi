"""WindowDetector — passive window awareness for the workspace layer.

Distinct from core.desktop.window (Gate 8: awareness != control): this
module only observes, it never focuses or closes anything.
"""
from __future__ import annotations

from typing import Optional


class WindowDetector:
    """Enumerates windows and reports the active window (read-only)."""

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

    def list_windows(self) -> list:
        gw = self._lazy_import()
        if not gw:
            return []
        try:
            return list(gw.getAllWindows())
        except Exception:  # noqa: BLE001
            return []

    def get_active_window(self) -> Optional[object]:
        gw = self._lazy_import()
        if not gw:
            return None
        try:
            return gw.getActiveWindow()
        except Exception:  # noqa: BLE001
            return None


__all__ = ["WindowDetector"]
