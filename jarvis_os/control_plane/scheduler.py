"""Heartbeat scheduler for always-on local tasks."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional


class HeartbeatScheduler:
    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self._storage_path = Path(self.config.get("storage_path", "data/jarvis_scheduler.json"))
        self._jobs: List[Dict[str, Any]] = []
        self._runner: Optional[asyncio.Task] = None
        self._running = False
        self._dispatch: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None

    async def initialize(self):
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        if self._storage_path.exists():
            try:
                self._jobs = json.loads(self._storage_path.read_text(encoding="utf-8"))
            except Exception:
                self._jobs = []
        if self._running:
            return
        self._running = True
        self._runner = asyncio.create_task(self._loop())

    async def shutdown(self):
        self._running = False
        if self._runner:
            self._runner.cancel()
            try:
                await self._runner
            except asyncio.CancelledError:
                pass
        self._persist()

    def set_dispatch(self, dispatch: Callable[[Dict[str, Any]], Awaitable[None]]):
        self._dispatch = dispatch

    def add_job(self, name: str, prompt: str, interval_s: int, channel: str = "local") -> Dict[str, Any]:
        job = {
            "job_id": f"hb_{uuid.uuid4().hex[:10]}",
            "name": name,
            "prompt": prompt,
            "interval_s": max(30, int(interval_s)),
            "channel": channel,
            "enabled": True,
            "created_at": time.time(),
            "last_run_at": 0.0,
        }
        self._jobs.append(job)
        self._persist()
        return job

    def list_jobs(self) -> List[Dict[str, Any]]:
        return list(self._jobs)

    def status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "jobs": list(self._jobs),
            "count": len(self._jobs),
        }

    async def _loop(self):
        while self._running:
            now = time.time()
            for job in self._jobs:
                if not job.get("enabled", True):
                    continue
                if now - float(job.get("last_run_at", 0.0)) < int(job.get("interval_s", 60)):
                    continue
                job["last_run_at"] = now
                self._persist()
                if self._dispatch:
                    await self._dispatch(job)
            await asyncio.sleep(5)

    def _persist(self):
        self._storage_path.write_text(json.dumps(self._jobs, indent=2), encoding="utf-8")
