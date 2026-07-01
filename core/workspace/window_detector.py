from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class WindowInfo:
    title: str
    class_name: str
    left: int
    top: int
    width: int
    height: int
    visible: bool
    hwnd: int
    process_id: int
    process_name: str = ""


class WindowDetector:
    def __init__(self) -> None:
        self._pygetwindow: object | None = None

    def _lazy_import(self) -> None:
        if self._pygetwindow is not None:
            return
        try:
            import pygetwindow as gw
            self._pygetwindow = gw
        except ImportError:
            self._pygetwindow = False

    def list_windows(self) -> list[WindowInfo]:
        self._lazy_import()
        if not self._pygetwindow:
            return []
        try:
            results: list[WindowInfo] = []
            for w in self._pygetwindow.getAllWindows():
                try:
                    if not w.title or not w.title.strip():
                        continue
                    results.append(WindowInfo(
                        title=w.title,
                        class_name="",
                        left=w.left,
                        top=w.top,
                        width=w.width or 0,
                        height=w.height or 0,
                        visible=w.visible,
                        hwnd=w._hWnd if hasattr(w, '_hWnd') else 0,
                        process_id=0,
                    ))
                except Exception:
                    continue
            return results
        except Exception as e:
            logger.debug("WindowDetector.list_windows failed: %s", e)
            return []

    def get_active_window(self) -> WindowInfo | None:
        self._lazy_import()
        if not self._pygetwindow:
            return None
        try:
            w = self._pygetwindow.getActiveWindow()
            if w is None:
                return None
            return WindowInfo(
                title=w.title,
                class_name="",
                left=w.left,
                top=w.top,
                width=w.width or 0,
                height=w.height or 0,
                visible=w.visible,
                hwnd=w._hWnd if hasattr(w, '_hWnd') else 0,
                process_id=0,
            )
        except Exception as e:
            logger.debug("WindowDetector.get_active_window failed: %s", e)
            return None
