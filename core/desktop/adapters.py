"""Desktop adapters — application-specific action wrappers.

Each adapter declares which applications it supports and which actions
it can perform. The AdapterRegistry answers "does anything support
application X doing action Y?" so the planner never invents abilities.
"""
from __future__ import annotations

from typing import Callable, Optional


class FileExplorerAdapter:
    name = "explorer"

    def supports(self, application: str, action: str) -> bool:
        return application.lower() in ("explorer", "file explorer") and \
            action in ("reveal", "open", "list")

    def reveal(self, path: str, user_actions: Callable) -> dict:
        """Reveal a path in File Explorer (selects the file)."""
        try:
            import subprocess
            subprocess.Popen(["explorer", "/select,", str(path)])
            return {"success": True, "revealed": str(path)}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc)}

    def open(self, path: str, user_actions: Callable,
             app: Optional[str] = None) -> dict:
        try:
            import os
            import subprocess
            if app:
                subprocess.Popen([app, str(path)], shell=False)
                return {"success": True, "opened": str(path), "app": app}
            os.startfile(str(path))  # type: ignore[attr-defined]
            return {"success": True, "opened": str(path)}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc)}


class TextEditorAdapter:
    name = "text_editor"

    def supports(self, application: str, action: str) -> bool:
        return application.lower() in ("notepad", "notepad++", "code") and \
            action in ("open", "edit", "type")

    def open(self, path: str, app: str = "notepad") -> dict:
        try:
            import subprocess
            subprocess.Popen([app, str(path)], shell=False)
            return {"success": True, "opened": str(path), "app": app}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc)}


class ProcessInspectionAdapter:
    name = "process_inspection"

    def supports(self, application: str, action: str) -> bool:
        return application.lower() in ("process", "system") and \
            action in ("list", "inspect", "running")

    def list_processes(self, user_actions: Callable) -> dict:
        try:
            import psutil
            return {"success": True,
                    "processes": [{"pid": p.pid, "name": p.name()}
                                  for p in psutil.process_iter()]}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc)}


class ClipboardAdapter:
    name = "clipboard"

    def supports(self, application: str, action: str) -> bool:
        return application.lower() == "clipboard" and \
            action in ("get", "set")

    def get(self) -> dict:
        try:
            import pyperclip
            return {"success": True, "text": pyperclip.paste()}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc)}

    def set(self, text: str) -> dict:
        try:
            import pyperclip
            pyperclip.copy(str(text))
            return {"success": True}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc)}


class WindowManagementAdapter:
    name = "window_management"

    def supports(self, application: str, action: str) -> bool:
        return application.lower() in ("window", "windows", "desktop") and \
            action in ("focus", "close", "minimize", "maximize", "list")

    def list(self, window_controller: Callable) -> dict:
        try:
            windows = window_controller.list_windows()
            return {"success": True, "windows": windows}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc)}


class AdapterRegistry:
    """Answers support queries across all registered adapters."""

    def __init__(self, adapters: list) -> None:
        self._adapters = list(adapters)

    def applications(self) -> list:
        return sorted({a.name for a in self._adapters})

    def supports(self, application: str, action: str) -> bool:
        return any(a.supports(str(application), str(action))
                   for a in self._adapters)

    def find(self, application: str, action: str):
        for adapter in self._adapters:
            if adapter.supports(str(application), str(action)):
                return adapter
        return None


__all__ = [
    "FileExplorerAdapter", "TextEditorAdapter", "ProcessInspectionAdapter",
    "ClipboardAdapter", "WindowManagementAdapter", "AdapterRegistry",
]
