"""
Module: core.desktop.screen
Screen capture with result serialization.
"""
from __future__ import annotations
from typing import Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid
import time
import logging
import os
from core.desktop.safety import DesktopActionType

logger = logging.getLogger(__name__)


@dataclass
class CaptureResult:
    artifact_id: str = ""
    width: int = 0
    height: int = 0
    format: str = "PNG"
    size_bytes: int = 0
    timestamp: float = field(default_factory=time.time)
    file_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    monitor_index: int = 0
    region: dict[str, int] | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "artifact_id": self.artifact_id,
            "width": self.width,
            "height": self.height,
            "format": self.format,
            "size_bytes": self.size_bytes,
            "timestamp": self.timestamp,
            "monitor_index": self.monitor_index,
            "metadata": self.metadata,
        }
        if self.file_path:
            result["file_path"] = self.file_path
        if self.region:
            result["region"] = self.region
        return result

    @property
    def has_data(self) -> bool:
        return self.size_bytes > 0

    @property
    def has_file(self) -> bool:
        return self.file_path is not None and len(self.file_path) > 0


@dataclass
class CaptureRegion:
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0

    def to_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}


@dataclass
class ScreenCapture:
    _captures: list[CaptureResult] = field(default_factory=list)
    _max_captures: int = 100

    @staticmethod
    def _remove_file(capture: CaptureResult) -> None:
        if capture.file_path:
            try:
                os.unlink(capture.file_path)
            except FileNotFoundError:
                pass
            except OSError:
                logger.warning("Unable to remove capture artifact %s", capture.file_path)

    def capture(self, region: CaptureRegion | None = None, format: str = "PNG", monitor_index: int = 0, metadata: dict[str, Any] | None = None) -> CaptureResult:
        import io
        import tempfile
        import pyautogui
        from core.desktop.controller import desktop_controller
        decision = desktop_controller.safety.check(DesktopActionType.SCREEN_CAPTURE)
        if not decision.allowed:
            raise PermissionError(decision.reason)
        if format.upper() not in {"PNG", "JPEG", "BMP"}:
            raise ValueError(f"Unsupported capture format: {format}")
        image = pyautogui.screenshot(region=tuple(region.to_dict().values()) if region else None)
        buffer = io.BytesIO()
        image.save(buffer, format=format.upper())
        suffix = f".{format.lower()}"
        artifact = tempfile.NamedTemporaryFile(prefix="jarvis_capture_", suffix=suffix, delete=False)
        try:
            artifact.write(buffer.getvalue())
        except Exception:
            artifact.close()
            try:
                os.unlink(artifact.name)
            except OSError:
                pass
            raise
        finally:
            if not artifact.closed:
                artifact.close()
        result = CaptureResult(
            artifact_id=f"sc_{uuid.uuid4().hex[:12]}",
            format=format.upper(),
            monitor_index=monitor_index,
            metadata=metadata or {},
            width=image.width,
            height=image.height,
            size_bytes=buffer.tell(),
            file_path=artifact.name,
            region=region.to_dict() if region else None,
        )
        self._captures.append(result)
        if len(self._captures) > self._max_captures:
            evicted = self._captures[:-self._max_captures]
            self._captures = self._captures[-self._max_captures:]
            for capture in evicted:
                self._remove_file(capture)
        return result

    def recent(self, limit: int = 10) -> list[CaptureResult]:
        return self._captures[-limit:]

    def get(self, capture_id: str) -> CaptureResult | None:
        for c in self._captures:
            if c.artifact_id == capture_id:
                return c
        return None

    def clear(self) -> int:
        count = len(self._captures)
        for capture in self._captures:
            self._remove_file(capture)
        self._captures.clear()
        return count

    def count(self) -> int:
        return len(self._captures)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_captures": len(self._captures),
            "recent": [c.to_dict() for c in self._captures[-5:]],
        }


def screen_capture(**kwargs: Any) -> ScreenCapture:
    return ScreenCapture(**kwargs)
