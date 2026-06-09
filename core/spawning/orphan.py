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
from typing import Any

from core.session import SESSION_DIR
from core.spawning.manager import SubagentManager, subagent_manager

logger = logging.getLogger("jarvis.spawning.orphan")

from core.config_schema import jarvis_config


class OrphanRecovery:
    def __init__(self, manager: SubagentManager):
        self.manager = manager

    async def recover(self):
        """Called at startup. Finds runs with no active parent session."""
        logger.info("[OrphanRecovery] Scanning for orphaned subagent runs...")
        # Configurable grace period
        grace_period = getattr(jarvis_config.build, "orphan_grace_period_seconds", 300)
        orphans = await self.manager.store.list_orphans(grace_period_s=grace_period)
        if not orphans:
            logger.info("[OrphanRecovery] No orphans found.")
            return

        logger.info(f"[OrphanRecovery] Found {len(orphans)} potential orphans.")
        for orphan in orphans:
            try:
                await self._recover_one(orphan)
            except Exception as e:
                logger.error(f"Failed to recover orphan {orphan['run_id']}: {e}")

    async def _recover_one(self, run: dict[str, Any]):
        child_key = run["child_session_key"]
        run_id = run["run_id"]

        # Check if hierarchical session file exists
        safe_key = child_key.replace(':', '_')
        session_file = SESSION_DIR / f"hier_{safe_key}.json"

        if session_file.exists():
            logger.info(f"[OrphanRecovery] Resuming run {run_id} (session {child_key})")

            task = run["task"]
            agent_id = run["agent_id"]

            cancel_event = asyncio.Event()
            self.manager._cancel_events[run_id] = cancel_event
            task_obj = asyncio.create_task(
                self.manager._run_agent(run_id, child_key, agent_id, f"RESUME: {task}", cancel_event)
            )
            self.manager._tasks[run_id] = task_obj
        else:
            logger.info(f"[OrphanRecovery] Finalizing run {run_id} (session data lost at {session_file})")
            await self.manager.store.update_status(
                run_id, "failed",
                error=f"Session data lost during restart (expected {session_file.name})",
                outcome="error"
            )

orphan_recovery = OrphanRecovery(subagent_manager)
