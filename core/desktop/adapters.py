"""Native desktop adapter contracts backed by shared user actions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class DesktopAdapter(Protocol):
    application: str

    def supports(self, action: str) -> bool: ...


@dataclass
class FileExplorerAdapter:
    """Safe Explorer operations; destructive work stays in UserActions/policy."""

    application: str = "explorer"

    def supports(self, action: str) -> bool:
        return action in {"reveal", "open"}

    def reveal(self, path: str, user_actions: Any) -> dict[str, Any]:
        if not self.supports("reveal"):
            return {"success": False, "error": "unsupported adapter action"}
        return user_actions.reveal_in_explorer(path)

    def open(self, path: str, user_actions: Any, app: str | None = None) -> dict[str, Any]:
        if not self.supports("open"):
            return {"success": False, "error": "unsupported adapter action"}
        return user_actions.open_with(path, app)


@dataclass
class TextEditorAdapter:
    """File-backed editor operations; mutation remains governed by caller policy."""

    application: str = "text_editor"

    def supports(self, action: str) -> bool:
        return action in {"open", "read", "write"}

    def open(self, path: str, user_actions: Any, app: str | None = None) -> dict[str, Any]:
        return user_actions.open_with(path, app or "notepad")

    def read(self, path: str, user_actions: Any) -> dict[str, Any]:
        return user_actions.read_file(path)

    def write(self, path: str, content: str, user_actions: Any) -> dict[str, Any]:
        return user_actions.write_file(path, content)


@dataclass
class ProcessInspectionAdapter:
    """Read-only process inspection; lifecycle control is intentionally absent."""

    application: str = "process_inspection"

    def supports(self, action: str) -> bool:
        return action in {"list", "find", "is_running"}

    def list(self, process_monitor: Any, limit: int = 100) -> dict[str, Any]:
        if not self.supports("list"):
            return {"success": False, "error": "unsupported adapter action"}
        snapshots = process_monitor.list_processes(max(1, min(int(limit), 500)))
        return {"success": True, "processes": [self._serialize(snapshot) for snapshot in snapshots]}

    def find(self, name: str, process_monitor: Any) -> dict[str, Any]:
        snapshots = process_monitor.find_by_name(name)
        return {"success": True, "name": name, "processes": [self._serialize(snapshot) for snapshot in snapshots]}

    def is_running(self, name: str, process_monitor: Any) -> dict[str, Any]:
        return {"success": True, "name": name, "running": bool(process_monitor.is_running(name))}

    @staticmethod
    def _serialize(snapshot: Any) -> dict[str, Any]:
        return {
            "name": str(getattr(snapshot, "name", "")),
            "pid": int(getattr(snapshot, "pid", 0)),
            "status": str(getattr(snapshot, "status", "")),
            "cpu_percent": float(getattr(snapshot, "cpu_percent", 0.0)),
            "memory_mb": float(getattr(snapshot, "memory_mb", 0.0)),
        }


@dataclass
class ClipboardAdapter:
    """Clipboard access delegated to the shared clipboard manager."""

    application: str = "clipboard"

    def supports(self, action: str) -> bool:
        return action in {"read", "write", "clear"}

    def read(self, clipboard: Any) -> dict[str, Any]:
        content = str(clipboard.get_text())
        return {"success": True, "content": content, "length": len(content)}

    def write(self, text: str, clipboard: Any) -> dict[str, Any]:
        result = clipboard.set_text(str(text))
        return {"success": bool(result.success), "content": result.content, "error": result.error}

    def clear(self, clipboard: Any) -> dict[str, Any]:
        result = clipboard.clear()
        return {"success": bool(result.success), "content": result.content, "error": result.error}


@dataclass
class WindowManagementAdapter:
    """Non-destructive window operations through the shared controller."""

    application: str = "windows"

    def supports(self, action: str) -> bool:
        return action in {"list", "focus", "minimize", "maximize"}

    def list(self, window_controller: Any) -> dict[str, Any]:
        windows = window_controller.list_windows()
        return {"success": True, "count": len(windows), "windows": windows}

    def _operate(self, action: str, title: str, window_controller: Any) -> dict[str, Any]:
        if not self.supports(action):
            return {"success": False, "error": f"unsupported window action: {action}"}
        result = getattr(window_controller, action)(title)
        return {
            "success": bool(result.success),
            "title": title,
            "action": action,
            "error": result.error,
            "details": result.details,
        }

    def focus(self, title: str, window_controller: Any) -> dict[str, Any]:
        return self._operate("focus", title, window_controller)

    def minimize(self, title: str, window_controller: Any) -> dict[str, Any]:
        return self._operate("minimize", title, window_controller)

    def maximize(self, title: str, window_controller: Any) -> dict[str, Any]:
        return self._operate("maximize", title, window_controller)


class AdapterRegistry:
    """Central adapter lookup so the agent never dispatches ad hoc app logic."""

    def __init__(self, adapters: list[DesktopAdapter] | None = None):
        self._adapters = {adapter.application.casefold(): adapter for adapter in (adapters or [])}

    def register(self, adapter: DesktopAdapter) -> None:
        key = adapter.application.strip().casefold()
        if not key:
            raise ValueError("adapter application is required")
        self._adapters[key] = adapter

    def get(self, application: str) -> DesktopAdapter | None:
        return self._adapters.get(application.strip().casefold())

    def supports(self, application: str, action: str) -> bool:
        adapter = self.get(application)
        return bool(adapter and adapter.supports(action))

    def applications(self) -> list[str]:
        return sorted(self._adapters)
