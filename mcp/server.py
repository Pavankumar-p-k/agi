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
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Set

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger("jarvis.mcp.server")

@dataclass
class QueueEvent:
    cursor: int
    type: str  # "message" | "approval_requested" | "approval_resolved"
    payload: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)

@dataclass
class PendingApproval:
    kind: Literal["exec", "plugin"]
    id: str
    tool_name: str
    description: str
    input_preview: str
    created_at: float = field(default_factory=time.time)
    expires_at: float = field(default=0.0)

    def __post_init__(self):
        if not self.expires_at:
            self.expires_at = self.created_at + 1800  # 30 mins

class MCPServer:
    """Exposes JARVIS tools and resources via the Model Context Protocol.

    Handles both HTTP (for local agents) and WebSocket (for external bridge)
    connections, providing a unified interface for tool discovery and execution.
    """

    def __init__(self):
        self._tools: dict[str, dict] = {}
        self._resources: dict[str, dict] = {}
        self._running = False
        
        # Bridge state
        self._connected_clients: Set[WebSocket] = set()
        self._event_queue: List[QueueEvent] = []
        self._cursor_counter = 0
        self._pending_approvals: Dict[str, PendingApproval] = {}
        self._approval_waiters: Dict[str, asyncio.Future] = {}
        self._waiters: List[asyncio.Event] = []

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

        # Check for approval if tool needs confirmation
        try:
            from core.tools.policy import policy_engine
            policy = policy_engine.get_policy(name)
            if policy and policy.needs_confirmation:
                import uuid
                approval_id = str(uuid.uuid4())
                decision = await self.wait_for_approval(
                    kind="exec",
                    approval_id=approval_id,
                    tool_name=name,
                    description=policy.description or f"Execution of {name}",
                    input_preview=json.dumps(arguments)[:1000]
                )
                if decision == "deny":
                    return {"content": [{"type": "text", "text": f"Tool '{name}' execution was denied by user."}], "isError": True}
        except Exception as e:
            logger.warning(f"[MCP] Approval check failed for {name}: {e}")

        return await tool["handler"](**arguments)

    async def read_resource(self, uri: str) -> Any:
        resource = self._resources.get(uri)
        if not resource:
            raise ValueError(f"Unknown MCP resource: {uri}")
        return await resource["handler"]()

    # ── WebSocket Bridge ──

    async def handle_websocket(self, websocket: WebSocket):
        """Handle bidirectional MCP Bridge connections."""
        await websocket.accept()
        
        # Enable token-based authentication
        try:
            from core.gateway.auth import BridgeAuth
            if not await BridgeAuth().authenticate(websocket):
                return
        except ImportError:
            logger.warning("[MCP] BridgeAuth not found, allowing unauthenticated connection")

        self._connected_clients.add(websocket)
        logger.info(f"[MCP] External bridge connected from {websocket.client}")

        try:
            while True:
                data = await websocket.receive_text()
                try:
                    msg = json.loads(data)
                    response = await self._handle_mcp_rpc(msg)
                    if response:
                        await websocket.send_text(json.dumps(response))
                except json.JSONDecodeError:
                    logger.warning(f"[MCP] Invalid JSON from bridge client: {data}")
                except Exception as e:
                    logger.exception(f"[MCP] Error handling bridge message: {e}")
                    
        except WebSocketDisconnect:
            logger.info("[MCP] External bridge disconnected")
        finally:
            self._connected_clients.discard(websocket)

    async def _handle_mcp_rpc(self, msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Dispatcher for JSON-RPC 2.0 messages from bridge clients."""
        msg_id = msg.get("id")
        method = msg.get("method")
        params = msg.get("params", {})

        if not method: return None

        # Handle initialization
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}, "logging": {}},
                    "serverInfo": {"name": "JARVIS MCP Server", "version": "1.0.0"}
                }
            }

        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": self.get_tool_definitions()}
            }

        if method == "tools/call":
            name = params.get("name")
            args = params.get("arguments", {})
            try:
                result = await self.call_tool(name, args)
                
                # If result is already in MCP format, use it directly
                if isinstance(result, dict) and "content" in result:
                    return {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": result
                    }

                # Otherwise, wrap it
                if isinstance(result, str):
                    content = [{"type": "text", "text": result}]
                else:
                    content = [{"type": "text", "text": json.dumps(result, indent=2)}]
                
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {"content": content, "isError": False}
                }
            except Exception as e:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {"content": [{"type": "text", "text": str(e)}], "isError": True}
                }

        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"}
        }

    # ── Event Queue & Approvals ──

    def enqueue_event(self, type: str, payload: Dict[str, Any]):
        """Enqueue an event and notify connected bridge clients."""
        self._cursor_counter += 1
        event = QueueEvent(cursor=self._cursor_counter, type=type, payload=payload)
        self._event_queue.append(event)
        
        # Bounded queue
        if len(self._event_queue) > 1000:
            self._event_queue.pop(0)

        # Notify long-pollers
        for waiter in self._waiters:
            waiter.set()
        self._waiters.clear()

        # Push notification to WebSocket clients
        if self._connected_clients:
            notification = {
                "jsonrpc": "2.0",
                "method": "notifications/event",
                "params": {
                    "cursor": event.cursor,
                    "type": event.type,
                    "payload": event.payload,
                    "timestamp": event.timestamp
                }
            }
            msg = json.dumps(notification)
            for ws in self._connected_clients:
                asyncio.create_task(ws.send_text(msg))

    async def wait_for_approval(self, kind: str, approval_id: str, 
                                tool_name: str, description: str, 
                                input_preview: str, timeout: float = 600) -> str:
        """Wait for an external client to resolve an approval."""
        approval = PendingApproval(
            kind=kind, id=approval_id, tool_name=tool_name,
            description=description, input_preview=input_preview
        )
        self._pending_approvals[approval_id] = approval
        
        self.enqueue_event("approval_requested", {
            "kind": kind, "id": approval_id, "tool_name": tool_name,
            "description": description, "input_preview": input_preview
        })

        future = asyncio.get_event_loop().create_future()
        self._approval_waiters[approval_id] = future
        try:
            logger.info(f"[MCP] Waiting for approval {approval_id}...")
            decision = await asyncio.wait_for(future, timeout=timeout)
            return decision
        except asyncio.TimeoutError:
            logger.warning(f"[MCP] Approval {approval_id} timed out")
            return "deny"
        finally:
            self._pending_approvals.pop(approval_id, None)
            self._approval_waiters.pop(approval_id, None)

    # ── JARVIS-local tools (registered at startup) ──

    def _register_jarvis_tools(self):
        # 1. Standard tools
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

        # 2. Bridge-specific tools (for external control)
        self.register_tool(
            name="conversations_list",
            description="List active JARVIS sessions",
            input_schema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 50},
                    "search": {"type": "string"},
                }
            },
            handler=self._handle_conversations_list,
        )
        self.register_tool(
            name="events_poll",
            description="Poll for new JARVIS events since a cursor",
            input_schema={
                "type": "object",
                "properties": {
                    "after_cursor": {"type": "integer", "default": 0},
                    "limit": {"type": "integer", "default": 20}
                }
            },
            handler=self._handle_events_poll,
        )
        self.register_tool(
            name="permissions_respond",
            description="Respond to a pending tool execution approval",
            input_schema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "The approval ID"},
                    "decision": {"type": "string", "enum": ["allow-once", "allow-always", "deny"]}
                },
                "required": ["id", "decision"]
            },
            handler=self._handle_permissions_respond,
        )

    # ── Tool Implementation Handlers ──

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
            from core.browser_manager import BrowserManager
            bm = BrowserManager.instance()
            session = await bm.get_or_create_session()
            page = session.current_page
            if page:
                await page.goto(url, timeout=30000)
            result = f"navigated to {url}"
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
            from memory.memory_facade import memory
            results = memory.recall(query, limit=limit)
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

    async def _handle_conversations_list(self, limit: int = 50, search: str = "") -> list[dict]:
        from core.session import session_manager
        return session_manager.list_conversations(limit=limit, search=search)

    async def _handle_events_poll(self, after_cursor: int = 0, limit: int = 20) -> dict:
        events = [e for e in self._event_queue if e.cursor > after_cursor]
        events = events[:limit]
        return {
            "events": [
                {"cursor": e.cursor, "type": e.type, "payload": e.payload, "timestamp": e.timestamp}
                for e in events
            ],
            "last_cursor": events[-1].cursor if events else after_cursor
        }

    async def _handle_permissions_respond(self, id: str, decision: str) -> str:
        future = self._approval_waiters.get(id)
        if future and not future.done():
            future.set_result(decision)
            return f"Approval {id} resolved with {decision}"
        return f"Approval {id} not found or already expired"

    # ── Lifecycle ──

    async def start(self) -> None:
        self._register_jarvis_tools()
        self._running = True
        logger.info("[MCP] Server ready — %d tools, %d resources",
                     len(self._tools), len(self._resources))

    async def stop(self) -> None:
        self._running = False
        # Clear event waiters
        for waiter in self._waiters:
            waiter.set()
        self._waiters.clear()
        
        # Deny pending approvals
        for future in self._approval_waiters.values():
            if not future.done():
                future.set_result("deny")
        
        # Close connections
        for ws in self._connected_clients:
            try:
                await ws.close()
            except Exception as e:
                logger.warning("[mcp.server] mcp_handle_request failed: %s", e)
        self._connected_clients.clear()
        
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
