"""core/governance/resource_monitor.py
ResourceMonitor — lightweight psutil wrapper for JARVIS governance.

Provides:
  get_snapshot()          → ResourceSnapshot
  should_throttle()       → bool   (cpu > 80% or ram > 85%)
  should_reject()         → bool   (cpu > 95% or ram > 95%)
  recommend_concurrency() → int    (1–8)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import List

logger = logging.getLogger(__name__)


# ── data class ────────────────────────────────────────────────────────────────

@dataclass
class ResourceSnapshot:
    cpu_pct:       float        # 0–100
    ram_pct:       float        # 0–100
    disk_pct:      float        # 0–100
    agent_count:   int          # number of tracked active agents
    active_skills: List[str]    # skill ids currently running
    timestamp:     float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "cpu_pct":       self.cpu_pct,
            "ram_pct":       self.ram_pct,
            "disk_pct":      self.disk_pct,
            "agent_count":   self.agent_count,
            "active_skills": self.active_skills,
            "timestamp":     self.timestamp,
        }

    @property
    def is_healthy(self) -> bool:
        return self.cpu_pct < 80 and self.ram_pct < 85

    @property
    def is_critical(self) -> bool:
        return self.cpu_pct >= 95 or self.ram_pct >= 95


# ── thresholds ────────────────────────────────────────────────────────────────

_THROTTLE_CPU = 80.0
_THROTTLE_RAM = 85.0
_REJECT_CPU   = 95.0
_REJECT_RAM   = 95.0


# ── main class ────────────────────────────────────────────────────────────────

class ResourceMonitor:
    """Monitors CPU, RAM, disk, and active agent/skill counts.

    Falls back to zero-values if psutil is unavailable so JARVIS can
    still start in minimal environments.
    """

    def __init__(self):
        self._active_agents: set[str]  = set()
        self._active_skills: list[str] = []
        self._psutil_available = False
        try:
            import psutil  # noqa: F401
            self._psutil_available = True
        except ImportError:
            logger.warning(
                "[ResourceMonitor] psutil not installed — resource readings will be 0. "
                "Run: pip install psutil"
            )

    # ── public API ────────────────────────────────────────────────────────────

    def get_snapshot(self) -> ResourceSnapshot:
        cpu_pct = disk_pct = ram_pct = 0.0

        if self._psutil_available:
            try:
                import psutil
                cpu_pct  = psutil.cpu_percent(interval=0.1)
                ram      = psutil.virtual_memory()
                ram_pct  = ram.percent
                disk     = psutil.disk_usage("/")
                disk_pct = disk.percent
            except Exception as exc:
                logger.debug("[ResourceMonitor] psutil error: %s", exc)

        return ResourceSnapshot(
            cpu_pct       = cpu_pct,
            ram_pct       = ram_pct,
            disk_pct      = disk_pct,
            agent_count   = len(self._active_agents),
            active_skills = list(self._active_skills),
        )

    def should_throttle(self) -> bool:
        """Pause queue ingestion when system is under moderate load."""
        snap = self.get_snapshot()
        throttle = snap.cpu_pct > _THROTTLE_CPU or snap.ram_pct > _THROTTLE_RAM
        if throttle:
            logger.warning(
                "[ResourceMonitor] Throttle triggered — CPU=%.1f%% RAM=%.1f%%",
                snap.cpu_pct, snap.ram_pct,
            )
        return throttle

    def should_reject(self) -> bool:
        """Reject new tasks when system is critically overloaded."""
        snap = self.get_snapshot()
        reject = snap.cpu_pct > _REJECT_CPU or snap.ram_pct > _REJECT_RAM
        if reject:
            logger.error(
                "[ResourceMonitor] Reject triggered — CPU=%.1f%% RAM=%.1f%%",
                snap.cpu_pct, snap.ram_pct,
            )
        return reject

    def recommend_concurrency(self) -> int:
        """Return 1–8 based on available CPU/RAM headroom."""
        if not self._psutil_available:
            return 2  # safe default

        snap = self.get_snapshot()
        cpu_free = 100.0 - snap.cpu_pct
        ram_free = 100.0 - snap.ram_pct
        headroom = min(cpu_free, ram_free)

        if headroom >= 80:
            return 8
        if headroom >= 60:
            return 6
        if headroom >= 40:
            return 4
        if headroom >= 20:
            return 2
        return 1

    # ── agent / skill tracking ────────────────────────────────────────────────

    def register_agent(self, agent_id: str) -> None:
        self._active_agents.add(agent_id)

    def unregister_agent(self, agent_id: str) -> None:
        self._active_agents.discard(agent_id)

    def start_skill(self, skill_id: str) -> None:
        if skill_id not in self._active_skills:
            self._active_skills.append(skill_id)

    def finish_skill(self, skill_id: str) -> None:
        try:
            self._active_skills.remove(skill_id)
        except ValueError:
            pass


# ── singleton ─────────────────────────────────────────────────────────────────

resource_monitor = ResourceMonitor()
