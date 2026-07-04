# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from core.observability.metrics import set_active_sessions, set_sandbox_containers

logger = logging.getLogger("jarvis.monitors.resource")

_psutil_available = False
try:
    import psutil
    _psutil_available = True
except ImportError:
    psutil = None  # type: ignore


@dataclass
class ResourceSnapshot:
    cpu_percent: float = 0.0
    ram_percent: float = 0.0
    ram_available_gb: float = 0.0
    disk_percent: float = 0.0
    disk_free_gb: float = 0.0
    gpu_free_gb: float = 0.0
    active_agents: int = 0
    active_skills: list[str] = field(default_factory=list)
    timestamp: float = 0.0

    @property
    def is_healthy(self) -> bool:
        return self.cpu_percent < 80 and self.ram_percent < 85

    @property
    def is_critical(self) -> bool:
        return self.cpu_percent >= 95 or self.ram_percent >= 95

    @property
    def should_throttle(self) -> bool:
        return self.cpu_percent > 80 or self.ram_percent > 85

    @property
    def should_reject(self) -> bool:
        return self.cpu_percent > 95 or self.ram_percent > 95

    @property
    def cpu_pct(self) -> float:
        return self.cpu_percent

    @property
    def ram_pct(self) -> float:
        return self.ram_percent

    @property
    def disk_pct(self) -> float:
        return self.disk_percent

    @property
    def agent_count(self) -> int:
        return self.active_agents

    def recommend_concurrency(self) -> int:
        cpu_headroom = max(0, 100 - self.cpu_percent)
        ram_headroom = max(0, 100 - self.ram_percent)
        headroom = min(cpu_headroom, ram_headroom)
        if headroom >= 80:
            return 8
        if headroom >= 60:
            return 6
        if headroom >= 40:
            return 4
        if headroom >= 20:
            return 2
        return 1

    def to_dict(self) -> dict:
        return {
            "cpu_percent": round(self.cpu_percent, 1),
            "ram_percent": round(self.ram_percent, 1),
            "ram_available_gb": round(self.ram_available_gb, 2),
            "disk_percent": round(self.disk_percent, 1),
            "disk_free_gb": round(self.disk_free_gb, 2),
            "gpu_free_gb": round(self.gpu_free_gb, 2),
            "active_agents": self.active_agents,
            "active_skills": self.active_skills,
            "is_healthy": self.is_healthy,
            "is_critical": self.is_critical,
            "timestamp": self.timestamp,
        }


class ResourceMonitor:
    """Consolidated system resource monitor — CPU, RAM, Disk, GPU.

    Replaces: health_monitor (GPU), environment_monitor (RAM/Disk),
    proactive_monitor/SystemMonitor (CPU/RAM/Disk), resource_monitor,
    telemetry/HealthTelemetry.
    """

    def __init__(self):
        self._active_agents: set[str] = set()
        self._active_skills: list[str] = []

    def register_agent(self, agent_id: str) -> None:
        self._active_agents.add(agent_id)

    def unregister_agent(self, agent_id: str) -> None:
        self._active_agents.discard(agent_id)

    def start_skill(self, skill_id: str) -> None:
        self._active_skills.append(skill_id)

    def finish_skill(self, skill_id: str) -> None:
        try:
            self._active_skills.remove(skill_id)
        except ValueError:
            pass

    def get_snapshot(self) -> ResourceSnapshot:
        return self.snapshot()

    def should_throttle(self) -> bool:
        return self.snapshot().should_throttle

    def should_reject(self) -> bool:
        return self.snapshot().should_reject

    def snapshot(self) -> ResourceSnapshot:
        snap = ResourceSnapshot(timestamp=time.time())

        if _psutil_available:
            snap.cpu_percent = psutil.cpu_percent(interval=0.1)  # type: ignore
            mem = psutil.virtual_memory()  # type: ignore
            snap.ram_percent = mem.percent
            snap.ram_available_gb = mem.available / (1024 ** 3)
            disk = psutil.disk_usage("/")  # type: ignore
            snap.disk_percent = disk.percent
            snap.disk_free_gb = disk.free / (1024 ** 3)

        snap.gpu_free_gb = self._check_gpu()
        snap.active_agents = len(self._active_agents)
        snap.active_skills = list(self._active_skills)

        # Export to metrics
        set_active_sessions(snap.active_agents)

        return snap

    @staticmethod
    def _check_gpu() -> float:
        try:
            from pynvml import (
                nvmlInit, nvmlDeviceGetHandleByIndex,
                nvmlDeviceGetMemoryInfo,
            )
            nvmlInit()
            handle = nvmlDeviceGetHandleByIndex(0)
            info = nvmlDeviceGetMemoryInfo(handle)
            return info.free / (1024 ** 3)
        except Exception as e:
            logger.warning("[monitors.resource] GPU check failed: %s", e)
            return 0.0


resource_monitor = ResourceMonitor()
