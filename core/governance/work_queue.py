"""core/governance/work_queue.py
WorkQueue — asyncio priority queue with disk persistence.

Priority:   1 = urgent   5 = normal   10 = background
Persistence: ~/.jarvis/queue.json  (survives FastAPI restarts)

Respects ResourceMonitor.should_throttle() — pauses when system is stressed.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── paths ─────────────────────────────────────────────────────────────────────

QUEUE_FILE = Path.home() / ".jarvis" / "queue.json"
QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)


# ── enums / data classes ──────────────────────────────────────────────────────

class TaskStatus(str, Enum):
    PENDING  = "pending"
    RUNNING  = "running"
    DONE     = "done"
    FAILED   = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskRecord:
    task_id:    str
    task:       str
    priority:   int
    context:    dict
    status:     TaskStatus = TaskStatus.PENDING
    created_at: float      = field(default_factory=time.time)
    started_at: float | None = None
    done_at:    float | None = None
    result:     Any          = None
    error:      str | None   = None

    # ── compare by priority then creation time (for heap) ──────────────────
    def __lt__(self, other: "TaskRecord") -> bool:
        if self.priority != other.priority:
            return self.priority < other.priority  # lower number = higher urgency
        return self.created_at < other.created_at

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "TaskRecord":
        d = dict(d)
        d["status"] = TaskStatus(d.get("status", "pending"))
        return cls(**d)


# ── main class ────────────────────────────────────────────────────────────────

class WorkQueue:
    """Asyncio-based priority work queue with disk persistence.

    Usage::
        wq = WorkQueue()
        wq.start()                     # starts background loop
        tid = await wq.enqueue("summarise my emails", priority=3)
        await asyncio.sleep(2)
        rec = wq.get_task(tid)
    """

    def __init__(self, resource_monitor=None, task_router=None):
        from core.governance.resource_monitor import resource_monitor as _rm
        from core.governance.task_router     import task_router     as _tr
        self._rm      = resource_monitor or _rm
        self._router  = task_router      or _tr

        self._queue: asyncio.PriorityQueue[tuple[int, float, TaskRecord]] = \
            asyncio.PriorityQueue()
        self._records: dict[str, TaskRecord] = {}
        self._running_count  = 0
        self._loop_task: asyncio.Task | None = None
        self._shutdown       = False

        self._load_pending()

    # ── public API ────────────────────────────────────────────────────────────

    async def enqueue(
        self,
        task: str,
        priority: int = 5,
        context: dict | None = None,
    ) -> str:
        """Add a task to the queue. Returns the task_id."""
        if self._rm.should_reject():
            raise RuntimeError(
                "System critically overloaded — task rejected. "
                "Check CPU/RAM usage before submitting."
            )

        priority = max(1, min(10, priority))
        task_id  = str(uuid.uuid4())
        record   = TaskRecord(
            task_id  = task_id,
            task     = task,
            priority = priority,
            context  = context or {},
        )
        self._records[task_id] = record
        # asyncio.PriorityQueue uses tuple comparison: (priority, tie-breaker, item)
        await self._queue.put((priority, record.created_at, record))
        self._persist()
        logger.info("[WorkQueue] Enqueued task %s (p=%d): %.60s…", task_id, priority, task)
        return task_id

    def start(self) -> asyncio.Task:
        """Start the background process loop (call once at app startup)."""
        if self._loop_task is None or self._loop_task.done():
            self._shutdown = False
            self._loop_task = asyncio.ensure_future(self.process_loop())
        return self._loop_task

    async def stop(self) -> None:
        """Gracefully stop the process loop."""
        self._shutdown = True
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass

    async def process_loop(self) -> None:
        """Background coroutine — dequeues and dispatches tasks."""
        logger.info("[WorkQueue] Process loop started.")
        while not self._shutdown:
            # Respect throttle
            if self._rm.should_throttle():
                logger.warning("[WorkQueue] Throttling — sleeping 5s.")
                await asyncio.sleep(5)
                continue

            concurrency = self._rm.recommend_concurrency()
            if self._running_count >= concurrency:
                await asyncio.sleep(0.5)
                continue

            try:
                _prio, _ts, record = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                await asyncio.sleep(0.5)
                continue

            if record.status == TaskStatus.CANCELLED:
                self._queue.task_done()
                continue

            # Dispatch
            asyncio.ensure_future(self._execute(record))

        logger.info("[WorkQueue] Process loop stopped.")

    def get_status(self) -> dict:
        pending  = sum(1 for r in self._records.values() if r.status == TaskStatus.PENDING)
        running  = sum(1 for r in self._records.values() if r.status == TaskStatus.RUNNING)
        done     = sum(1 for r in self._records.values() if r.status == TaskStatus.DONE)
        failed   = sum(1 for r in self._records.values() if r.status == TaskStatus.FAILED)
        return {
            "pending":  pending,
            "running":  running,
            "done":     done,
            "failed":   failed,
            "total":    len(self._records),
        }

    def get_task(self, task_id: str) -> TaskRecord | None:
        return self._records.get(task_id)

    def list_tasks(self) -> list[dict]:
        return [r.to_dict() for r in sorted(self._records.values(), key=lambda r: r.created_at, reverse=True)]

    def cancel(self, task_id: str) -> bool:
        record = self._records.get(task_id)
        if record is None:
            return False
        if record.status not in (TaskStatus.PENDING, TaskStatus.RUNNING):
            return False
        record.status = TaskStatus.CANCELLED
        self._persist()
        logger.info("[WorkQueue] Cancelled task %s", task_id)
        return True

    # ── internal ──────────────────────────────────────────────────────────────

    async def _execute(self, record: TaskRecord) -> None:
        self._running_count += 1
        record.status     = TaskStatus.RUNNING
        record.started_at = time.time()
        self._persist()

        try:
            # Route the task
            decision = await self._router.route(record.task, record.context)

            # Dispatch based on decision
            result = await self._dispatch(record.task, record.context, decision)

            record.status  = TaskStatus.DONE
            record.result  = result
            logger.info("[WorkQueue] Task %s DONE in %.1fs",
                        record.task_id, time.time() - record.started_at)

        except Exception as exc:
            record.status = TaskStatus.FAILED
            record.error  = str(exc)
            logger.error("[WorkQueue] Task %s FAILED: %s", record.task_id, exc)

        finally:
            record.done_at = time.time()
            self._running_count = max(0, self._running_count - 1)
            self._queue.task_done()
            self._persist()

    async def _dispatch(self, task: str, context: dict, decision) -> Any:
        """Dispatch to the correct handler based on RouteDecision."""
        # If confidence is too low, ask for clarification (raise so caller handles it)
        if decision.needs_clarification():
            raise ValueError(
                f"Task routing confidence too low ({decision.confidence:.2f}). "
                f"Please clarify: '{task}'"
            )

        if decision.handler == "llm_direct":
            return await self._llm_direct(task, context)

        if decision.handler == "skill":
            return await self._run_skill(decision.target, task, context)

        if decision.handler == "sub_agent":
            return await self._run_sub_agent(decision.target, task, context)

        if decision.handler == "tool":
            return await self._run_tool(decision.target, task, context)

        return {"note": f"Unhandled handler type '{decision.handler}'"}

    async def _llm_direct(self, task: str, context: dict) -> dict:
        try:
            from core.llm_router import complete  # type: ignore
            result = await complete("chat", [{"role": "user", "content": task}])
            answer = result.unwrap_or("") if hasattr(result, "unwrap_or") else str(result)
            return {"response": answer, "handler": "llm_direct"}
        except Exception as exc:
            logger.debug("[WorkQueue] llm_direct fallback: %s", exc)
            return {"response": f"(offline) Task noted: {task}", "handler": "llm_direct"}

    async def _run_skill(self, skill_id: str, task: str, context: dict) -> dict:
        try:
            from skills.registry import get_skill  # type: ignore
            skill_fn = get_skill(skill_id)
            result   = await skill_fn({"task": task, **context})
            return result
        except Exception as exc:
            logger.debug("[WorkQueue] skill '%s' error: %s", skill_id, exc)
            return {"status": "error", "skill": skill_id, "error": str(exc)}

    async def _run_sub_agent(self, agent_role: str, task: str, context: dict) -> dict:
        try:
            from core.agent_registry import get_agent  # type: ignore
            agent  = get_agent(agent_role)
            result = await agent.execute(task, context)
            return result
        except Exception as exc:
            logger.debug("[WorkQueue] sub_agent '%s' error: %s", agent_role, exc)
            return {"status": "error", "agent": agent_role, "task": task, "error": str(exc)}

    async def _run_tool(self, tool_name: str, task: str, context: dict) -> dict:
        try:
            from ai_os.tool_registry import get_default_tool_registry  # type: ignore
            reg    = get_default_tool_registry()
            result = reg.execute({"tool": tool_name, "args": {"task": task, **context}})
            return result
        except Exception as exc:
            logger.debug("[WorkQueue] tool '%s' error: %s", tool_name, exc)
            return {"status": "error", "tool": tool_name, "error": str(exc)}

    # ── persistence ───────────────────────────────────────────────────────────

    def _persist(self) -> None:
        """Write pending+running tasks to disk (skip done/failed/cancelled)."""
        try:
            to_save = [
                r.to_dict()
                for r in self._records.values()
                if r.status in (TaskStatus.PENDING, TaskStatus.RUNNING)
            ]
            QUEUE_FILE.write_text(json.dumps(to_save, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning("[WorkQueue] Persist failed: %s", exc)

    def _load_pending(self) -> None:
        """Restore pending tasks from disk on startup."""
        if not QUEUE_FILE.exists():
            return
        try:
            data = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
            loaded = 0
            for d in data:
                # Reset RUNNING→PENDING (were interrupted by a previous crash)
                if d.get("status") == TaskStatus.RUNNING.value:
                    d["status"] = TaskStatus.PENDING.value
                    d["started_at"] = None
                record = TaskRecord.from_dict(d)
                self._records[record.task_id] = record
                if record.status == TaskStatus.PENDING:
                    # Re-enqueue synchronously (queue not yet started)
                    # Use put_nowait; queue size is unlimited by default
                    self._queue.put_nowait((record.priority, record.created_at, record))
                    loaded += 1
            if loaded:
                logger.info("[WorkQueue] Restored %d pending tasks from disk.", loaded)
        except Exception as exc:
            logger.warning("[WorkQueue] Could not restore queue: %s", exc)


# ── singleton ─────────────────────────────────────────────────────────────────

work_queue = WorkQueue()
