from __future__ import annotations

import asyncio
import inspect

from core.scheduler.queue import SchedulerQueue


class SchedulerState:
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"


class _ExecutorRegistry:
    def __init__(self):
        self._items = {}

    def register(self, node_type, executor):
        self._items[node_type] = executor

    def get(self, node_type):
        return self._items.get(node_type)


class Scheduler:
    def __init__(self, manager, resume_engine, execute_fn=None, tick_interval=1.0, store_db_path="scheduler.db", **_kwargs):
        self.manager, self.resume_engine = manager, resume_engine
        self.execute_fn, self.tick_interval = execute_fn, tick_interval
        self.queue = SchedulerQueue(manager)
        self.registry = _ExecutorRegistry()
        self._max_workers = 3
        self._workers = set()
        self.state = SchedulerState.STOPPED
        self.is_running = False
        self.ticks = 0
        self._task = None
        self._callbacks = []

    @property
    def max_workers(self): return self._max_workers

    @max_workers.setter
    def max_workers(self, value):
        if not isinstance(value, int) or value < 1:
            raise ValueError("max_workers must be a positive integer")
        self._max_workers = value

    @property
    def running_count(self): return len(self._workers)

    @property
    def running_activities(self): return list(self._workers)

    def on_tick(self, callback): self._callbacks.append(callback)

    async def tick(self):
        if self.state == SchedulerState.PAUSED:
            return {"executed": False, "launched": [], "reason": "paused"}
        self.queue.refresh()
        candidates = self.queue.get_best_n(max(0, self.max_workers - self.running_count))
        if not candidates:
            self.ticks += 1
            return {"tick": self.ticks, "launched": [], "executed": False,
                    **({"reason": "all_workers_busy"} if self.running_count else {})}
        launched = []
        for activity in candidates:
            executor = self.registry.get(activity.node_type)
            if executor is None and self.execute_fn is None:
                self.queue.mark_failed(activity.activity_id)
                self.ticks += 1
                payload = {"tick": self.ticks, "error": f"no_executor_for_type:{activity.node_type}", "executed": False, "launched": []}
                for callback in list(self._callbacks): callback(payload)
                return payload
            self.queue.mark_running(activity.activity_id)
            async def worker(item=activity, fn=executor):
                try:
                    if fn is not None:
                        await fn(goal=item.goal, activity_id=item.activity_id)
                    elif self.execute_fn is not None:
                        result = self.execute_fn(item.activity_id, item.goal)
                        if inspect.isawaitable(result): await result
                    self.queue.mark_completed(item.activity_id)
                finally:
                    self._workers.discard(asyncio.current_task())
            task = asyncio.create_task(worker())
            self._workers.add(task)
            launched.append(activity.activity_id)
        self.ticks += 1
        payload = {"tick": self.ticks, "launched": launched, "executed": True}
        for callback in list(self._callbacks): callback(payload)
        return payload

    async def _loop(self):
        while self.is_running:
            await self.tick()
            await asyncio.sleep(self.tick_interval)

    async def start(self):
        self.state = SchedulerState.RUNNING
        self.is_running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self):
        self.is_running = False
        self.state = SchedulerState.STOPPED
        if self._task:
            await self._task
            self._task = None
        for task in list(self._workers): task.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

    async def pause(self): self.state = SchedulerState.PAUSED
    async def resume(self): self.state = SchedulerState.RUNNING
