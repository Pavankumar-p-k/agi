"""Structured discovery of native Windows windows and accessible controls."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
import logging

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ControlInfo:
    name: str = ""
    control_type: str = ""
    automation_id: str = ""
    enabled: bool = True
    visible: bool = True
    bounds: dict[str, int] = field(default_factory=dict)
    patterns: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WindowInfo:
    title: str
    handle: int | None = None
    process_id: int | None = None
    class_name: str = ""
    bounds: dict[str, int] = field(default_factory=dict)
    active: bool = False
    controls: tuple[ControlInfo, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "controls": [control.to_dict() for control in self.controls],
        }


class DesktopDiscovery:
    """Best-effort discovery with an explicit backend indicator.

    pywinauto is optional. Without it, window discovery still works through
    pygetwindow, while control discovery returns an honest empty result.
    """

    def __init__(self, window_controller: Any | None = None, max_controls: int = 200):
        if max_controls <= 0:
            raise ValueError("max_controls must be positive")
        self.window_controller = window_controller
        self.max_controls = max_controls

    def list_windows(self) -> list[WindowInfo]:
        windows: list[WindowInfo] = []
        raw_windows = (
            self.window_controller.list_windows()
            if self.window_controller is not None
            else self._pygetwindow_list()
        )
        for window in raw_windows:
            title = str(window.get("title", "") or "").strip()
            if not title:
                continue
            windows.append(
                WindowInfo(
                    title=title,
                    bounds={
                        "left": int(window.get("left", 0)),
                        "top": int(window.get("top", 0)),
                        "width": int(window.get("width", 0)),
                        "height": int(window.get("height", 0)),
                    },
                    active=bool(window.get("isActive", False)),
                )
            )
        return windows

    @staticmethod
    def _pygetwindow_list() -> list[dict[str, Any]]:
        import pygetwindow as gw
        return [
            {
                "title": window.title,
                "left": window.left,
                "top": window.top,
                "width": window.width,
                "height": window.height,
                "isActive": window.isActive,
            }
            for window in gw.getAllWindows()
        ]

    def discover_window(self, title: str, include_controls: bool = True) -> WindowInfo | None:
        if not title:
            raise ValueError("title is required")
        candidates = [window for window in self.list_windows() if title.lower() in window.title.lower()]
        if not candidates:
            return None
        window = candidates[0]
        if not include_controls:
            return window
        controls = self._discover_controls(title)
        return WindowInfo(
            title=window.title,
            handle=window.handle,
            process_id=window.process_id,
            class_name=window.class_name,
            bounds=window.bounds,
            active=window.active,
            controls=tuple(controls),
        )

    def capability_snapshot(self, title: str) -> dict[str, Any]:
        window = self.discover_window(title)
        if window is None:
            return {"found": False, "title": title, "backend": self.backend_name}
        return {
            "found": True,
            "backend": self.backend_name,
            "window": window.to_dict(),
            "capabilities": sorted({pattern for control in window.controls for pattern in control.patterns}),
        }

    @property
    def backend_name(self) -> str:
        try:
            import pywinauto  # noqa: F401
        except ImportError:
            return "pygetwindow"
        return "pywinauto-uia"

    def _discover_controls(self, title: str) -> list[ControlInfo]:
        try:
            from pywinauto import Desktop
        except ImportError:
            return []
        try:
            window = Desktop(backend="uia").window(title_re=f".*{title}.*")
            controls: list[ControlInfo] = []
            for element in window.descendants():
                if len(controls) >= self.max_controls:
                    break
                info = element.element_info
                rect = element.rectangle()
                controls.append(
                    ControlInfo(
                        name=str(getattr(info, "name", "") or ""),
                        control_type=str(getattr(info, "control_type", "") or ""),
                        automation_id=str(getattr(info, "automation_id", "") or ""),
                        enabled=bool(element.is_enabled()),
                        visible=bool(element.is_visible()),
                        bounds={
                            "left": int(rect.left),
                            "top": int(rect.top),
                            "width": int(rect.width()),
                            "height": int(rect.height()),
                        },
                        patterns=tuple(sorted(self._patterns(element))),
                    )
                )
            return controls
        except Exception as exc:
            logger.warning("UIA discovery failed for %s: %s", title, exc)
            return []

    @staticmethod
    def _patterns(element: Any) -> set[str]:
        patterns = set()
        for pattern, method in (
            ("invoke", "invoke"),
            ("value", "get_value"),
            ("selection", "get_selection"),
            ("toggle", "get_toggle_state"),
        ):
            if hasattr(element, method):
                patterns.add(pattern)
        return patterns


def create_desktop_discovery(window_controller: Any) -> DesktopDiscovery:
    """Create discovery against the repository's shared window controller."""
    return DesktopDiscovery(window_controller=window_controller)
