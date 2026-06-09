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

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("jarvis.monitors.services")


@dataclass
class ServiceHealth:
    name: str
    status: str = "unknown"  # healthy / degraded / down / unknown
    latency_ms: float = 0.0
    error: str = ""
    last_checked: float = 0.0


@dataclass
class ServicesSnapshot:
    ollama: ServiceHealth = field(default_factory=lambda: ServiceHealth(name="ollama"))
    search: ServiceHealth = field(default_factory=lambda: ServiceHealth(name="search"))
    network: ServiceHealth = field(default_factory=lambda: ServiceHealth(name="network"))
    voice_modules: ServiceHealth = field(default_factory=lambda: ServiceHealth(name="voice"))
    timestamp: float = 0.0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ollama": {"status": self.ollama.status, "latency_ms": round(self.ollama.latency_ms, 1)},
            "search": {"status": self.search.status, "latency_ms": round(self.search.latency_ms, 1)},
            "network": {"status": self.network.status, "latency_ms": round(self.network.latency_ms, 1)},
            "voice": {"status": self.voice_modules.status},
            "warnings": self.warnings,
            "timestamp": self.timestamp,
        }


class ServiceHealthChecker:
    """Consolidated service health checker — Ollama, Search, Network, Voice.

    Replaces: health_monitor (Ollama, Search, Voice, GPU),
    environment_monitor (Ollama, Network),
    proactive_monitor/SystemMonitor (Ollama).
    """

    def __init__(self, interval: int = 30):
        self._interval = interval
        self._task: Optional[asyncio.Task] = None
        self._last_snapshot: ServicesSnapshot = ServicesSnapshot()
        self._failure_counts: dict[str, int] = {}

    async def start(self):
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._loop())

    async def stop(self):
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self):
        while True:
            self._last_snapshot = await self.check_all()
            await asyncio.sleep(self._interval)

    async def check_all(self) -> ServicesSnapshot:
        snap = ServicesSnapshot(timestamp=time.time())

        snap.ollama = await self._check_ollama()
        snap.search = await self._check_search()
        snap.network = await self._check_network()
        snap.voice_modules = await self._check_voice_modules()

        if snap.ollama.status == "down":
            snap.warnings.append("Ollama is not responding")
        if snap.search.status == "down":
            snap.warnings.append(f"Search engine (SearXNG) is not responding: {snap.search.error}")
        if snap.network.status == "down":
            snap.warnings.append("Network is unreachable")

        return snap

    def latest(self) -> ServicesSnapshot:
        return self._last_snapshot

    @staticmethod
    async def _check_ollama() -> ServiceHealth:
        sh = ServiceHealth(name="ollama")
        try:
            import httpx
            start = time.monotonic()
            async with httpx.AsyncClient(timeout=3) as client:
                r = await client.get("http://localhost:11434/api/tags")
            elapsed = (time.monotonic() - start) * 1000
            sh.latency_ms = elapsed
            if r.status_code == 200:
                sh.status = "healthy"
            else:
                sh.status = "degraded"
                sh.error = f"HTTP {r.status_code}"
        except Exception as e:
            sh.status = "down"
            sh.error = str(e)[:80]
        sh.last_checked = time.time()
        return sh

    @staticmethod
    async def _check_search() -> ServiceHealth:
        sh = ServiceHealth(name="search")
        try:
            import httpx
            start = time.monotonic()
            async with httpx.AsyncClient(timeout=3) as client:
                r = await client.get("http://localhost:8888/health")
            elapsed = (time.monotonic() - start) * 1000
            sh.latency_ms = elapsed
            if r.status_code < 500:
                sh.status = "healthy"
            else:
                sh.status = "degraded"
                sh.error = f"HTTP {r.status_code}"
        except Exception as e:
            sh.status = "down"
            sh.error = str(e)[:80]
        sh.last_checked = time.time()
        return sh

    @staticmethod
    async def _check_network() -> ServiceHealth:
        sh = ServiceHealth(name="network")
        try:
            import socket
            start = time.monotonic()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            sock.connect(("8.8.8.8", 443))
            sock.close()
            elapsed = (time.monotonic() - start) * 1000
            sh.latency_ms = elapsed
            sh.status = "healthy"
        except Exception as e:
            sh.status = "down"
            sh.error = str(e)[:80]
        sh.last_checked = time.time()
        return sh

    @staticmethod
    async def _check_voice_modules() -> ServiceHealth:
        sh = ServiceHealth(name="voice")
        results = []
        for mod in ("stt", "tts", "wake_word"):
            try:
                if mod == "stt":
                    from assistant.stt import get_stt
                    _ = get_stt()
                elif mod == "tts":
                    from assistant.tts import get_tts
                    _ = get_tts()
                elif mod == "wake_word":
                    from assistant.wake_word import get_detector
                    _ = get_detector()
                results.append(f"{mod}=ok")
            except ImportError:
                results.append(f"{mod}=not_loaded")
            except Exception as e:
                results.append(f"{mod}={e}")
        sh.status = "degraded" if any("=" in r and "ok" not in r for r in results) else "healthy"
        sh.error = ", ".join(results)
        sh.last_checked = time.time()
        return sh


service_health = ServiceHealthChecker()
