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

import logging
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select, update

from core.database import AsyncSessionLocal, SubagentRun

logger = logging.getLogger("jarvis.spawning.store")

class SubagentStore:
    async def create_run(self, run_id: str, agent_id: str, parent_session_key: str | None,
                         child_session_key: str, task: str, depth: int, cleanup: str = "delete") -> dict:
        async with AsyncSessionLocal() as session:
            run = SubagentRun(
                run_id=run_id,
                agent_id=agent_id,
                parent_session_key=parent_session_key,
                child_session_key=child_session_key,
                task=task,
                depth=depth,
                cleanup=cleanup,
                status="pending",
                created_at=datetime.utcnow()
            )
            session.add(run)
            await session.commit()
            await session.refresh(run)
            return self._to_dict(run)

    async def get_run(self, run_id: str) -> dict | None:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(SubagentRun).where(SubagentRun.run_id == run_id))
            run = result.scalar_one_or_none()
            return self._to_dict(run) if run else None

    async def get_run_by_child_key(self, child_key: str) -> dict | None:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(SubagentRun).where(SubagentRun.child_session_key == child_key))
            run = result.scalar_one_or_none()
            return self._to_dict(run) if run else None

    async def update_status(self, run_id: str, status: str, **extra):
        async with AsyncSessionLocal() as session:
            stmt = update(SubagentRun).where(SubagentRun.run_id == run_id).values(status=status, **extra)
            await session.execute(stmt)
            await session.commit()

    async def list_active(self) -> list[dict]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(SubagentRun).where(SubagentRun.status.in_(["pending", "running"])))
            runs = result.scalars().all()
            return [self._to_dict(r) for r in runs]

    async def list_by_parent(self, parent_key: str) -> list[dict]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(SubagentRun).where(SubagentRun.parent_session_key == parent_key))
            runs = result.scalars().all()
            return [self._to_dict(r) for r in runs]

    async def count_active_by_parent(self, parent_key: str) -> int:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(func.count())
                .select_from(SubagentRun)
                .where(SubagentRun.parent_session_key == parent_key)
                .where(SubagentRun.status.in_(["pending", "running"]))
            )
            return result.scalar() or 0

    async def list_orphans(self, grace_period_s: int = 300) -> list[dict]:
        """Runs that are stuck in 'running' or 'pending' for too long."""
        cutoff = datetime.utcnow() - timedelta(seconds=grace_period_s)
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(SubagentRun)
                .where(SubagentRun.status.in_(["pending", "running"]))
                .where(SubagentRun.created_at < cutoff)
            )
            runs = result.scalars().all()
            return [self._to_dict(r) for r in runs]

    async def delete_run(self, run_id: str):
        async with AsyncSessionLocal() as session:
            await session.execute(delete(SubagentRun).where(SubagentRun.run_id == run_id))
            await session.commit()

    def _to_dict(self, run: SubagentRun) -> dict:
        return {
            "run_id": run.run_id,
            "agent_id": run.agent_id,
            "parent_session_key": run.parent_session_key,
            "child_session_key": run.child_session_key,
            "task": run.task,
            "status": run.status,
            "depth": run.depth,
            "created_at": run.created_at.isoformat(),
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "ended_at": run.ended_at.isoformat() if run.ended_at else None,
            "result_text": run.result_text,
            "error": run.error,
            "outcome": run.outcome,
            "cleanup": run.cleanup,
            "meta": run.meta,
        }
