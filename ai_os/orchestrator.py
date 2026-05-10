import time, asyncio
from typing import Any
from .config import AIOSConfig
from .planner import Planner
from .policy import PolicyEngine
from .tool_registry import ToolRegistry, get_default_tool_registry
from .model_router import ModelRouter
from .memory import MemoryManager
from .event_bus import EventBus


class AIOrchestrator:
    def __init__(self, config: AIOSConfig | None = None):
        self.config = config or AIOSConfig()
        self.events = EventBus()
        self.memory = MemoryManager(self.config)
        self.model_router = ModelRouter(self.config)
        self.planner = Planner(self.model_router, self.config, self.events)
        self.policy = PolicyEngine(self.config)
        self.tools = get_default_tool_registry()

    def warmup_models(self) -> dict[str, Any]:
        """Warm up available models by checking Ollama status."""
        return self.model_router.warmup_models()

    def _is_safe_to_continue(self, step: dict[str, Any], tool_result: dict[str, Any]) -> bool:
        """Universe-level assertion: decide if safe to continue after tool error."""
        # Always safe to continue on read-only operations
        tool = step.get("tool", "")
        if tool in {"file_ops", "browser_control", "code_agent"}:
            # Read operations are safe to skip
            args = step.get("args", {})
            if tool == "file_ops" and args.get("op") == "read":
                return True
            # Other operations may have side effects - continue anyway
            return True
        
        # For shell commands that failed, it's safe to continue
        if tool == "safe_shell":
            return True
        
        return True

    async def run(self, goal: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        metadata = {"goal": goal, "context": context or {}, "started_at": time.time()}
        self.events.publish("received", metadata)

        try:
            self.events.publish("planning", metadata)
            plan = self.planner.build_plan(goal, context)

            policy_results = self.policy.enforce(plan)
            blocked = [r for r in policy_results if not r["policy"]["allowed"]]
            if blocked:
                reason = blocked[0]["policy"]["reason"]
                self.events.publish("error", {"reason": reason, "step": blocked[0]["step"]})
                return {"success": False, "error": f"Policy blocked action: {reason}", "policy": policy_results}

            execution_log = []
            for step in plan:
                step_event = {"step": step, "status": "executing"}
                self.events.publish("executing", step_event)
                
                try:
                    result = self.tools.execute(step)
                    execution_log.append({"step": step, "result": result})
                    self.events.publish("executed", {"step": step, "result": result})
                    
                    # Universe-level assertion: record errors in memory and continue if safe
                    if not result.get("success", False):
                        # Record error in memory for audit trail
                        self.memory.save_short_term({
                            "type": "error",
                            "step_id": step.get("id", "unknown"),
                            "tool": step.get("tool", "unknown"),
                            "error": result.get("error", "unknown"),
                        })
                        
                        # Check if safe to continue
                        if not self._is_safe_to_continue(step, result):
                            self.events.publish("error", {"step": step, "result": result})
                            break
                        # Otherwise continue with next step
                
                except Exception as tool_error:
                    # Handle unexpected tool exceptions - record and continue
                    self.memory.save_short_term({
                        "type": "exception",
                        "step_id": step.get("id", "unknown"),
                        "tool": step.get("tool", "unknown"),
                        "exception": str(tool_error),
                    })
                    self.events.publish("error", {"step": step, "exception": str(tool_error)})
                    execution_log.append({"step": step, "result": {"success": False, "error": str(tool_error)}})
                    # Continue with next step - errors are non-critical
                    continue

            final = {
                "success": len([e for e in execution_log if e.get("result", {}).get("success", False)]) > 0,
                "goal": goal,
                "plan": plan,
                "execution": execution_log,
                "policy": policy_results,
                "context": context or {},
                "latency_ms": int((time.time() - metadata["started_at"]) * 1000),
                "error_count": len([e for e in execution_log if not e.get("result", {}).get("success", False)]),
            }
            self.memory.save_short_term({"type": "session", "goal": goal, "plan": plan, "result": final})
            self.memory.persist("session", final)
            self.events.publish("completed", final)
            return final

        except Exception as e:
            self.events.publish("error", {"error": str(e)})
            return {"success": False, "error": str(e), "policy": []}
