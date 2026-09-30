"""Desktop adapters — application-specific action wrappers.

Each adapter declares which applications it supports and which actions
it can perform, and delegates the real work to the shared action layer
passed in by the caller. The AdapterRegistry answers "does anything
support application X doing action Y?" so the planner never invents
abilities.
"""
from __future__ import annotations

from typing import Any, Callable, Optional


class FileExplorerAdapter:
    name = "explorer"
    application = "Explorer"

    def supports(self, application: str, action: str) -> bool:
        app = str(application).lower()
        return app in ("explorer", "file explorer") and \
            action in ("reveal", "open", "list")

    # ── delegated actions ────────────────────────────────────────────
    def reveal(self, path: str, actions: Any) -> dict:
        return actions.reveal_in_explorer(path)

    def open(self, path: str, actions: Any,
             app: Optional[str] = None) -> dict:
        if app:
            return actions.open_with(path, app)
        return actions.open_with(path, "explorer")


class TextEditorAdapter:
    name = "text_editor"
    application = "Notepad"

    def supports(self, application: str, action: str) -> bool:
        app = str(application).lower()
        return app in ("notepad", "notepad++", "code") and \
            action in ("open", "read", "write", "edit", "type")

    def open(self, path: str, actions: Any, app: str = "notepad") -> dict:
        return actions.open_with(path, app)

    def read(self, path: str, actions: Any) -> dict:
        return actions.read_file(path)

    def write(self, path: str, content: str, actions: Any) -> dict:
        return actions.write_file(path, content)


class ProcessInspectionAdapter:
    name = "process_inspection"
    application = "System"
    _ACTIONS = ("list", "inspect", "running")

    def supports(self, application: str, action: Optional[str] = None) -> bool:
        if action is None:  # single-argument form: supports(action)
            return str(application).lower() in self._ACTIONS
        app = str(application).lower()
        return app in ("process", "system") and action in self._ACTIONS

    def list(self, monitor: Any, limit: int = 50) -> dict:
        processes = monitor.list_processes(limit)
        return {"success": True,
                "processes": [{"name": getattr(p, "name", ""), "pid": getattr(p, "pid", 0)}
                              for p in processes]}

    def is_running(self, name: str, monitor: Any) -> dict:
        return {"running": bool(monitor.is_running(name))}


class ClipboardAdapter:
    name = "clipboard"
    application = "Clipboard"

    def supports(self, application: str, action: Optional[str] = None) -> bool:
        if action is None:  # single-argument form: supports(action)
            return str(application).lower() in ("read", "write", "get", "set", "clear")
        return str(application).lower() == "clipboard" and \
            action in ("read", "write", "get", "set", "clear")

    def read(self, manager: Any) -> dict:
        result = manager.get_text()
        if hasattr(result, "content"):  # structured result object
            return {"success": bool(getattr(result, "success", True)),
                    "content": str(getattr(result, "content", ""))}
        return {"success": True, "content": str(result)}

    def write(self, text: str, manager: Any) -> dict:
        result = manager.set_text(text)
        if isinstance(result, dict):
            return result
        return {"success": bool(getattr(result, "success", True)),
                "error": str(getattr(result, "error", "") or "")}


class WindowManagementAdapter:
    name = "window_management"
    application = "Window"
    _ACTIONS = ("focus", "minimize", "maximize", "list")

    def supports(self, application: str, action: Optional[str] = None) -> bool:
        if action is None:  # single-argument form: supports(action)
            return str(application).lower() in self._ACTIONS
        app = str(application).lower()
        return app in ("window", "windows", "desktop") and action in self._ACTIONS

    def list(self, controller: Any) -> dict:
        try:
            windows = controller.list_windows()
        except Exception as exc:  # noqa: BLE001 — delegate errors surface honestly
            return {"success": False, "count": 0, "windows": [],
                    "error": str(exc)}
        return {"success": True, "count": len(windows),
                "windows": list(windows)}

    def focus(self, title: str, controller: Any) -> dict:
        result = controller.focus(title)
        if isinstance(result, dict):
            return result
        return {"success": bool(getattr(result, "success", False)),
                "error": str(getattr(result, "error", "") or "")}


class AdapterRegistry:
    """Answers support queries across all registered adapters."""

    def __init__(self, adapters: Optional[list] = None) -> None:
        self._adapters: list = []
        for adapter in (adapters or []):
            self.register(adapter)

    def register(self, adapter: Any) -> None:
        application = str(getattr(adapter, "application", "") or "").strip()
        if not application:
            raise ValueError("adapter must declare a non-empty application")
        if not hasattr(adapter, "supports"):
            raise ValueError("adapter must implement supports()")
        self._adapters.append(adapter)

    def applications(self) -> list:
        return sorted({str(getattr(a, "application", a.name))
                       for a in self._adapters})

    def supports(self, application: str, action: str) -> bool:
        return any(a.supports(str(application), str(action))
                   for a in self._adapters)

    def get(self, application: str) -> Optional[Any]:
        """The adapter whose declared application matches, else None."""
        wanted = str(application).strip().lower()
        for adapter in self._adapters:
            declared = str(getattr(adapter, "application", "")).strip().lower()
            if declared == wanted:
                return adapter
        return None

    def find(self, application: str, action: str) -> Optional[Any]:
        for adapter in self._adapters:
            if adapter.supports(str(application), str(action)):
                return adapter
        return None


__all__ = [
    "FileExplorerAdapter", "TextEditorAdapter", "ProcessInspectionAdapter",
    "ClipboardAdapter", "WindowManagementAdapter", "AdapterRegistry",
]
