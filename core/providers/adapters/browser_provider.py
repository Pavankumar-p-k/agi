from __future__ import annotations

import logging
import time
from typing import Any

from core.providers.base import (
    ExecutionProvider,
    ExecutionResult,
    ProviderCapabilities,
    ProviderHealth,
    ProviderHealthStatus,
)

logger = logging.getLogger(__name__)

_BROWSER_TOOL_MAP: dict[str, str] = {
    "browser_navigate": "navigate",
    "browser_click": "click",
    "browser_fill": "fill",
    "browser_press": "press",
    "browser_snapshot": "snapshot",
    "browser_screenshot": "screenshot",
    "browser_evaluate": "evaluate",
    "browser_find": "find",
    "browser_get_url": "get_url",
    "browser_get_title": "get_title",
    "browser_current_state": "current_state",
    "browser_get_history": "get_history",
    "browser_list_tabs": "list_tabs",
    "browser_switch_tab": "switch_tab",
    "browser_new_tab": "new_tab",
    "browser_close_tab": "close_tab",
    "browser_wait_visible": "wait_visible",
    "browser_wait_text": "wait_text",
    "browser_wait_interactive": "wait_interactive",
    "browser_shadow_query": "shadow_query",
    "browser_health": "health",
}


class BrowserProvider(ExecutionProvider):
    provider_id = "browser"
    name = "Browser Automation"
    version = "1.0.0"
    priority = 10
    installed = True

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            capability_names=[
                "browser",
                "web",
                "search",
                "navigate",
                "browse",
            ],
            features=[
                "navigation",
                "search",
                "form_fill",
                "click",
                "extraction",
                "screenshot",
                "tab_management",
            ],
        )

    async def health(self) -> ProviderHealth:
        from core.tools.browser_tools import do_browser_health
        try:
            result = await do_browser_health()
            if result and result.get("status") == "ok":
                return ProviderHealth(
                    status=ProviderHealthStatus.HEALTHY,
                    latency_ms=0.0,
                    last_checked=time.time(),
                )
        except Exception as e:
            logger.debug("[BrowserProvider] Health check failed: %s", e)
        return ProviderHealth(
            status=ProviderHealthStatus.DOWN,
            error="Browser engine unavailable",
            last_checked=time.time(),
        )

    async def execute(
        self, task: dict[str, Any], context: dict[str, Any] | None = None
    ) -> ExecutionResult:
        goal = task.get("goal", task.get("query", ""))
        url = task.get("url", "")
        session_id = task.get("session_id", "")
        start = time.monotonic()

        try:
            from core.tools.browser_planner import BrowserPlanner

            ctx = BrowserPlanner.init(goal)

            blocks, ctx = BrowserPlanner.pre_plan([], ctx)

            all_outputs: list[dict] = []
            max_iterations = 15

            for iteration in range(max_iterations):
                if not blocks:
                    break

                results: list[dict] = []
                for block in blocks:
                    tool_result = await self._execute_tool(
                        block.tool_type, block.content, session_id
                    )
                    results.append(tool_result)
                    all_outputs.append(tool_result)

                blocks, ctx = BrowserPlanner.post_plan(
                    [r for r in results],
                    blocks,
                    ctx,
                )

                fsm_state = ctx.get("fsm", {}).get("state", "")
                if fsm_state in ("COMPLETE", "FAIL"):
                    break

            elapsed = (time.monotonic() - start) * 1000
            success = ctx.get("fsm", {}).get("state") != "FAIL"

            output_parts = []
            for o in all_outputs:
                text = o.get("result", o.get("output", ""))
                if isinstance(text, dict):
                    text = str(text.get("text", text.get("content", str(text))))
                if text and len(str(text)) > 10:
                    output_parts.append(str(text)[:500])
            combined = "\n".join(output_parts) if output_parts else str(all_outputs[-1] if all_outputs else "")

            return ExecutionResult(
                success=success,
                output=combined[:10000],
                exit_code=0 if success else 1,
                duration_ms=elapsed,
                artifacts={},
                metadata={
                    "provider": "browser",
                    "tools_executed": len(all_outputs),
                    "final_state": ctx.get("fsm", {}).get("state", "UNKNOWN"),
                    "url": url or ctx.get("current_url", ""),
                },
            )
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            logger.exception("[BrowserProvider] Execution failed: %s", e)
            return ExecutionResult(
                success=False,
                output="",
                error=str(e),
                exit_code=1,
                duration_ms=elapsed,
                metadata={"provider": "browser"},
            )

    async def handle_tool(
        self, tool_type: str, content: str, **kwargs: Any,
    ) -> ExecutionResult | None:
        if not tool_type.startswith("browser_"):
            return None
        session_id = kwargs.get("session_id", "")
        try:
            result = await self._execute_tool(tool_type, content, session_id)
            success = result.get("status") != "error"
            output = str(result.get("result", result.get("output", "")))
            error = result.get("error", "")
            return ExecutionResult(
                success=success,
                output=output[:10000],
                error=error,
                exit_code=0 if success else 1,
                metadata={"provider": "browser", "tool_type": tool_type},
            )
        except Exception as e:
            return ExecutionResult(
                success=False, output="", error=str(e), exit_code=1,
                metadata={"provider": "browser", "tool_type": tool_type},
            )

    async def _execute_tool(
        self, tool_type: str, content: str, session_id: str
    ) -> dict:
        from core.tools import browser_tools as bt

        tool_map = {
            "browser_navigate": lambda: bt.do_browser_navigate(
                content.strip(), session_id=session_id
            ),
            "browser_snapshot": lambda: bt.do_browser_snapshot(
                session_id=session_id
            ),
            "browser_screenshot": lambda: bt.do_browser_screenshot(
                session_id=session_id
            ),
            "browser_click": lambda: bt.do_browser_click(
                content.strip(), session_id=session_id
            ),
            "browser_fill": lambda: self._fill(content, session_id),
            "browser_press": lambda: self._press(content, session_id),
            "browser_evaluate": lambda: bt.do_browser_evaluate(
                content.strip(), session_id=session_id
            ),
            "browser_find": lambda: bt.do_browser_find(
                content.strip(), session_id=session_id
            ),
            "browser_get_url": lambda: bt.do_browser_get_url(
                session_id=session_id
            ),
            "browser_get_title": lambda: bt.do_browser_get_title(
                session_id=session_id
            ),
            "browser_current_state": lambda: bt.do_browser_current_state(
                session_id=session_id
            ),
            "browser_get_history": lambda: bt.do_browser_get_history(
                session_id=session_id
            ),
            "browser_list_tabs": lambda: bt.do_browser_list_tabs(
                session_id=session_id
            ),
            "browser_switch_tab": lambda: bt.do_browser_switch_tab(
                int(content.strip()) if content.strip().lstrip("-").isdigit() else 0,
                session_id=session_id,
            ),
            "browser_new_tab": lambda: bt.do_browser_new_tab(
                url=content.strip() or None, session_id=session_id
            ),
            "browser_close_tab": lambda: bt.do_browser_close_tab(
                int(content.strip()) if content.strip().lstrip("-").isdigit() else 0,
                session_id=session_id,
            ),
            "browser_wait_visible": lambda: bt.do_browser_wait_visible(
                content.strip(), session_id=session_id
            ),
            "browser_wait_text": lambda: bt.do_browser_wait_text(
                content.strip(), session_id=session_id
            ),
            "browser_wait_interactive": lambda: bt.do_browser_wait_interactive(
                content.strip(), session_id=session_id
            ),
            "browser_shadow_query": lambda: bt.do_browser_shadow_query(
                content.strip(), session_id=session_id
            ),
            "browser_health": lambda: bt.do_browser_health(
                session_id=session_id
            ),
        }

        handler = tool_map.get(tool_type)
        if handler is None:
            return {"tool": tool_type, "status": "error", "error": f"Unknown tool: {tool_type}"}

        try:
            result = await handler()
            return {"tool": tool_type, "result": result, "status": result.get("status", "ok")}
        except Exception as e:
            return {"tool": tool_type, "status": "error", "error": str(e)}

    async def _fill(self, content: str, session_id: str) -> dict:
        from core.tools import browser_tools as bt
        parts = content.split("\n", 1)
        selector = parts[0].strip()
        text = parts[1].strip() if len(parts) > 1 else ""
        return await bt.do_browser_fill(selector, text, session_id=session_id)

    async def _press(self, content: str, session_id: str) -> dict:
        from core.tools import browser_tools as bt
        parts = content.split("\n", 1)
        selector = parts[0].strip()
        key = parts[1].strip() if len(parts) > 1 else "Enter"
        return await bt.do_browser_press(selector, key, session_id=session_id)

    async def estimate_cost(self, task: dict[str, Any]) -> float:
        return 0.0

    async def estimate_latency(self, task: dict[str, Any]) -> float:
        return 100.0
