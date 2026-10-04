"""Live environment probes: disk, memory, Ollama, network (STEP 4 rebuild).

Why rebuilt
-----------
The previous body was a stub-shaped shell: ``check()`` hardcoded
``ollama_available=False`` without ever contacting the daemon, and the
``EnvironmentSnapshot`` dataclass lacked ``memory_free_mb``,
``ollama_latency_ms`` and ``network_reachable``. ``jarvis doctor`` therefore
printed ``Environment check failed: 'EnvironmentSnapshot' object has no
attribute 'memory_free_mb'`` — one of the gate errors.

Pinned specs
------------
* ``tests/integration/test_auto_resume_deep.py::test_environment_monitor`` —
  ``check(force=True)`` must return a snapshot with ``disk_free_gb >= 0``,
  ``disk_total_gb > 0``, ``isinstance(ollama_available, bool)``, and
  ``get_history(1)`` must be non-empty afterwards.
* ``jarvis-export/cli/cli_commands.py::cmd_doctor`` reads
  ``disk_free_gb``, ``memory_free_mb``, ``ollama_available``,
  ``ollama_latency_ms``, ``network_reachable``.

All four probes are real: disk via ``shutil.disk_usage``, memory via
``psutil`` (no-op fields fall back to 0 rather than fake numbers), Ollama via
an HTTP ping with measured latency, network via a short TCP connect.
"""
from __future__ import annotations

import shutil
import socket
import time
import urllib.request
from dataclasses import dataclass, field
from typing import List, Optional

__all__ = ["EnvironmentSnapshot", "EnvironmentMonitor", "environment_monitor"]

_OLLAMA_URL = "http://127.0.0.1:11434"
_NETWORK_TARGET = ("1.1.1.1", 443)
_PROBE_TTL = 10.0


@dataclass
class EnvironmentSnapshot:
    disk_free_gb: float
    disk_total_gb: float
    ollama_available: bool = False
    timestamp: float = 0.0
    # Fields the doctor gate reads (added in the STEP 4 rebuild):
    memory_free_mb: float = 0.0
    memory_total_mb: float = 0.0
    ollama_latency_ms: float = 0.0
    network_reachable: bool = False
    disk_used_pct: float = 0.0
    warnings: List[str] = field(default_factory=list)


def _probe_ollama(timeout: float = 2.0) -> tuple[bool, float]:
    """HTTP ping to the Ollama daemon. Returns (reachable, latency_ms)."""
    import os
    url = os.getenv("OLLAMA_BASE_URL", os.getenv("OLLAMA_HOST", _OLLAMA_URL))
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    url = url.rstrip("/") + "/api/tags"
    start = time.monotonic()
    try:
        with urllib.request.urlopen(url, timeout=timeout):
            pass
        return True, (time.monotonic() - start) * 1000.0
    except Exception:  # noqa: BLE001 — down daemon is a valid reading
        return False, 0.0


def _probe_network(timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection(_NETWORK_TARGET, timeout=timeout):
            return True
    except OSError:
        return False


def _probe_memory() -> tuple[float, float]:
    """Returns (free_mb, total_mb); (0.0, 0.0) when unavailable — never faked."""
    try:
        import psutil
        vm = psutil.virtual_memory()
        return vm.available / 2**20, vm.total / 2**20
    except Exception:  # noqa: BLE001 — psutil optional
        return 0.0, 0.0


class EnvironmentMonitor:
    """Caches a short-lived snapshot so repeated checks do not stall the CLI."""

    def __init__(self, ttl: float = _PROBE_TTL) -> None:
        self._history: List[EnvironmentSnapshot] = []
        self._cached: Optional[EnvironmentSnapshot] = None
        self._ttl = ttl

    def check(self, force: bool = False) -> EnvironmentSnapshot:
        now = time.time()
        if (not force and self._cached is not None
                and now - self._cached.timestamp < self._ttl):
            return self._cached

        usage = shutil.disk_usage("/")
        free_gb = usage.free / 2**30
        total_gb = usage.total / 2**30
        used_pct = (usage.used / usage.total * 100.0) if usage.total else 0.0
        free_mb, total_mb = _probe_memory()
        ollama_ok, latency = _probe_ollama()
        net_ok = _probe_network()

        warnings: List[str] = []
        if free_gb < 1.0:
            warnings.append(f"disk critically low: {free_gb:.2f}GB free")
        if total_mb and free_mb < 512:
            warnings.append(f"memory low: {free_mb:.0f}MB free")

        snapshot = EnvironmentSnapshot(
            disk_free_gb=free_gb,
            disk_total_gb=total_gb,
            ollama_available=ollama_ok,
            timestamp=now,
            memory_free_mb=free_mb,
            memory_total_mb=total_mb,
            ollama_latency_ms=round(latency, 1),
            network_reachable=net_ok,
            disk_used_pct=round(used_pct, 1),
            warnings=warnings,
        )
        self._cached = snapshot
        self._history.append(snapshot)
        # Bound memory: keep the most recent 100 readings.
        if len(self._history) > 100:
            del self._history[:-100]
        return snapshot

    def get_history(self, count: int = 10) -> List[EnvironmentSnapshot]:
        return self._history[-count:]


environment_monitor = EnvironmentMonitor()
