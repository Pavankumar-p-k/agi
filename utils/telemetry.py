from pydantic.v1.dataclasses import dataclass
from dataclasses import field
from enum import Enum
from typing import Dict, Any
import time, psutil

class HealthState(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"

@dataclass
class SystemSnapshot:
    cpu_percent: float = 0.0
    ram_percent: float = 0.0
    ram_available_gb: float = 0.0
    active_tasks: int = 0
    error_rate_1m: float = 0.0
    timestamp: float = field(default_factory=time.time)

class HealthTelemetry:
    """Lightweight health telemetry that reads system metrics."""
    
    def get_snapshot(self) -> SystemSnapshot:
        mem = psutil.virtual_memory()
        return SystemSnapshot(
            cpu_percent=psutil.cpu_percent(interval=0.1),
            ram_percent=mem.percent,
            ram_available_gb=mem.available / (1024**3),
            active_tasks=0,
            error_rate_1m=0.0,
        )
    
    def compute_health_state(self, snap: SystemSnapshot) -> HealthState:
        if snap.cpu_percent > 90 or snap.ram_percent > 90:
            return HealthState.CRITICAL
        if snap.cpu_percent > 70 or snap.ram_percent > 75:
            return HealthState.DEGRADED
        return HealthState.HEALTHY

    def compute_global_health(self) -> Any:
        # Added to satisfy MetaGovernor.py requirements
        snap = self.get_snapshot()
        # Mocking values that MetaGovernor expects
        class MockHealth:
            def __init__(self, score, state, tasks):
                self.global_score = score
                self.global_state = state
                self.active_tasks = tasks
                self.module_healths = {}
            def record_intervention(self, **kwargs): pass
            def get_resource_trends(self): return {"token_total": 0}
            def adjust_thresholds(self, t): pass
            def get_intervention_log(self, n): return []

        state = self.compute_health_state(snap)
        score = 1.0 if state == HealthState.HEALTHY else (0.5 if state == HealthState.DEGRADED else 0.1)
        return MockHealth(score, state, snap.active_tasks)
