"""Tool implementations for the autonomous scheduler.

Each function is async and follows the standard tool pattern.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from core.scheduler.models import ScheduledActivity
from core.scheduler.queue import SchedulerQueue
from core.scheduler.scheduler import Scheduler
from core.scheduler.store import SchedulerStore

logger = logging.getLogger(__name__)

# Global scheduler instance — set by lifespan.py or CLI startup
_scheduler: Scheduler | None = None


def set_scheduler(sched: Scheduler) -> None:
    global _scheduler
    _scheduler = sched


def get_scheduler() -> Scheduler | None:
    return _scheduler


def _ensure_scheduler() -> Scheduler:
    if _scheduler is None:
        raise RuntimeError(
            "Scheduler not initialized. Start JARVIS with --scheduler or "
            "run `jarvis scheduler start` first."
        )
    return _scheduler


# ── Tool implementations ─────────────────────────────────────────


async def do_scheduler_start(tick_interval: float = 10.0) -> dict[str, Any]:
    """Start the autonomous scheduler background loop."""
    sched = _ensure_scheduler()
    if sched.is_running:
        return {"status": "already_running", "state": sched.state}
    await sched.start()
    return {"status": "started", "state": SchedulerStateName(sched.state)}


async def do_scheduler_stop() -> dict[str, Any]:
    """Stop the scheduler background loop."""
    sched = _ensure_scheduler()
    await sched.stop()
    return {"status": "stopped"}


async def do_scheduler_pause() -> dict[str, Any]:
    """Pause the scheduler (stops ticking but keeps state)."""
    sched = _ensure_scheduler()
    await sched.pause()
    return {"status": "paused", "state": SchedulerStateName(sched.state)}


async def do_scheduler_resume() -> dict[str, Any]:
    """Resume a paused scheduler."""
    sched = _ensure_scheduler()
    await sched.resume()
    return {"status": "resumed", "state": SchedulerStateName(sched.state)}


async def do_scheduler_submit(
    goal: str,
    priority: int = 0,
    activity_id: str | None = None,
    node_type: str = "goal",
    depends_on: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Submit a new activity to the scheduler queue."""
    sched = _ensure_scheduler()
    import uuid
    aid = activity_id or f"sched_{uuid.uuid4().hex[:12]}"
    act = sched.queue.submit(
        activity_id=aid,
        goal=goal,
        priority=priority,
        node_type=node_type,
        depends_on=depends_on,
        metadata=metadata,
    )
    return {
        "activity_id": act.activity_id,
        "goal": act.goal,
        "priority": act.priority,
        "status": act.status,
    }


async def do_scheduler_list(
    status_filter: str | None = None,
) -> dict[str, Any]:
    """List all activities in the scheduler queue."""
    sched = _ensure_scheduler()
    if status_filter:
        activities = [a for a in sched.queue.all if a.status == status_filter]
    else:
        activities = sched.queue.all
    return {
        "total": len(activities),
        "ready": len(sched.queue.ready),
        "blocked": len(sched.queue.blocked),
        "activities": [_serialize(a) for a in activities],
        "current": _serialize(sched.current_activity) if sched.current_activity else None,
    }


async def do_scheduler_status(activity_id: str) -> dict[str, Any]:
    """Get status of a specific activity."""
    sched = _ensure_scheduler()
    for a in sched.queue.all:
        if a.activity_id == activity_id:
            return _serialize(a)
    return {"error": f"Activity {activity_id} not found", "activity_id": activity_id}


async def do_scheduler_cancel(activity_id: str) -> dict[str, Any]:
    """Cancel a pending or blocked activity."""
    sched = _ensure_scheduler()
    cancelled = sched.queue.cancel(activity_id)
    return {
        "activity_id": activity_id,
        "cancelled": cancelled,
    }


async def do_scheduler_set_priority(activity_id: str, priority: int) -> dict[str, Any]:
    """Change the priority of a queued activity."""
    sched = _ensure_scheduler()
    updated = sched.queue.set_priority(activity_id, priority)
    return {
        "activity_id": activity_id,
        "priority": priority,
        "updated": updated,
    }


async def do_scheduler_tick() -> dict[str, Any]:
    """Force a single scheduler tick (for testing or manual use)."""
    sched = _ensure_scheduler()
    result = await sched.tick()
    result["state"] = SchedulerStateName(sched.state)
    return result


# ── Helpers ──────────────────────────────────────────────────────


def _serialize(a: ScheduledActivity) -> dict[str, Any]:
    return {
        "activity_id": a.activity_id,
        "priority": a.priority,
        "score": a.score,
        "status": a.status,
        "goal": a.goal,
        "node_type": a.node_type,
        "depends_on": a.depends_on,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "metadata": a.metadata,
    }


def SchedulerStateName(state: str) -> str:
    m = {"stopped": "stopped", "running": "running", "paused": "paused"}
    return m.get(state, state)


# ── Chain tools ─────────────────────────────────────────────────────


async def do_scheduler_chain_submit(
    name: str,
    steps: list[list[str]],
    priority: int = 0,
) -> dict[str, Any]:
    """Submit a chain of dependent activities.

    Steps is a list of [goal, node_type] pairs in execution order.
    Each activity depends on the previous. Returns the chain details.
    """
    from core.scheduler.chain import ChainManager
    mgr = ChainManager()
    typed_steps: list[tuple[str, str]] = [(s[0], s[1]) for s in steps]
    chain = mgr.create_chain(name, typed_steps, priority=priority)
    return {
        "chain_id": chain.chain_id,
        "name": chain.name,
        "status": chain.status,
        "progress": chain.progress,
        "activities": [_serialize(a) for a in chain.activities],
    }


async def do_scheduler_chain_list() -> dict[str, Any]:
    """List all activity chains."""
    from core.scheduler.chain import ChainManager
    mgr = ChainManager()
    chains = mgr.list_chains()
    return {
        "chains": [
            {
                "chain_id": c.chain_id,
                "name": c.name,
                "status": c.status,
                "progress": c.progress,
                "step_count": len(c.activities),
            }
            for c in chains
        ],
    }


async def do_scheduler_chain_status(chain_id: str) -> dict[str, Any]:
    """Get detailed status of a specific chain."""
    from core.scheduler.chain import ChainManager
    mgr = ChainManager()
    chain = mgr.get_chain(chain_id)
    if not chain:
        return {"error": f"Chain {chain_id} not found"}
    return {
        "chain_id": chain.chain_id,
        "name": chain.name,
        "status": chain.status,
        "progress": chain.progress,
        "current_step": chain.current_step,
        "is_complete": chain.is_complete,
        "activities": [_serialize(a) for a in chain.activities],
    }


async def do_scheduler_chain_cancel(chain_id: str) -> dict[str, Any]:
    """Cancel all pending/blocked activities in a chain."""
    from core.scheduler.chain import ChainManager
    mgr = ChainManager()
    found = mgr.delete_chain(chain_id)
    return {"chain_id": chain_id, "cancelled": found}
