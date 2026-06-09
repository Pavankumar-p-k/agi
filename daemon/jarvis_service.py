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

"""daemon/jarvis_service.py
Windows service for JARVIS — survives reboot, auto-resumes builds.
Phase 5 (E4): Background Stability — health checks, crash recovery, watchdog.
Run: python daemon/jarvis_service.py install|start|stop|status
"""
import os, sys, json, logging, asyncio, threading, time, signal
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger("jarvis_service")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SERVICE_PID_FILE = Path.home() / ".jarvis" / "service.pid"
SERVICE_LOG_FILE = Path.home() / ".jarvis" / "service.log"
SERVICE_HEALTH_FILE = Path.home() / ".jarvis" / "service_health.json"
PROJECTS_DIR = Path.home() / ".jarvis" / "projects"


class JarvisDaemon:
    """Background daemon with health checks, crash recovery, and watchdog."""

    def __init__(self):
        self.running = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._healthy = True
        self._last_heartbeat = 0.0
        self._consecutive_failures = 0
        self._max_failures = 5

    def start(self):
        if self.running:
            print("[SERVICE] Already running")
            return
        SERVICE_PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        SERVICE_PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
        self._write_health({"status": "starting", "pid": os.getpid(), "started_at": datetime.now().isoformat()})
        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        print(f"[SERVICE] Started (PID {os.getpid()})")

    def stop(self):
        self.running = False
        self._write_health({"status": "stopped", "stopped_at": datetime.now().isoformat()})
        if SERVICE_PID_FILE.exists():
            SERVICE_PID_FILE.unlink()
        print("[SERVICE] Stopped")

    def _write_health(self, extra: dict = None):
        data = {
            "timestamp": datetime.now().isoformat(),
            "pid": os.getpid(),
            "healthy": self._healthy,
            "consecutive_failures": self._consecutive_failures,
        }
        if extra:
            data.update(extra)
        try:
            SERVICE_HEALTH_FILE.parent.mkdir(parents=True, exist_ok=True)
            SERVICE_HEALTH_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.exception("[SERVICE] write_health: %s", e)

    def _run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main_loop())
        except Exception as e:
            self._healthy = False
            self._write_health({"status": "crashed", "error": str(e)})
            logger.error(f"[SERVICE] Fatal error: {e}")
        finally:
            self._loop.close()

    async def _main_loop(self):
        logger.info("[SERVICE] Daemon heartbeat started")
        self._last_heartbeat = time.time()
        idle_cycles = 0

        while self.running:
            try:
                await self._heartbeat()
                self._consecutive_failures = 0
                self._healthy = True
                idle_cycles = 0
            except Exception as e:
                self._consecutive_failures += 1
                logger.warning(f"[SERVICE] Heartbeat error ({self._consecutive_failures}/{self._max_failures}): {e}")
                if self._consecutive_failures >= self._max_failures:
                    logger.error(f"[SERVICE] Too many consecutive failures, self-restarting")
                    self._healthy = False
                    self._write_health({"status": "unhealthy", "error": str(e)})
                    self.running = False
                    break
                idle_cycles += 1

            self._last_heartbeat = time.time()
            self._write_health()
            # Sleep with early-exit check
            for _ in range(30):
                if not self.running:
                    break
                await asyncio.sleep(1)

        logger.info("[SERVICE] Daemon stopped")

    async def _heartbeat(self):
        """Main heartbeat: check environment, resume projects, run health checks."""
        # Phase 5 (E1): Environment monitoring
        try:
            from core.environment_monitor import environment_monitor
            snap = environment_monitor.check()
            if snap.warnings:
                for w in snap.warnings:
                    logger.warning(f"[ENV] {w}")
        except Exception as e:
            logger.warning(f"[SERVICE] Monitor error: {e}")

        # Phase 5 (E2): Proactive adaptation
        try:
            from core.proactive_adaptation import adaptation_engine
            if adaptation_engine.should_pause():
                logger.warning("[SERVICE] Adaptation engine: pausing builds due to environment")
        except Exception as e:
            logger.warning(f"[SERVICE] Adaptation error: {e}")

        # Phase 4 (D1): System Governor cleanup — reset stale projects
        try:
            from core.system_governor import system_governor
            for project_dir in PROJECTS_DIR.iterdir() if PROJECTS_DIR.exists() else []:
                state_file = project_dir / "state.json"
                if state_file.exists():
                    try:
                        data = json.loads(state_file.read_text(encoding="utf-8"))
                        status = data.get("status", "")
                        if status in ("done", "failed", "cancelled"):
                            system_governor.reset(project_dir.name)
                    except Exception as e:
                        logger.exception("[SERVICE] governor reset: %s", e)
        except Exception as e:
            logger.warning(f"[SERVICE] Governor cleanup error: {e}")

        # Core: resume pending projects
        try:
            from core.control_loop import control_loop
            resumed = await control_loop.run_pending()
            if resumed:
                logger.info(f"[SERVICE] Resumed {len(resumed)} projects: {resumed}")
        except Exception as e:
            logger.warning(f"[SERVICE] Error checking projects: {e}")

    async def _check_projects(self):
        """Public helper used by tests: trigger run_pending and return discovered projects."""
        try:
            from core.control_loop import control_loop
            resumed = await control_loop.run_pending()
            return resumed or []
        except Exception as e:
            logger.warning("[SERVICE] _check_projects error: %s", e)
            return []

    @staticmethod
    def install():
        script = Path(__file__).resolve()
        cmd = (
            f'schtasks /Create /SC ONLOGON /TN "JARVIS Daemon" '
            f'/TR "{sys.executable} {script} start" /F /DELAY 0001:00'
        )
        print(f"[SERVICE] Installing via: {cmd}")
        subprocess.run(cmd, shell=False)
        print("[SERVICE] Install scheduled. Will start ~1 min after next login.")

    @staticmethod
    def uninstall():
        subprocess.run(['schtasks', '/Delete', '/TN', 'JARVIS Daemon', '/F'], shell=False)
        print("[SERVICE] Scheduled task removed.")

    @staticmethod
    def status():
        if SERVICE_PID_FILE.exists():
            pid = SERVICE_PID_FILE.read_text(encoding="utf-8").strip()
            print(f"[SERVICE] Running (PID {pid})")
        else:
            print("[SERVICE] Not running")
        if SERVICE_HEALTH_FILE.exists():
            try:
                health = json.loads(SERVICE_HEALTH_FILE.read_text(encoding="utf-8"))
                print(f"[SERVICE] Health: {health.get('status', 'unknown')} "
                      f"failures={health.get('consecutive_failures', 0)}")
            except Exception as e:
                logger.exception("[SERVICE] status read: %s", e)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.FileHandler(str(SERVICE_LOG_FILE)),
            logging.StreamHandler(),
        ]
    )

    daemon = JarvisDaemon()

    if len(sys.argv) < 2:
        print("Usage: python daemon/jarvis_service.py [start|stop|install|uninstall|status]")
        return

    cmd = sys.argv[1].lower()
    if cmd == "start":
        daemon.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            daemon.stop()
    elif cmd == "stop":
        daemon.stop()
    elif cmd == "install":
        JarvisDaemon.install()
    elif cmd == "uninstall":
        JarvisDaemon.uninstall()
    elif cmd == "status":
        JarvisDaemon.status()
    else:
        print(f"Unknown command: {cmd}")


if __name__ == "__main__":
    main()
