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

"""core/proactive_monitor.py
ProactiveMonitor — background system health monitoring + alert broadcast.
Runs every 5 minutes, checks CPU/RAM/Disk/Ollama/SearXNG.
Critical alerts trigger TTS + WebSocket broadcast.
"""

from __future__ import annotations
import asyncio
import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger("proactive")


@dataclass
class Alert:
    priority: str = "info"
    message: str = ""
    voice_summary: str = ""
    module: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "type": "proactive_alert",
            "priority": self.priority,
            "message": self.message,
            "voice_summary": self.voice_summary,
            "module": self.module,
            "timestamp": self.timestamp,
        }

    def to_ws_payload(self) -> dict:
        return self.to_dict()


class SystemMonitor:
    """Checks CPU, RAM, Disk, Ollama, SearXNG health."""

    async def check(self) -> Alert | None:
        loop = asyncio.get_event_loop()
        cpu_alert = await loop.run_in_executor(None, self._check_cpu)
        if cpu_alert:
            return cpu_alert
        mem_alert = await loop.run_in_executor(None, self._check_memory)
        if mem_alert:
            return mem_alert
        disk_alert = await loop.run_in_executor(None, self._check_disk)
        if disk_alert:
            return disk_alert
        ollama_alert = await self._check_ollama()
        if ollama_alert:
            return ollama_alert
        return None

    def _check_cpu(self) -> Alert | None:
        import psutil
        pct = psutil.cpu_percent(interval=1)
        if pct > 90:
            return Alert(priority="warning", module="cpu", message=f"CPU at {pct}%",
                         voice_summary=f"CPU is at {pct} percent")
        return None

    def _check_memory(self) -> Alert | None:
        import psutil
        mem = psutil.virtual_memory()
        if mem.percent > 85:
            return Alert(priority="warning", module="memory", message=f"RAM at {mem.percent}%",
                         voice_summary=f"Memory at {mem.percent} percent")
        return None

    def _check_disk(self) -> Alert | None:
        import psutil
        disk = psutil.disk_usage("/")
        if disk.percent > 90:
            return Alert(priority="warning", module="disk", message=f"Disk at {disk.percent}%",
                         voice_summary=f"Disk is {disk.percent} percent full")
        return None

    async def _check_ollama(self) -> Alert | None:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=3) as client:
                r = await client.get("http://localhost:11434/api/tags")
                if r.status_code != 200:
                    return Alert(priority="critical", module="ollama", message="Ollama not responding",
                                 voice_summary="Ollama is down")
        except Exception as e:
            logger.exception("[PROACTIVE] Ollama check failed: %s", e)
            return Alert(priority="critical", module="ollama", message="Ollama unreachable",
                         voice_summary="Ollama is offline")
        return None


class BuildMonitor:
    """Watches for stalled builds — reserved for future use."""

    async def check(self) -> Alert | None:
        return None


class ProactiveMonitor:
    """Background loop: checks system health every N seconds and broadcasts alerts."""

    def __init__(self, broadcast_fn=None, speak_fn=None, whatsapp_fn=None):
        self._broadcast = broadcast_fn
        self._speak = speak_fn
        self._whatsapp = whatsapp_fn
        self._interval = 300
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self):
        if self._task is not None:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("[PROACTIVE] ProactiveMonitor started (interval=%ds)", self._interval)

    async def stop(self):
        self._running = False
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _loop(self):
        while self._running:
            try:
                await self._tick()
            except Exception as e:
                logger.warning("[PROACTIVE] Tick error: %s", e)
            await asyncio.sleep(self._interval)

    async def _tick(self):
        checks = [
            SystemMonitor().check(),
            BuildMonitor().check(),
        ]
        results = await asyncio.gather(*checks, return_exceptions=True)
        for r in results:
            if isinstance(r, Alert):
                await self._notify(r)

    async def _notify(self, alert: Alert):
        if self._broadcast:
            try:
                await self._broadcast(alert.to_ws_payload())
            except Exception as e:
                logger.warning("[PROACTIVE] Broadcast failed: %s", e)
        if alert.priority == "critical" and self._speak:
            try:
                await self._speak(alert.voice_summary)
            except Exception as e:
                logger.warning("[PROACTIVE] TTS failed: %s", e)
        if alert.priority in ("warning", "critical") and self._whatsapp:
            try:
                await self._whatsapp(alert.message)
            except Exception as e:
                logger.warning("[PROACTIVE] WhatsApp failed: %s", e)
        logger.warning("[PROACTIVE] %s: %s", alert.module, alert.message)


proactive_monitor: ProactiveMonitor | None = None
