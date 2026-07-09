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

"""core/health_monitor.py
Per-module health monitor â€” background checks every N seconds for each registered module.
Exposes app.state.health for auto-failover and the /health endpoint.

Auto-restarts failed modules via self_healing handlers (max 3 consecutive failures
triggers a heal attempt).

Usage in lifespan():
    from core.health_monitor import HealthMonitor
    app.state.health = HealthMonitor()
    await app.state.health.start()
"""

from __future__ import annotations

import asyncio
import logging
import time

logger = logging.getLogger("health_monitor")


class HealthMonitor:
    """Tracks per-module health with exponential backoff and auto-restart."""

    MODULES = ["ollama", "search", "stt", "tts", "wake_word", "gpu"]

    def __init__(self, interval: int = 30):
        self._interval = interval
        self._task: asyncio.Task | None = None
        self._modules: dict[str, dict] = {}

        for name in self.MODULES:
            self._modules[name] = {
                "status": "unknown",
                "last_ok": 0.0,
                "failures": 0,
                "skips_until": 0.0,  # for backoff
            }

    async def start(self):
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._check_loop())

    async def stop(self):
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _check_loop(self):
        while True:
            for name in self.MODULES:
                mod = self._modules[name]
                # Skip dead modules (auto-heal already failed, retry on restart)
                if mod.get("status") == "dead":
                    continue
                # Skip if in backoff
                if mod["skips_until"] > time.time():
                    continue
                ok, detail = await self._check_module(name)
                if ok:
                    mod["status"] = "ok"
                    mod["last_ok"] = time.time()
                    mod["failures"] = 0
                else:
                    mod["failures"] += 1
                    if mod["failures"] >= 3:
                        mod["status"] = "down"
                        mod["skips_until"] = time.time() + self._interval * min(mod["failures"], 10)
                        await self._auto_heal(name, detail)
                    else:
                        mod["status"] = "degraded"
            await asyncio.sleep(self._interval)

    async def _check_module(self, name: str) -> tuple[bool, str]:
        """Check a single module. Returns (ok: bool, detail: str)."""
        if name == "ollama":
            ok = await self._check_ollama()
            return ok, "" if ok else "ollama not responding"
        elif name == "search":
            return await self._check_search()
        elif name in ("stt", "tts", "wake_word"):
            return await self._check_voice_module(name)
        elif name == "gpu":
            return self._check_gpu()
        return True, ""

    async def _check_ollama(self) -> bool:
        """Check Ollama connectivity via /api/tags endpoint."""
        try:
            import httpx
            from core.config_registry import config as _c
            ollama_url = _c.get("ollama.base_url", "http://localhost:11434")
            async with httpx.AsyncClient(timeout=3) as client:
                r = await client.get(f"{ollama_url}/api/tags")
            return r.status_code == 200
        except Exception:
            return False

    async def _check_search(self) -> tuple[bool, str]:
        """Check SearXNG on port 8888."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=3) as client:
                r = await client.get("http://localhost:8888/health")
            if r.status_code < 500:
                return True, ""
            return False, f"search returned {r.status_code}"
        except Exception as e:
            return False, str(e)[:60]

    async def _check_voice_module(self, name: str) -> tuple[bool, str]:
        """Check voice modules by import (lazy-loaded, may not be imported yet)."""
        try:
            if name == "stt":
                from assistant.stt import get_stt
                _ = get_stt()
            elif name == "tts":
                from assistant.tts import get_tts
                _ = get_tts()
            elif name == "wake_word":
                from assistant.wake_word import get_detector
                _ = get_detector()
            return True, ""
        except ImportError:
            return True, "not_loaded"  # Not an error if not imported yet
        except Exception as e:
            return False, str(e)[:60]

    def _check_gpu(self) -> tuple[bool, str]:
        """Check GPU memory via pynvml."""
        try:
            import warnings
            warnings.filterwarnings("ignore", message="The pynvml package is deprecated")
            from pynvml import nvmlDeviceGetHandleByIndex, nvmlDeviceGetMemoryInfo, nvmlInit
            nvmlInit()
            handle = nvmlDeviceGetHandleByIndex(0)
            info = nvmlDeviceGetMemoryInfo(handle)
            free_gb = info.free / 1024 ** 3
            if free_gb < 0.5:
                return False, f"low VRAM: {free_gb:.1f}GB free"
            return True, f"{free_gb:.1f}GB free"
        except Exception as e:
            logger.warning("[HEALTH] GPU check: %s", e)
            return True, "pynvml not available"

    async def _auto_heal(self, module: str, detail: str):
        """Attempt to auto-heal a failed module via self_healing."""
        try:
            from core.self_healing import self_healing
            logger.warning("[HEALTH] Auto-healing %s (failures=%s): %s", module, self._modules[module]['failures'], detail)
            if module == "ollama":
                await self_healing.heal_ollama()
            elif module == "search":
                await self_healing.heal_search()
            ok, _ = await self._check_module(module)
            if ok:
                self._modules[module]["status"] = "ok"
                self._modules[module]["failures"] = 0
                self._modules[module]["last_ok"] = time.time()
                logger.info("[HEALTH] Auto-heal succeeded for %s", module)
            else:
                self._modules[module]["status"] = "dead"
                logger.warning("[HEALTH] Auto-heal failed for %s â€” marked dead (won't retry until restart)", module)
        except Exception as e:
            logger.warning("[HEALTH] Auto-heal error for %s: %s", module, e)

    def module_status(self, name: str) -> str:
        return self._modules.get(name, {}).get("status", "unknown")

    def module_ok(self, name: str) -> bool:
        mod = self._modules.get(name)
        if not mod:
            return False
        return mod["status"] == "ok"

    def all_ok(self) -> bool:
        return all(m["status"] == "ok" for m in self._modules.values())

    def ollama_alive(self) -> bool:
        return self.module_ok("ollama")

    def record_failure(self, module: str, detail: str) -> None:
        if module not in self._modules:
            self._modules[module] = {
                "status": "degraded",
                "failures": 1,
                "last_ok": 0.0,
                "skips_until": 0.0,
                "last_detail": detail
            }
        else:
            self._modules[module]["failures"] += 1
            self._modules[module]["status"] = "degraded"
            self._modules[module]["last_detail"] = detail

    async def check_all(self) -> dict:
        """Run all module checks and return status summary."""
        for name in list(self._modules.keys()):
            ok, detail = await self._check_module(name)
            if not ok:
                self.record_failure(name, detail)
        return {name: m["status"] for name, m in self._modules.items()}

    def to_dict(self) -> dict:
        now = time.time()
        modules = {}
        for name, mod in self._modules.items():
            modules[name] = {
                "status": mod["status"],
                "last_ok_ago_s": round(now - mod["last_ok"], 1) if mod["last_ok"] else -1,
                "failures": mod["failures"],
            }
        return {
            "ollama_alive": self.module_ok("ollama"),
            "all_ok": self.all_ok(),
            "interval_s": self._interval,
            "modules": modules,
        }
