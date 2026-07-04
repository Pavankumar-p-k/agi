"""DEPRECATED — use `monitors.resource` instead.

This module is a backward-compatibility shim that re-exports
from `monitors.resource` with the original governance API names.
"""

from __future__ import annotations

import logging
import warnings
from typing import Any

from monitors.resource import (
    ResourceMonitor as _ResourceMonitor,
    ResourceSnapshot as _ResourceSnapshot,
)

logger = logging.getLogger(__name__)

_warned = False


def _warn() -> None:
    global _warned
    if not _warned:
        warnings.warn(
            "core.governance.resource_monitor is deprecated. "
            "Use 'from monitors.resource import ResourceMonitor, resource_monitor' instead.",
            DeprecationWarning, stacklevel=3,
        )
        _warned = True


class ResourceSnapshot:
    """Backward-compatible snapshot. Delegates to monitors.resource.ResourceSnapshot."""

    def __init__(self, cpu_pct: float = 0.0, ram_pct: float = 0.0,
                 disk_pct: float = 0.0, agent_count: int = 0,
                 active_skills: list[str] | None = None,
                 timestamp: float | None = None):
        import time
        self._snap = _ResourceSnapshot(
            cpu_percent=cpu_pct, ram_percent=ram_pct, disk_percent=disk_pct,
            active_agents=agent_count, active_skills=active_skills or [],
            timestamp=timestamp or time.time(),
        )
        _warn()

    @property
    def cpu_pct(self) -> float:
        return self._snap.cpu_percent

    @cpu_pct.setter
    def cpu_pct(self, value: float) -> None:
        self._snap.cpu_percent = value

    @property
    def ram_pct(self) -> float:
        return self._snap.ram_percent

    @ram_pct.setter
    def ram_pct(self, value: float) -> None:
        self._snap.ram_percent = value

    @property
    def disk_pct(self) -> float:
        return self._snap.disk_percent

    @disk_pct.setter
    def disk_pct(self, value: float) -> None:
        self._snap.disk_percent = value

    @property
    def agent_count(self) -> int:
        return self._snap.active_agents

    @agent_count.setter
    def agent_count(self, value: int) -> None:
        self._snap.active_agents = value

    @property
    def active_skills(self) -> list[str]:
        return self._snap.active_skills

    @active_skills.setter
    def active_skills(self, value: list[str]) -> None:
        self._snap.active_skills = value

    @property
    def timestamp(self) -> float:
        return self._snap.timestamp

    @timestamp.setter
    def timestamp(self, value: float) -> None:
        self._snap.timestamp = value

    @property
    def is_healthy(self) -> bool:
        return self._snap.is_healthy

    @property
    def is_critical(self) -> bool:
        return self._snap.is_critical

    def to_dict(self) -> dict:
        return {
            "cpu_pct": self._snap.cpu_percent,
            "ram_pct": self._snap.ram_percent,
            "disk_pct": self._snap.disk_percent,
            "agent_count": self._snap.active_agents,
            "active_skills": self._snap.active_skills,
            "timestamp": self._snap.timestamp,
        }


class ResourceMonitor:
    """Backward-compatible monitor. Delegates to monitors.resource.ResourceMonitor."""

    def __init__(self):
        self._mon = _ResourceMonitor()
        _warn()

    def get_snapshot(self) -> ResourceSnapshot:
        snap = self._mon.snapshot()
        return ResourceSnapshot(
            cpu_pct=snap.cpu_percent, ram_pct=snap.ram_percent,
            disk_pct=snap.disk_percent, agent_count=snap.active_agents,
            active_skills=snap.active_skills, timestamp=snap.timestamp,
        )

    def should_throttle(self) -> bool:
        return self._mon.should_throttle()

    def should_reject(self) -> bool:
        return self._mon.should_reject()

    def recommend_concurrency(self) -> int:
        return self._mon.snapshot().recommend_concurrency()

    def register_agent(self, agent_id: str) -> None:
        self._mon.register_agent(agent_id)

    def unregister_agent(self, agent_id: str) -> None:
        self._mon.unregister_agent(agent_id)

    def start_skill(self, skill_id: str) -> None:
        self._mon.start_skill(skill_id)

    def finish_skill(self, skill_id: str) -> None:
        self._mon.finish_skill(skill_id)


resource_monitor = ResourceMonitor()
