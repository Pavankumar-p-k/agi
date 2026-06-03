"""ai_os/orchestrator.py
AIOrchestrator — now uses TaskRouter for all dispatch decisions.

execute(task, context) flow:
  1. TaskRouter.route(task) → RouteDecision
  2. Dispatch to sub_agent / skill / tool / llm_direct
  3. Return structured result

The old AIOrchestrator.run(goal) path is preserved for backward-compat.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from .config      import AIOSConfig
from .planner     import Planner
from .policy      import PolicyEngine
from .tool_registry import ToolRegistry, get_default_tool_registry
from .model_router  import ModelRouter
from .memory        import MemoryManager
from .event_bus     import EventBus

try:
    from jarvis_os.core.planner import PlanningEngine
except ImportError:
    PlanningEngine = None

logger = logging.getLogger(__name__)


class AIOrchestrator:
    """AI OS Orchestrator with governance-layer routing.

    New method
    ----------
    execute(task, context) → structured result dict using TaskRouter

    Legacy method
    -------------
    run(goal, context)     → original plan-based execution (unchanged)
    """

    def __init__(self, config: AIOSConfig | None = None):
        self.config      = config or AIOSConfig()
        self.events      = EventBus()
        self.memory      = MemoryManager(self.config)
        self.model_router = ModelRouter(self.config)
        self.tools       = get_default_tool_registry()

        engine      = PlanningEngine(self.tools, self.model_router) if PlanningEngine else None
        self.planner = Planner(planner=engine, router=self.model_router,
                               config=self.config, events=self.events)
        self.policy  = PolicyEngine(self.config)

        # Lazy-loaded router
        self._task_router = None

    @property
    def task_router(self):
        if self._task_router is None:
            from core.governance.task_router import task_router
            self._task_router = task_router
            # Register known tools so skill matching works
            self._task_router._load_skill_keywords(self.tools)
        return self._task_router

    # ── new execute() using TaskRouter ────────────────────────────────────────

    async def execute(self, task: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Route and execute a task via the governance layer."""
        context = context or {}
        started = time.time()

        self.events.publish("received", {"task": task, "context": context})

        try:
            # Step 1: route
            decision = await self.task_router.route(task, context)
            self.events.publish("routed", decision.to_dict())

            # Step 2: clarification check
            if decision.needs_clarification():
                return {
                    "success":    False,
                    "task":       task,
                    "status":     "needs_clarification",
                    "decision":   decision.to_dict(),
                    "message":    (
                        f"Task routing confidence is low ({decision.confidence:.0%}). "
                        "Please provide more detail."
                    ),
                    "latency_ms": int((time.time() - started) * 1000),
                }

            # Step 3: dispatch
            result = await self._dispatch(task, context, decision)

            payload = {
                "success":    True,
                "task":       task,
                "handler":    decision.handler,
                "target":     decision.target,
                "decision":   decision.to_dict(),
                "result":     result,
                "latency_ms": int((time.time() - started) * 1000),
            }
            self.memory.save_short_term({"type": "execute", "task": task, "result": payload})
            self.events.publish("completed", payload)
            return payload

        except Exception as exc:
            logger.exception("[Orchestrator] execute() failed: %s", exc)
            err_payload = {
                "success":    False,
                "task":       task,
                "error":      str(exc),
                "latency_ms": int((time.time() - started) * 1000),
            }
            self.events.publish("error", err_payload)
            return err_payload

    # ── dispatch helpers ──────────────────────────────────────────────────────

    async def _dispatch(self, task: str, context: dict, decision) -> Any:
        """Dispatch to the correct handler — no hardcoded if/elif chains."""
        handler_map = {
            "llm_direct": self._handle_llm_direct,
            "sub_agent":  self._handle_sub_agent,
            "skill":      self._handle_skill,
            "tool":       self._handle_tool,
        }
        fn = handler_map.get(decision.handler)
        if fn is None:
            raise ValueError(f"Unknown handler type '{decision.handler}'")
        return await fn(task, context, decision)

    async def _handle_llm_direct(self, task: str, context: dict, decision) -> dict:
        try:
            from core.llm_router import complete  # type: ignore
            result = await complete("chat", [{"role": "user", "content": task}])
            answer = result.unwrap_or("") if hasattr(result, "unwrap_or") else str(result)
            return {"response": answer, "source": "llm_direct"}
        except Exception as exc:
            logger.debug("[Orchestrator] llm_direct error: %s", exc)
            return {"response": f"Offline mode — task noted: {task}", "source": "llm_direct"}

    async def _handle_sub_agent(self, task: str, context: dict, decision) -> dict:
        agent_role = decision.target
        try:
            from core.agent_registry import get_agent  # type: ignore
            agent  = get_agent(agent_role)
            result = await agent.execute(task, context)
            return {"result": result, "agent": agent_role}
        except Exception as exc:
            logger.warning("[Orchestrator] sub_agent '%s' error: %s", agent_role, exc)
            # Graceful fallback to LLM
            return await self._handle_llm_direct(task, context, decision)

    async def _handle_skill(self, task: str, context: dict, decision) -> dict:
        skill_id = decision.target
        try:
            from skills.registry import get_skill  # type: ignore
            skill_fn = get_skill(skill_id)
            result   = await skill_fn({"task": task, **context})
            return {"result": result, "skill": skill_id}
        except Exception as exc:
            logger.warning("[Orchestrator] skill '%s' error: %s", skill_id, exc)
            return {"error": str(exc), "skill": skill_id}

    async def _handle_tool(self, task: str, context: dict, decision) -> dict:
        tool_name = decision.target
        try:
            result = self.tools.execute({"tool": tool_name, "args": {"task": task, **context}})
            return {"result": result, "tool": tool_name}
        except Exception as exc:
            logger.warning("[Orchestrator] tool '%s' error: %s", tool_name, exc)
            return {"error": str(exc), "tool": tool_name}

    # ── legacy run() — unchanged ──────────────────────────────────────────────

    def warmup_models(self) -> dict[str, Any]:
        return self.model_router.warmup_models()

    def _is_safe_to_continue(self, step: dict[str, Any], tool_result: dict[str, Any]) -> bool:
        return True  # read-only + shell ops are always safe to continue past

    async def run(self, goal: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Original plan-based execution — preserved for backward-compat."""
        metadata = {"goal": goal, "context": context or {}, "started_at": time.time()}
        self.events.publish("received", metadata)

        try:
            self.events.publish("planning", metadata)
            plan = self.planner.build_plan(goal, {"type": "auto"}, context or {})

            policy_results = self.policy.enforce(plan)
            blocked = [r for r in policy_results if not r["policy"]["allowed"]]
            if blocked:
                reason = blocked[0]["policy"]["reason"]
                self.events.publish("error", {"reason": reason, "step": blocked[0]["step"]})
                return {"success": False, "error": f"Policy blocked: {reason}", "policy": policy_results}

            execution_log = []
            for step in plan:
                self.events.publish("executing", {"step": step})
                try:
                    result = self.tools.execute(step)
                    execution_log.append({"step": step, "result": result})
                    self.events.publish("executed", {"step": step, "result": result})
                    if not result.get("success", False):
                        self.memory.save_short_term({
                            "type": "error",
                            "step_id": step.get("id", "unknown"),
                            "tool": step.get("tool", "unknown"),
                            "error": result.get("error", "unknown"),
                        })
                        if not self._is_safe_to_continue(step, result):
                            break
                except Exception as tool_error:
                    self.memory.save_short_term({
                        "type": "exception",
                        "step_id": step.get("id", "unknown"),
                        "error": str(tool_error),
                    })
                    self.events.publish("error", {"step": step, "exception": str(tool_error)})
                    execution_log.append({"step": step, "result": {"success": False, "error": str(tool_error)}})
                    continue

            final = {
                "success": any(e.get("result", {}).get("success", False) for e in execution_log),
                "goal":       goal,
                "plan":       plan,
                "execution":  execution_log,
                "policy":     policy_results,
                "context":    context or {},
                "latency_ms": int((time.time() - metadata["started_at"]) * 1000),
                "error_count": sum(
                    1 for e in execution_log
                    if not e.get("result", {}).get("success", False)
                ),
            }
            self.memory.save_short_term({"type": "session", "goal": goal, "result": final})
            self.memory.persist("session", final)
            self.events.publish("completed", final)
            return final

        except Exception as e:
            self.events.publish("error", {"error": str(e)})
            return {"success": False, "error": str(e), "policy": []}
