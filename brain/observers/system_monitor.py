from __future__ import annotations

import logging
import os
from typing import Any

from brain.events.event_bus import Event
from brain.events.event_types import SystemDiskLow, SystemCpuHigh, SystemMemoryHigh

from .observer_manager import Observer

logger = logging.getLogger(__name__)


class SystemMonitor(Observer):
    """Monitors system resources: disk, CPU, memory.

    Emits events when thresholds are exceeded so the system can
    autonomously react (e.g. create cleanup goals).
    """

    def __init__(self, disk_threshold_percent: float = 10.0,
                 cpu_threshold_percent: float = 90.0,
                 memory_threshold_percent: float = 90.0,
                 poll_interval: float = 60.0, **kwargs):
        super().__init__(name="system_monitor", poll_interval=poll_interval, **kwargs)
        self.disk_threshold = disk_threshold_percent
        self.cpu_threshold = cpu_threshold_percent
        self.memory_threshold = memory_threshold_percent
        self._last_alerts: dict[str, float] = {}

    async def observe(self) -> list[Event]:
        events: list[Event] = []

        # Disk monitoring
        disk_events = self._check_disk()
        events.extend(disk_events)

        # CPU / Memory monitoring (best-effort, may not be available on all platforms)
        cpu_event = self._check_cpu()
        if cpu_event:
            events.append(cpu_event)

        mem_event = self._check_memory()
        if mem_event:
            events.append(mem_event)

        return events

    def _check_disk(self) -> list[Event]:
        events = []
        for path in self._get_mount_points():
            try:
                usage = os.statvfs(path) if hasattr(os, 'statvfs') else None
                if usage is None:
                    continue
                free_bytes = usage.f_frsize * usage.f_bavail
                total_bytes = usage.f_frsize * usage.f_blocks
                if total_bytes == 0:
                    continue
                free_percent = (free_bytes / total_bytes) * 100

                if free_percent < self.disk_threshold:
                    alert_key = f"disk_low:{path}"
                    events.append(Event(
                        type="system.disk_low",
                        source="observer.system_monitor",
                        payload=SystemDiskLow(
                            path=path,
                            free_bytes=free_bytes,
                            free_percent=round(free_percent, 1),
                        ).__dict__,
                    ))
            except OSError:
                continue
        return events

    def _get_mount_points(self) -> list[str]:
        if os.name == "nt":
            drives = []
            for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                drive = f"{letter}:\\"
                if os.path.exists(drive):
                    drives.append(drive)
            return drives
        return ["/"]

    def _check_cpu(self) -> Event | None:
        try:
            import psutil
            percent = psutil.cpu_percent(interval=0.5)
            if percent > self.cpu_threshold:
                return Event(
                    type="system.cpu_high",
                    source="observer.system_monitor",
                    payload=SystemCpuHigh(percent=percent, threshold=self.cpu_threshold).__dict__,
                )
        except ImportError:
            pass
        except Exception as e:
            logger.debug("[SystemMonitor] cpu check failed: %s", e)
        return None

    def _check_memory(self) -> Event | None:
        try:
            import psutil
            percent = psutil.virtual_memory().percent
            if percent > self.memory_threshold:
                return Event(
                    type="system.memory_high",
                    source="observer.system_monitor",
                    payload=SystemMemoryHigh(percent=percent, threshold=self.memory_threshold).__dict__,
                )
        except ImportError:
            pass
        except Exception as e:
            logger.debug("[SystemMonitor] memory check failed: %s", e)
        return None
