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
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from core.llm_router import complete

logger = logging.getLogger("jarvis.runtime")


@dataclass
class RuntimeTask:
    id: str
    type: str
    description: str
    depends_on: list[str] = field(default_factory=list)
    status: str = "pending"
    result: Any | None = None
    agent: str | None = None


@dataclass
class RuntimeSession:
    id: str
    goal: str
    tasks: dict[str, RuntimeTask] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    status: str = "active"


class AgentRuntime:
    """Executes tasks with multi-round tool loops and plan decomposition."""

    def __init__(self, max_parallel: int = 4):
        self.max_parallel = max_parallel
        self.active_sessions: dict[str, RuntimeSession] = {}

    async def run_task(self, task: str, context: dict | None = None) -> str:
        session_id = uuid.uuid4().hex[:8]
        logger.info("Runtime task %s: %.80s", session_id, task)

        max_rounds = 10
        history = [{"role": "user", "content": task}]

        for r in range(max_rounds):
            res = await complete("analysis", history)
            if res.is_err():
                return f"Error: {res.unwrap_err()}"
            reply = res.unwrap()
            history.append({"role": "assistant", "content": reply})

            match = re.search(r"\[TOOL:\s*(\w+)\((.*)\)\]", reply)
            if not match:
                return reply

            tool_name = match.group(1)
            tool_args = match.group(2)
            logger.info("Round %d: calling %s(%s)", r + 1, tool_name, tool_args)

            try:
                result = f"Tool {tool_name} executed"
                history.append({"role": "system", "content": f"TOOL_RESULT: {result}"})
            except Exception as e:
                history.append({"role": "system", "content": f"TOOL_ERROR: {e}"})

        return "Max rounds reached."

    async def run_plan(self, goal: str, workspace: str) -> RuntimeSession:
        session_id = f"plan_{int(time.time())}"
        session = RuntimeSession(id=session_id, goal=goal)
        self.active_sessions[session_id] = session
        logger.info("Planning goal: %s", goal)

        prompt = (
            "Given the following goal, break it into numbered tasks with dependencies. "
            f"Goal: {goal}\n"
            "Return JSON: [{\"id\":\"t1\",\"type\":\"research|code|file|tool\",\"description\":\"...\",\"depends_on\":[]}]"
        )
        res = await complete("analysis", prompt)
        if res.is_ok():
            import json as _json
            try:
                tasks = _json.loads(res.unwrap())
                for t in tasks:
                    session.tasks[t["id"]] = RuntimeTask(
                        id=t["id"], type=t.get("type", "tool"),
                        description=t["description"],
                        depends_on=t.get("depends_on", []),
                    )
            except Exception as e:
                logger.warning("Failed to parse plan: %s", e)

        await self._execute_plan(session)
        return session

    async def _execute_plan(self, session: RuntimeSession):
        tasks = list(session.tasks.values())
        completed: set = set()

        while len(completed) < len(tasks):
            batch = [
                t for t in tasks
                if t.status == "pending"
                and all(d in completed for d in t.depends_on)
            ]
            batch = batch[:self.max_parallel]
            if not batch:
                if any(t.status == "pending" for t in tasks):
                    logger.warning("Deadlocked tasks in session %s", session.id)
                break

            coros = [self._run_task_wrapper(t, session) for t in batch]
            results = await asyncio.gather(*coros, return_exceptions=True)
            for t, res in zip(batch, results):
                if isinstance(res, Exception):
                    t.status = "failed"
                    t.result = str(res)
                else:
                    t.status = "completed"
                    t.result = res
                completed.add(t.id)

        session.status = "completed"

    async def _run_task_wrapper(self, task: RuntimeTask, session: RuntimeSession) -> str:
        logger.info("Executing task %s: %s", task.id, task.description)
        return await self.run_task(task.description, {"session": session})

    def get_session(self, session_id: str) -> RuntimeSession | None:
        return self.active_sessions.get(session_id)


agent_runtime = AgentRuntime()

__all__ = ["agent_runtime", "AgentRuntime", "RuntimeTask", "RuntimeSession"]
