"""ScreenCapture — screenshot capture producing artifact results (Gate 7).

The real capture backend (mss/PIL/pyautogui) is optional; when absent,
capture reports honestly that no backend is available rather than
fabricating an artifact.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class CaptureResult:
    """Artifact representation of a single screenshot."""
    artifact_id: str
    width: int
    height: int
    format: str
    size_bytes: int
    timestamp: float
    path: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "artifact_id": self.artifact_id,
            "width": self.width,
            "height": self.height,
            "format": self.format,
            "size_bytes": self.size_bytes,
            "timestamp": self.timestamp,
            "path": self.path,
            "metadata": dict(self.metadata),
        }


class ScreenCapture:
    """Captures the screen through whichever backend is available."""

    def __init__(self) -> None:
        self._last_result: Optional[CaptureResult] = None

    def capture(self, save_path: Optional[str] = None) -> CaptureResult:
        """Take a screenshot; returns a CaptureResult artifact.

        Raises RuntimeError when no capture backend is installed —
        callers (the DesktopController) surface that honestly.
        """
        image = self._grab()
        if image is None:
            raise RuntimeError("no screen capture backend available")

        width, height = image.size
        fmt = "PNG"
        size_bytes = 0
        path = save_path
        if save_path:
            image.save(save_path, format=fmt)
            import os
            size_bytes = os.path.getsize(save_path)
        else:
            try:
                size_bytes = len(image.tobytes())
            except Exception:  # noqa: BLE001
                size_bytes = width * height * 4

        result = CaptureResult(
            artifact_id=f"sc_{uuid.uuid4().hex[:12]}",
            width=width,
            height=height,
            format=fmt,
            size_bytes=size_bytes,
            timestamp=time.time(),
            path=path,
        )
        self._last_result = result
        return result

    @property
    def last_result(self) -> Optional[CaptureResult]:
        return self._last_result

    # ── backends ─────────────────────────────────────────────────────
    @staticmethod
    def _grab():
        try:
            import mss  # type: ignore
            import mss.tools  # type: ignore

            with mss.mss() as sct:
                monitor = sct.monitors[1]
                raw = sct.grab(monitor)
                from PIL import Image
                return Image.frombytes(
                    "RGB", raw.size, raw.bgra, "raw", "BGRX")
        except Exception:  # noqa: BLE001 — fall through to next backend
            pass
        try:
            import pyautogui
            return pyautogui.screenshot()
        except Exception:  # noqa: BLE001
            return None


# Module-level singleton.
screen_capture = ScreenCapture()


__all__ = ["CaptureResult", "ScreenCapture", "screen_capture"]
