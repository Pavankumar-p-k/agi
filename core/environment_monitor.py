from dataclasses import dataclass
import shutil
import time


@dataclass
class EnvironmentSnapshot:
    disk_free_gb: float
    disk_total_gb: float
    ollama_available: bool = False
    timestamp: float = 0.0


class EnvironmentMonitor:
    def __init__(self):
        self._history: list[EnvironmentSnapshot] = []

    def check(self, force: bool = False) -> EnvironmentSnapshot:
        usage = shutil.disk_usage("/")
        snapshot = EnvironmentSnapshot(usage.free / 2**30, usage.total / 2**30, False, time.time())
        self._history.append(snapshot)
        return snapshot

    def get_history(self, count: int = 10) -> list[EnvironmentSnapshot]:
        return self._history[-count:]


environment_monitor = EnvironmentMonitor()
