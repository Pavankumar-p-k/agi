from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class MCPServer:
    """Exposes JARVIS tools and resources via the Model Context Protocol.

    MCP allows LLMs (Claude, etc.) to discover and call JARVIS tools
    through a standardized interface — matching OpenClaw's MCP bridge.
    """

    def __init__(self):
        self._tools: dict[str, dict] = {}
        self._resources: dict[str, dict] = {}
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def register_tool(self, name: str, description: str,
                      input_schema: dict, handler: Any) -> None:
        self._tools[name] = {
            "name": name,
            "description": description,
            "inputSchema": input_schema,
            "handler": handler,
        }
        logger.debug("[MCP] Registered tool: %s", name)

    def register_resource(self, uri: str, name: str,
                          description: str, handler: Any) -> None:
        self._resources[uri] = {
            "uri": uri,
            "name": name,
            "description": description,
            "handler": handler,
        }
        logger.debug("[MCP] Registered resource: %s", uri)

    def get_tool_definitions(self) -> list[dict]:
        return [
            {"name": t["name"], "description": t["description"],
             "inputSchema": t["inputSchema"]}
            for t in self._tools.values()
        ]

    def get_resource_definitions(self) -> list[dict]:
        return [
            {"uri": r["uri"], "name": r["name"], "description": r["description"]}
            for r in self._resources.values()
        ]

    async def call_tool(self, name: str, arguments: dict) -> Any:
        tool = self._tools.get(name)
        if not tool:
            raise ValueError(f"Unknown MCP tool: {name}")
        return await tool["handler"](**arguments)

    async def read_resource(self, uri: str) -> Any:
        resource = self._resources.get(uri)
        if not resource:
            raise ValueError(f"Unknown MCP resource: {uri}")
        return await resource["handler"]()

    # ── JARVIS-local tools (registered at startup) ──

    def _register_jarvis_tools(self):
        self.register_tool(
            name="web_search",
            description="Search the web for current information",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "max_results": {"type": "integer", "description": "Max results", "default": 5},
                },
                "required": ["query"],
            },
            handler=self._handle_web_search,
        )
        self.register_tool(
            name="browser_navigate",
            description="Navigate a browser to a URL",
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to navigate to"},
                },
                "required": ["url"],
            },
            handler=self._handle_browser_navigate,
        )
        self.register_tool(
            name="computer",
            description="Execute a natural language PC command",
            input_schema={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Command to execute"},
                },
                "required": ["command"],
            },
            handler=self._handle_computer,
        )
        self.register_tool(
            name="memory_search",
            description="Search JARVIS's semantic memory",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {"type": "integer", "description": "Max results", "default": 5},
                },
                "required": ["query"],
            },
            handler=self._handle_memory_search,
        )
        self.register_tool(
            name="send_message",
            description="Send a message via a messaging channel",
            input_schema={
                "type": "object",
                "properties": {
                    "channel": {"type": "string", "description": "Channel (discord, slack, telegram, etc.)"},
                    "target": {"type": "string", "description": "Recipient or channel ID"},
                    "message": {"type": "string", "description": "Message text"},
                },
                "required": ["channel", "target", "message"],
            },
            handler=self._handle_send_message,
        )
        self.register_tool(
            name="get_status",
            description="Get JARVIS system status",
            input_schema={
                "type": "object",
                "properties": {},
            },
            handler=self._handle_get_status,
        )

    async def _handle_web_search(self, query: str, max_results: int = 5) -> str:
        try:
            from tools.search_tool import SearchDecisionGate
            gate = SearchDecisionGate()
            if not gate.should_search(query):
                return "Search not needed for this query."
            from tools.search_fallback import search_with_content
            results = await search_with_content(query, max_results=max_results)
            return json.dumps(results, indent=2)
        except Exception as e:
            return f"Search failed: {e}"

    async def _handle_browser_navigate(self, url: str) -> str:
        try:
            from tools.browser_tool import BrowserTool
            bt = BrowserTool()
            result = await bt.navigate(url)
            return f"Navigated to {url}: {result}"
        except Exception as e:
            return f"Browser failed: {e}"

    async def _handle_computer(self, command: str) -> str:
        try:
            from pc_agent.computer_agent import ComputerAgent
            agent = ComputerAgent()
            result = await agent.run(command)
            return str(result)
        except Exception as e:
            return f"PC command failed: {e}"

    async def _handle_memory_search(self, query: str, limit: int = 5) -> str:
        try:
            from memory.tiered_memory import TieredMemory
            tm = TieredMemory()
            results = await tm.recall(query, limit=limit)
            return json.dumps(results, indent=2)
        except Exception as e:
            return f"Memory search failed: {e}"

    async def _handle_send_message(self, channel: str, target: str, message: str) -> str:
        try:
            from channels import channel_controller
            ch = channel_controller.get(channel)
            if not ch:
                return f"Unknown channel: {channel}"
            if not ch.is_running:
                return f"Channel {channel} is not running"
            ok = await ch.send(target, message)
            return f"Message sent: {ok}"
        except Exception as e:
            return f"Send failed: {e}"

    async def _handle_get_status(self) -> str:
        import datetime
        try:
            from channels import channel_controller
            channels = [
                {"id": c.id, "name": c.name, "running": c.is_running}
                for c in channel_controller.channels.values()
            ]
            from core.llm_router import get_available_providers
            providers = get_available_providers()
            return json.dumps({
                "time": datetime.datetime.now().isoformat(),
                "channels": channels,
                "llm_providers": providers,
                "plugins_running": hasattr(__import__("core.plugins", fromlist=["plugin_registry"]), "plugin_registry"),
            }, indent=2)
        except Exception as e:
            return f"Status failed: {e}"

    # ── Lifecycle ──

    async def start(self) -> None:
        self._register_jarvis_tools()
        self._running = True
        logger.info("[MCP] Server ready — %d tools, %d resources",
                     len(self._tools), len(self._resources))

    async def stop(self) -> None:
        self._running = False
        logger.info("[MCP] Server stopped")

    def get_fastapi_router(self):
        from fastapi import APIRouter
        router = APIRouter(prefix="/mcp")

        @router.get("/tools")
        async def list_mcp_tools():
            return {"tools": self.get_tool_definitions()}

        @router.get("/resources")
        async def list_mcp_resources():
            return {"resources": self.get_resource_definitions()}

        @router.post("/tools/call")
        async def call_mcp_tool(body: dict):
            name = body.get("name")
            arguments = body.get("arguments", {})
            try:
                result = await self.call_tool(name, arguments)
                return {"result": result}
            except ValueError as e:
                from fastapi import HTTPException
                raise HTTPException(404, str(e))

        return router


mcp_server = MCPServer()
