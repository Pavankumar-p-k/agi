"""ProcessMonitor — read-only process/system awareness."""
from __future__ import annotations

from typing import Optional


class ProcessMonitor:
    """Process listing and system stats via a lazy psutil backend."""

    def __init__(self) -> None:
        self._psutil = None

    def _lazy_import(self):
        if self._psutil is None:
            try:
                import psutil
                self._psutil = psutil
            except ImportError:
                self._psutil = False
        return self._psutil

    def list_processes(self) -> list:
        psutil = self._lazy_import()
        if not psutil:
            return []
        try:
            return [{"pid": p.info.get("pid"), "name": p.info.get("name", "")}
                    for p in psutil.process_iter(["pid", "name"])]
        except Exception:  # noqa: BLE001
            return []

    def find_by_name(self, name: str) -> list:
        key = str(name).lower().replace(".exe", "")
        return [p for p in self.list_processes()
                if key in str(p.get("name", "")).lower().replace(".exe", "")]

    def is_process_running(self, name: str) -> bool:
        return len(self.find_by_name(name)) > 0

    def is_running(self, name: str) -> bool:
        return self.is_process_running(name)

    def get_system_stats(self) -> dict:
        psutil = self._lazy_import()
        if not psutil:
            return {"available": False}
        try:
            return {
                "available": True,
                "cpu_percent": psutil.cpu_percent(interval=0.1),
                "ram_total_gb": round(psutil.virtual_memory().total / 1024 ** 3, 2),
                "ram_used_gb": round(psutil.virtual_memory().used / 1024 ** 3, 2),
                "ram_percent": psutil.virtual_memory().percent,
            }
        except Exception:  # noqa: BLE001
            return {"available": False}


__all__ = ["ProcessMonitor"]
