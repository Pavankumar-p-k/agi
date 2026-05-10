"""Mobile device discovery and local sync metadata."""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


class MobileSyncService:
    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self._storage_path = Path(self.config.get("storage_path", "data/jarvis_mobile_sync.json"))
        self._state: Dict[str, Any] = {"linked_devices": [], "sync_jobs": [], "last_scan_at": 0.0}

    async def initialize(self):
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        if self._storage_path.exists():
            try:
                self._state = json.loads(self._storage_path.read_text(encoding="utf-8"))
            except Exception as err:
                import logging
                logging.getLogger(__name__).error("Exception swallowed: %s", err)
                raise RuntimeError(f"Exception swallowed: {err}")
        self.scan_devices()

    async def shutdown(self):
        self._persist()

    def scan_devices(self) -> List[Dict[str, Any]]:
        devices: List[Dict[str, Any]] = []
        if shutil.which("adb"):
            try:
                completed = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=10)
                for line in completed.stdout.splitlines()[1:]:
                    line = line.strip()
                    if not line or "\t" not in line:
                        continue
                    serial, status = line.split("\t", 1)
                    devices.append({"serial": serial, "status": status, "platform": "android"})
            except Exception as err:
                import logging
                logging.getLogger(__name__).error("Exception swallowed: %s", err)
                raise RuntimeError(f"Exception swallowed: {err}")
        self._state["linked_devices"] = devices
        self._state["last_scan_at"] = time.time()
        self._persist()
        return devices

    def queue_sync(self, target: str, scope: str = "messages") -> Dict[str, Any]:
        job = {
            "job_id": f"sync_{int(time.time() * 1000)}",
            "target": target,
            "scope": scope,
            "status": "queued",
            "created_at": time.time(),
        }
        self._state.setdefault("sync_jobs", []).append(job)
        self._state["sync_jobs"] = self._state["sync_jobs"][-100:]
        self._persist()
        return job

    def status(self) -> Dict[str, Any]:
        return {
            "adb_available": bool(shutil.which("adb")),
            "linked_devices": list(self._state.get("linked_devices", [])),
            "sync_jobs": self._state.get("sync_jobs", [])[-20:],
            "last_scan_at": self._state.get("last_scan_at", 0.0),
        }

    def _persist(self):
        self._storage_path.write_text(json.dumps(self._state, indent=2), encoding="utf-8")
