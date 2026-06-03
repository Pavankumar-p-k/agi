from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

STORE_PATH = Path.home() / ".jarvis" / "cron_jobs.json"


class CronScheduler:
    """Simple cron scheduler for background jobs — matching OpenClaw's cron system."""

    def __init__(self):
        self._jobs: dict[str, dict] = {}
        self._task: asyncio.Task | None = None
        self._running = False
        self._load()

    # ── Persistence ──

    def _load(self):
        try:
            if STORE_PATH.exists():
                data = json.loads(STORE_PATH.read_text())
                self._jobs = {j["id"]: j for j in data}
                logger.info("[Cron] Loaded %d jobs", len(self._jobs))
        except Exception as e:
            logger.warning("[Cron] Load failed: %s", e)

    def _save(self):
        try:
            STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
            STORE_PATH.write_text(json.dumps(list(self._jobs.values()), indent=2))
        except Exception as e:
            logger.warning("[Cron] Save failed: %s", e)

    # ── Job Management ──

    def add_job(self, job_id: str, schedule: str, action: str,
                params: dict | None = None, enabled: bool = True) -> dict:
        job = {
            "id": job_id,
            "schedule": schedule,
            "action": action,
            "params": params or {},
            "enabled": enabled,
            "created": datetime.now().isoformat(),
            "last_run": None,
            "next_run": None,
        }
        self._jobs[job_id] = job
        self._save()
        logger.info("[Cron] Added job: %s (%s)", job_id, schedule)
        return job

    def remove_job(self, job_id: str) -> bool:
        if job_id in self._jobs:
            del self._jobs[job_id]
            self._save()
            logger.info("[Cron] Removed job: %s", job_id)
            return True
        return False

    def get_job(self, job_id: str) -> dict | None:
        return self._jobs.get(job_id)

    def list_jobs(self) -> list[dict]:
        return list(self._jobs.values())

    # ── Execution ──

    def _parse_interval(self, schedule: str) -> int | None:
        try:
            s = schedule.strip().lower()
            if s.endswith("s"):
                return int(s[:-1])
            if s.endswith("m"):
                return int(s[:-1]) * 60
            if s.endswith("h"):
                return int(s[:-1]) * 3600
            if s.endswith("d"):
                return int(s[:-1]) * 86400
            return int(s)
        except (ValueError, AttributeError) as e:
            logger.warning("[Cron] Invalid schedule '%s': %s", schedule, e)
            return None

    async def _execute_job(self, job: dict):
        action = job["action"]
        params = job.get("params", {})
        logger.info("[Cron] Running job %s: %s", job["id"], action)
        try:
            if action == "memory_consolidate":
                from memory.tiered_memory import TieredMemory
                tm = TieredMemory()
                tm.consolidate()
            elif action == "health_check":
                from core.health_monitor import HealthMonitor
                hm = HealthMonitor()
                await hm.check_all()
            elif action == "backup":
                from core.backup import BackupManager
                bm = BackupManager()
                await bm.create_backup()
            elif action == "daily_digest":
                from channels import channel_controller
                for c in channel_controller.running:
                    await c.send(params.get("target", "") or "", "Daily digest: All systems operational.")
            elif action == "webhook":
                url = params.get("url")
                if not url:
                    logger.warning("[Cron] Webhook job %s has no URL", job["id"])
                    return
                import httpx
                async with httpx.AsyncClient(timeout=30) as client:
                    await client.post(url, json=params.get("data", {}))
            elif action == "custom":
                logger.info("[Cron] Custom job %s: %s", job["id"], params)
            job["last_run"] = datetime.now().isoformat()
            self._save()
        except Exception as e:
            logger.exception("[Cron] Job %s failed: %s", job["id"], e)

    async def _loop(self):
        while self._running:
            now = datetime.now()
            for job in self._jobs.values():
                if not job.get("enabled", True):
                    continue
                interval = self._parse_interval(job.get("schedule", ""))
                if interval is None:
                    continue
                last_run = job.get("last_run")
                if last_run:
                    try:
                        last = datetime.fromisoformat(last_run)
                    except (ValueError, TypeError):
                        logger.warning("[Cron] Invalid last_run for job %s: %s", job.get("id"), last_run)
                        continue
                    elapsed = (now - last).total_seconds()
                    if elapsed < interval:
                        continue
                await self._execute_job(job)
            await asyncio.sleep(30)

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("[Cron] Scheduler started — %d job(s)", len(self._jobs))

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        logger.info("[Cron] Scheduler stopped")


cron_scheduler = CronScheduler()
