from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any


class LegacyAutomationAdapter:
    def __init__(self, backend_root: Path) -> None:
        self.backend_root = Path(backend_root)
        self.module_path = self.backend_root / "automation" / "pc_automation.py"
        self._module: Any | None = None
        self._load_error = ""

    def status(self) -> dict[str, Any]:
        if self.module_path.exists() and self._module is None and not self._load_error:
            self._load()
        return {
            "name": "legacy_pc_automation",
            "available": self.module_path.exists() and hasattr(self._module, "execute_command"),
            "path": str(self.module_path),
            "error": self._load_error,
        }

    def execute(self, command: str) -> dict[str, Any]:
        if self._module is None and not self._load_error:
            self._load()
        if self._module is None or not hasattr(self._module, "execute_command"):
            return {
                "success": False,
                "available": False,
                "error": self._load_error or "legacy automation module unavailable",
                "command": command,
            }
        try:
            result = self._module.execute_command(command)
            if isinstance(result, dict):
                return {"available": True, **result}
            return {"available": True, "success": True, "result": result}
        except Exception as exc:
            return {"success": False, "available": True, "error": str(exc), "command": command}

    def _load(self) -> None:
        if not self.module_path.exists():
            self._load_error = f"missing module: {self.module_path}"
            return
        try:
            spec = importlib.util.spec_from_file_location("jarvis_legacy_pc_automation", self.module_path)
            if spec is None or spec.loader is None:
                self._load_error = "unable to create module spec"
                return
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self._module = module
        except Exception as exc:
            self._load_error = str(exc)
