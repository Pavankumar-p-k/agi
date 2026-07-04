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
"""core/environment_monitor.py
Phase 5 (E1): Environment Monitor.
Tracks API health, disk space, network connectivity, Ollama status.
Provides real-time health data for proactive decisions.
"""
import json
import logging
import os
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

MONITOR_DATA_DIR = Path.home() / ".jarvis" / "monitor"


@dataclass
class ServiceHealth:
    name: str
    status: str  # "healthy", "degraded", "down", "unknown"
    latency_ms: float = 0.0
    error: str = ""
    last_checked: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "latency_ms": round(self.latency_ms, 1),
            "error": self.error,
            "last_checked": self.last_checked,
        }


@dataclass
class EnvironmentSnapshot:
    timestamp: str = ""
    disk_free_gb: float = 0.0
    disk_total_gb: float = 0.0
    memory_free_mb: float = 0.0
    memory_total_mb: float = 0.0
    ollama_available: bool = False
    ollama_latency_ms: float = 0.0
    network_reachable: bool = False
    services: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "disk_free_gb": round(self.disk_free_gb, 1),
            "disk_total_gb": round(self.disk_total_gb, 1),
            "memory_free_mb": round(self.memory_free_mb, 1),
            "ollama_available": self.ollama_available,
            "ollama_latency_ms": round(self.ollama_latency_ms, 1),
            "network_reachable": self.network_reachable,
            "services": {k: v.to_dict() for k, v in self.services.items()},
            "warnings": self.warnings,
        }


class EnvironmentMonitor:
    def __init__(self):
        self._history: list[EnvironmentSnapshot] = []
        from core.config_registry import config as _c
        self._ollama_url = _c.get("ollama.base_url")
        self._check_interval = _c.get("monitor.check_interval", 60)
        self._last_check = 0.0

    def check(self, force: bool = False) -> EnvironmentSnapshot:
        now = time.time()
        if not force and now - self._last_check < self._check_interval and self._history:
            return self._history[-1]

        snap = EnvironmentSnapshot(timestamp=datetime.now().isoformat())
        snap.disk_free_gb, snap.disk_total_gb = self._check_disk()
        snap.memory_free_mb, snap.memory_total_mb = self._check_memory()
        snap.ollama_available, snap.ollama_latency_ms = self._check_ollama()
        snap.network_reachable = self._check_network()
        snap.services = self._check_services()
        snap.warnings = self._generate_warnings(snap)

        self._history.append(snap)
        if len(self._history) > 100:
            self._history = self._history[-100:]
        self._last_check = now
        self._persist(snap)
        return snap

    def _check_disk(self) -> tuple[float, float]:
        try:
            usage = shutil.disk_usage(Path.home())
            return usage.free / (1024**3), usage.total / (1024**3)
        except Exception:
            logger.warning("[MONITOR] disk check failed")
            return 0.0, 0.0

    def _check_memory(self) -> tuple[float, float]:
        try:
            import psutil
            mem = psutil.virtual_memory()
            return mem.available / (1024**2), mem.total / (1024**2)
        except ImportError:
            pass
        try:
            result = subprocess.run(
                ["wmic", "OS", "get", "FreePhysicalMemory,TotalVisibleMemorySize", "/format:csv"],
                capture_output=True, text=True, timeout=5
            )
            lines = result.stdout.strip().split("\n")
            if len(lines) >= 2:
                parts = lines[-1].split(",")
                if len(parts) >= 3:
                    free_kb = int(parts[1])
                    total_kb = int(parts[2])
                    return free_kb / 1024, total_kb / 1024
        except Exception:
            logger.warning("[MONITOR] memory check failed")
        return 0.0, 0.0

    def _check_ollama(self) -> tuple[bool, float]:
        urls_to_try = [self._ollama_url]
        alt = os.getenv("OLLAMA_URL")
        if alt and alt not in urls_to_try:
            urls_to_try.append(alt)
        import urllib.request
        for url in urls_to_try:
            try:
                start = time.time()
                req = urllib.request.Request(f"{url.rstrip('/')}/api/tags", method="GET")
                resp = urllib.request.urlopen(req, timeout=3)
                latency = (time.time() - start) * 1000
                if resp.status == 200:
                    return True, latency
            except Exception:
                continue
        logger.warning("[MONITOR] ollama check failed — tried: %s", urls_to_try)
        return False, 0.0

    def _check_network(self) -> bool:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            sock.connect(("8.8.8.8", 443))
            sock.close()
            return True
        except Exception:
            logger.warning("[MONITOR] network check failed")
            return False

    def _check_services(self) -> dict[str, ServiceHealth]:
        services = {}
        # Check key directories
        for name, path in [
            ("templates", Path.home() / ".jarvis" / "templates" / "library"),
            ("projects", Path.home() / ".jarvis" / "projects"),
            ("api_keys", Path.home() / ".jarvis" / "api_keys.json"),
        ]:
            exists = path.exists()
            services[name] = ServiceHealth(
                name=name,
                status="healthy" if exists else "down",
                error="" if exists else f"{path} not found",
                last_checked=datetime.now().isoformat(),
            )
        return services

    def _generate_warnings(self, snap: EnvironmentSnapshot) -> list[str]:
        warnings = []
        if snap.disk_free_gb < 5.0:
            warnings.append(f"Low disk space: {snap.disk_free_gb:.1f} GB free")
        if not snap.ollama_available:
            warnings.append("Ollama is not responding on localhost:11434")
        if not snap.network_reachable:
            warnings.append("Network is unreachable")
        for s in snap.services.values():
            if s.status == "down":
                warnings.append(f"Service {s.name} is down")
        return warnings

    def get_history(self, n: int = 10) -> list[EnvironmentSnapshot]:
        return self._history[-n:] if self._history else []

    def latest(self) -> EnvironmentSnapshot | None:
        return self._history[-1] if self._history else None

    def summary(self) -> str:
        snap = self.check()
        lines = ["Environment:"]
        lines.append(f"  Disk: {snap.disk_free_gb:.1f}/{snap.disk_total_gb:.1f} GB free")
        lines.append(f"  Memory: {snap.memory_free_mb:.0f}/{snap.memory_total_mb:.0f} MB free")
        lines.append(f"  Ollama: {'✓' if snap.ollama_available else '✗'} ({snap.ollama_latency_ms:.0f}ms)")
        lines.append(f"  Network: {'✓' if snap.network_reachable else '✗'}")
        if snap.warnings:
            lines.append(f"  Warnings ({len(snap.warnings)}):")
            for w in snap.warnings:
                lines.append(f"    ⚠ {w}")
        return "\n".join(lines)

    def _persist(self, snap: EnvironmentSnapshot):
        try:
            MONITOR_DATA_DIR.mkdir(parents=True, exist_ok=True)
            path = MONITOR_DATA_DIR / "latest.json"
            path.write_text(json.dumps(snap.to_dict(), indent=2), encoding="utf-8")
            path = MONITOR_DATA_DIR / "history.jsonl"
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(snap.to_dict()) + "\n")
        except Exception as e:
            logger.warning(f"[MONITOR] Persist error: {e}")


environment_monitor = EnvironmentMonitor()
