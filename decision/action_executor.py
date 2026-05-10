# decision/action_executor.py
from __future__ import annotations


class ActionExecutor:
    async def execute(self, decision, tools) -> dict:
        try:
            tool = decision.tool
            params = decision.params or {}

            if hasattr(tools, tool):
                fn = getattr(tools, tool)
                if callable(fn):
                    result = fn(**params) if params else fn()
                    if hasattr(result, "__await__"):
                        result = await result
                    return {"success": True, "result": result}

            # fallback: speak if available
            if hasattr(tools, "speak"):
                await tools.speak(f"Action: {decision.action}")
            return {"success": True, "result": None}
        except Exception as e:
            return {"success": False, "error": str(e)}
