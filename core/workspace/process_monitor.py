from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ProcessInfo:
    pid: int
    name: str
    exe: str
    cpu_percent: float
    memory_mb: float
    cmdline: str
    create_time: float
    status: str


class ProcessMonitor:
    def __init__(self) -> None:
        self._psutil: object | None = None

    def _lazy_import(self) -> None:
        if self._psutil is not None:
            return
        try:
            import psutil
            self._psutil = psutil
        except ImportError:
            self._psutil = False

    def list_processes(self, filter_name: str = "") -> list[ProcessInfo]:
        self._lazy_import()
        if not self._psutil:
            return []
        results: list[ProcessInfo] = []
        try:
            for proc in self._psutil.process_iter(["pid", "name", "exe", "cpu_percent", "memory_info", "cmdline", "create_time", "status"]):
                try:
                    info = proc.info
                    name = (info.get("name") or "").lower()
                    if filter_name and filter_name.lower() not in name:
                        continue
                    mem = info.get("memory_info")
                    memory_mb = (mem.rss / 1024 / 1024) if mem and hasattr(mem, "rss") else 0.0
                    cmd = info.get("cmdline")
                    results.append(ProcessInfo(
                        pid=info["pid"],
                        name=info.get("name") or "",
                        exe=info.get("exe") or "",
                        cpu_percent=info.get("cpu_percent") or 0.0,
                        memory_mb=memory_mb,
                        cmdline=" ".join(cmd) if cmd else "",
                        create_time=info.get("create_time") or 0.0,
                        status=info.get("status") or "",
                    ))
                except Exception:
                    continue
        except Exception as e:
            logger.debug("ProcessMonitor.list_processes failed: %s", e)
        return results

    def find_by_name(self, name: str) -> list[ProcessInfo]:
        return self.list_processes(filter_name=name)

    def is_process_running(self, name: str) -> bool:
        return len(self.find_by_name(name)) > 0

    def get_system_stats(self) -> dict:
        self._lazy_import()
        if not self._psutil:
            return {}
        try:
            cpu = self._psutil.cpu_percent(interval=0.1)
            mem = self._psutil.virtual_memory()
            disk = self._psutil.disk_usage("/")
            return {
                "cpu_percent": cpu,
                "memory_percent": mem.percent,
                "memory_available_mb": mem.available / 1024 / 1024,
                "disk_percent": disk.percent,
                "disk_free_gb": disk.free / 1024 / 1024 / 1024,
                "boot_time": self._psutil.boot_time(),
            }
        except Exception as e:
            logger.debug("ProcessMonitor.get_system_stats failed: %s", e)
            return {}
