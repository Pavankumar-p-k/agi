from __future__ import annotations

import io
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from core.desktop.replay import desktop_replay
from core.desktop.safety import DesktopActionType, SafetyManager, safety_manager

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CaptureResult:
    artifact_id: str
    width: int
    height: int
    format: str
    size_bytes: int
    timestamp: float
    replay_node_id: str = ""

    def to_dict(self) -> dict:
        return {
            "artifact_id": self.artifact_id,
            "width": self.width,
            "height": self.height,
            "format": self.format,
            "size_bytes": self.size_bytes,
            "timestamp": self.timestamp,
            "replay_node_id": self.replay_node_id,
        }


class ScreenCapture:
    def __init__(self, safety: SafetyManager | None = None) -> None:
        self._safety = safety or safety_manager

    def capture_screen(self) -> CaptureResult:
        decision = self._safety.check(DesktopActionType.SCREEN_CAPTURE)
        if not decision.allowed:
            raise RuntimeError(f"Screen capture blocked: {decision.reason}")

        import mss
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            screenshot = sct.grab(monitor)
            width = screenshot.width
            height = screenshot.height
            from PIL import Image
            img = Image.frombytes("RGB", screenshot.size, screenshot.raw)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            size_bytes = buf.tell()

        artifact_id = f"sc_{uuid.uuid4().hex[:12]}"
        node = desktop_replay.record("capture_screen", {
            "artifact_id": artifact_id, "width": width, "height": height,
        })

        return CaptureResult(
            artifact_id=artifact_id,
            width=width,
            height=height,
            format="PNG",
            size_bytes=size_bytes,
            timestamp=time.time(),
            replay_node_id=node.node_id,
        )

    def capture_window(self, window_title: str | None = None) -> CaptureResult:
        decision = self._safety.check(DesktopActionType.SCREEN_CAPTURE, {"window": window_title or "active"})
        if not decision.allowed:
            raise RuntimeError(f"Window capture blocked: {decision.reason}")

        import pygetwindow as gw
        if window_title:
            windows = gw.getWindowsWithTitle(window_title)
            if not windows:
                raise ValueError(f"No window found with title: {window_title}")
            win = windows[0]
            if win.isMinimized:
                win.restore()
                time.sleep(0.2)
        else:
            win = gw.getActiveWindow()

        if win is None:
            return self.capture_screen()

        import mss
        with mss.mss() as sct:
            region = {"left": win.left, "top": win.top, "width": win.width, "height": win.height}
            screenshot = sct.grab(region)
            from PIL import Image
            img = Image.frombytes("RGB", screenshot.size, screenshot.raw)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            size_bytes = buf.tell()

        artifact_id = f"sc_{uuid.uuid4().hex[:12]}"
        node = desktop_replay.record("capture_window", {
            "artifact_id": artifact_id, "window": window_title or "active",
        })

        return CaptureResult(
            artifact_id=artifact_id,
            width=win.width,
            height=win.height,
            format="PNG",
            size_bytes=size_bytes,
            timestamp=time.time(),
            replay_node_id=node.node_id,
        )

    def capture_region(self, x: int, y: int, width: int, height: int) -> CaptureResult:
        decision = self._safety.check(DesktopActionType.SCREEN_CAPTURE, {
            "region": {"x": x, "y": y, "width": width, "height": height},
        })
        if not decision.allowed:
            raise RuntimeError(f"Region capture blocked: {decision.reason}")

        import mss
        with mss.mss() as sct:
            region = {"left": x, "top": y, "width": width, "height": height}
            screenshot = sct.grab(region)
            from PIL import Image
            img = Image.frombytes("RGB", screenshot.size, screenshot.raw)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            size_bytes = buf.tell()

        artifact_id = f"sc_{uuid.uuid4().hex[:12]}"
        node = desktop_replay.record("capture_region", {
            "artifact_id": artifact_id, "x": x, "y": y, "width": width, "height": height,
        })

        return CaptureResult(
            artifact_id=artifact_id,
            width=width,
            height=height,
            format="PNG",
            size_bytes=size_bytes,
            timestamp=time.time(),
            replay_node_id=node.node_id,
        )


screen_capture = ScreenCapture()
