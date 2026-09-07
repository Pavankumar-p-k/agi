"""
Module: core.workspace.process_monitor
Real process monitoring using psutil.
"""
from __future__ import annotations
from typing import Any
from dataclasses import dataclass, field
import logging
import psutil

logger = logging.getLogger(__name__)


@dataclass
class ProcessSnapshot:
    name: str = ""
    pid: int = 0
    status: str = ""
    cpu_percent: float = 0.0
    memory_mb: float = 0.0


class ProcessMonitor:
    def __init__(self) -> None:
        logger.info("ProcessMonitor initialized")

    def list_processes(self, limit: int = 100) -> list[ProcessSnapshot]:
        processes = []
        for proc in psutil.process_iter(["name", "pid", "status", "cpu_percent", "memory_info"]):
            try:
                info = proc.info
                mem_mb = 0.0
                if info.get("memory_info"):
                    mem_mb = info["memory_info"].rss / (1024 * 1024)
                processes.append(ProcessSnapshot(
                    name=info.get("name", ""),
                    pid=info.get("pid", 0),
                    status=str(info.get("status", "")),
                    cpu_percent=info.get("cpu_percent", 0.0) or 0.0,
                    memory_mb=round(mem_mb, 1),
                ))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            if len(processes) >= limit:
                break
        return processes

    def find_by_name(self, name: str) -> list[ProcessSnapshot]:
        results = []
        for proc in psutil.process_iter(["name", "pid", "status"]):
            try:
                info = proc.info
                if name.lower() in info.get("name", "").lower():
                    results.append(ProcessSnapshot(
                        name=info.get("name", ""),
                        pid=info.get("pid", 0),
                        status=str(info.get("status", "")),
                    ))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return results

    def is_running(self, name: str) -> bool:
        return len(self.find_by_name(name)) > 0

    def snapshot(self, limit: int = 100) -> dict[str, Any]:
        procs = self.list_processes(limit)
        return {
            "total": len(procs),
            "processes": [p.__dict__ for p in procs[:limit]],
        }
