from __future__ import annotations
import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Literal, Optional

from core.session import session_manager, HierarchicalSession
from core.spawning.store import SubagentStore
from core.sub_agents.registry import agent_registry
from core.sub_agents.base_agent import AgentResult

logger = logging.getLogger("jarvis.spawning.manager")

@dataclass
class SpawnResult:
    accepted: bool
    run_id: str = ""
    child_session_key: str = ""
    depth: int = 0
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "accepted": self.accepted,
            "run_id": self.run_id,
            "child_session_key": self.child_session_key,
            "depth": self.depth,
            "error": self.error
        }

from core.config_schema import jarvis_config

class SubagentManager:
    def __init__(self, max_depth: Optional[int] = None, max_children: Optional[int] = None):
        self.store = SubagentStore()
        self.max_depth = max_depth or getattr(jarvis_config.build, "max_spawn_depth", 5)
        self.max_children = max_children or getattr(jarvis_config.build, "max_child_agents", 10)
        self._tasks: Dict[str, asyncio.Task] = {}
        self._cancel_events: Dict[str, asyncio.Event] = {}

    async def spawn(
        self,
        agent_id: str,
        task: str,
        parent_session_key: str | None = None,
        context_mode: Literal["isolated", "fork"] = "isolated",
        cleanup: Literal["keep", "delete"] = "delete",
    ) -> SpawnResult:
        try:
            # 1. Resolve parent
            if not parent_session_key:
                parent_session_key = "root:default"
            
            parent = session_manager.get_session(parent_session_key)
            if not parent:
                parent = session_manager.create_session(parent_session_key)

            # 2. Depth check
            depth = parent.data.get("spawn_depth", 0) + 1
            if depth >= self.max_depth:
                return SpawnResult(False, error=f"Max spawn depth reached ({self.max_depth})")

            # 3. Child count check
            active_children = await self.store.count_active_by_parent(parent_session_key)
            if active_children >= self.max_children:
                return SpawnResult(False, error=f"Max child agents reached for this session ({self.max_children})")

            # 4. Generate child key
            u_id = uuid.uuid4().hex[:8]
            child_key = f"agent:{agent_id.lower()}:spawn:{u_id}"
            run_id = f"run_{u_id}"

            # 5. Fork/create child session
            if context_mode == "fork":
                session_manager.fork_session(child_key, parent_session_key)
            else:
                session_manager.create_session(child_key, parent_id=parent_session_key)

            # 6. Register run
            await self.store.create_run(run_id, agent_id, parent_session_key, child_key, task, depth, cleanup)

            # 7. Launch agent
            cancel_event = asyncio.Event()
            self._cancel_events[run_id] = cancel_event
            task_obj = asyncio.create_task(self._run_agent(run_id, child_key, agent_id, task, cancel_event))
            self._tasks[run_id] = task_obj

            return SpawnResult(True, run_id=run_id, child_session_key=child_key, depth=depth)

        except Exception as e:
            logger.exception("Failed to spawn subagent")
            return SpawnResult(False, error=str(e))

    async def _run_agent(self, run_id: str, child_key: str, agent_id: str, task: str, cancel_event: asyncio.Event):
        try:
            # 1. Mark as running
            await self.store.update_status(run_id, "running", started_at=datetime.utcnow())
            
            # 2. Lookup agent
            agent_cls = agent_registry.get(agent_id)
            if not agent_cls:
                raise ValueError(f"Unknown agent: {agent_id}")
            
            agent = agent_cls()
            
            # 3. Call agent.run
            result: AgentResult = await agent.run(task, cancel_event=cancel_event, _session_key=child_key)

            # 4. Success / Failure
            if result.success:
                await self.store.update_status(
                    run_id, "completed", 
                    ended_at=datetime.utcnow(), 
                    result_text=result.output,
                    outcome="ok"
                )
            else:
                await self.store.update_status(
                    run_id, "failed", 
                    ended_at=datetime.utcnow(), 
                    error=result.error,
                    outcome="error"
                )

        except asyncio.CancelledError:
            await self.store.update_status(run_id, "killed", ended_at=datetime.utcnow(), outcome="killed")
            raise
        except Exception as e:
            logger.exception(f"Error in subagent run {run_id}")
            await self.store.update_status(run_id, "failed", ended_at=datetime.utcnow(), error=str(e), outcome="error")
        finally:
            self._tasks.pop(run_id, None)
            self._cancel_events.pop(run_id, None)
            
            # Cleanup session if requested
            run_data = await self.store.get_run(run_id)
            if run_data and run_data.get("cleanup") == "delete":
                logger.info(f"Cleaning up session {child_key}")
                session_manager.delete_session(child_key)

    async def kill(self, run_id: str) -> bool:
        event = self._cancel_events.get(run_id)
        if event:
            event.set()
        
        task = self._tasks.get(run_id)
        if task:
            task.cancel()
            return True
        return False

    async def steer(self, run_id: str, message: str) -> bool:
        run = await self.store.get_run(run_id)
        if not run: return False
        
        child_key = run["child_session_key"]
        # Injected into the conversation for the agent to pick up
        # ConversationManager expects session_id as used in file names (colons replaced)
        from core.session import ConversationManager
        conv = ConversationManager(session_id=child_key.replace(':', '_'))
        conv.load()
        conv.add_message("user", f"GUIDANCE: {message}")
        conv.save()
        return True

subagent_manager = SubagentManager()
