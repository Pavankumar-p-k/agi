"""Minimal proactive monitor stub — prevents ImportError on test-alert endpoint."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Alert:
    priority: str = "medium"
    module: str = ""
    message: str = ""
    voice_summary: str = ""


class ProactiveMonitor:
    """Placeholder monitor that logs alerts. Expand when proactive subsystem is built."""

    def __init__(self):
        self.alerts: list[Alert] = []
        logger.info("[ProactiveMonitor] initialized (stub)")

    async def _notify(self, alert: Alert):
        self.alerts.append(alert)
        logger.info("[ProactiveMonitor] alert: [%s] %s — %s", alert.priority, alert.module, alert.message)

    def to_dict(self) -> list[dict]:
        return [{"priority": a.priority, "module": a.module, "message": a.message} for a in self.alerts]


async def init_proactive_monitor(app_state: Any):
    """Initialize and attach the monitor to app state."""
    monitor = ProactiveMonitor()
    app_state.proactive_monitor = monitor
    logger.info("[ProactiveMonitor] attached to app state")
