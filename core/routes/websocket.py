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

import json
import logging
import os

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger("jarvis")

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/mcp/bridge")
async def mcp_bridge_websocket(websocket: WebSocket):
    from mcp.server import mcp_server
    await mcp_server.handle_websocket(websocket)


@router.websocket("/ws/chat_stream")
async def chat_stream_websocket(ws: WebSocket):
    import traceback as _tb
    try:
        from core.plugins import plugin_registry
    except Exception:
        plugin_registry = None
        logger.exception("[WS] plugin registry unavailable")

    await ws.accept()
    print("[WS] ACCEPTED", flush=True)
    logger.info("WS_STAGE_1_ACCEPTED")
    session_id = str(id(ws))
    if plugin_registry:
        try:
            await plugin_registry.run_hook("session_start", session_id=session_id, metadata={"source": "websocket"})
        except Exception:
            logger.exception("[WS] session_start hook failed")
    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get('type')

            # Accept both standard format: {"type":"chat","text":"..."}
            # and CLI format: {"message":"...", "tier":"...", "session_id":"..."}
            if msg_type == 'chat' or (msg_type is None and 'message' in msg):
                text = msg.get('text') or msg.get('message', '')
                session_id = msg.get('session_id') or str(id(ws))
                user_id = session_id

                from core.pipeline.adapters import ws_adapter
                await ws_adapter.stream_via_pipeline(
                    ws=ws,
                    text=text,
                    user_id=user_id,
                    session_id=session_id,
                    metadata={"channel": "websocket"},
                )
                logger.info("WS_STAGE_PIPELINE_DONE")
                if plugin_registry:
                    await plugin_registry.run_hook("message_sent", message={"id": session_id, "text": text, "type": "response"})
            elif msg_type == 'ping':
                await ws.send_json({'type': 'pong'})
    except WebSocketDisconnect:
        await plugin_registry.run_hook("session_end", session_id=session_id, summary={"disconnect": "websocket_disconnect"})
        pass
    except Exception as e:
        try:
            await ws.send_json({"type": "error", "message": "An unexpected error occurred"})
        except Exception:
            pass
        logger.warning("WebSocket exception: %s", e, exc_info=True)
        _tb.print_exc()
        await plugin_registry.run_hook("session_end", session_id=session_id, summary={"error": str(e)})
        try:
            await ws.close()
        except Exception as _e:
            print(f"[WS] close failed: {_e}")
    else:
        await plugin_registry.run_hook("session_end", session_id=session_id, summary={"status": "closed"})


@router.websocket("/ws/logs")
async def log_stream_websocket(ws: WebSocket):
    import asyncio
    from pathlib import Path

    await ws.accept()

    log_paths = [
        Path("data/logs/jarvis.json.log"),
        Path("logs/jarvis.log"),
    ]

    for lp in log_paths:
        lp.parent.mkdir(parents=True, exist_ok=True)

    async def tail_file(file: Path):
        if not file.exists():
            file.write_text("")
        size = file.stat().st_size
        while True:
            try:
                cur = file.stat().st_size
                if cur > size:
                    with open(file, encoding="utf-8", errors="replace") as f:
                        f.seek(size)
                        for line in f:
                            yield line
                    size = cur
            except (OSError, Exception):
                pass
            await asyncio.sleep(0.3)

    try:
        async for line in tail_file(log_paths[0]):
            line = line.strip()
            if not line:
                continue
            severity = "INFO"
            for s in ("ERROR", "WARNING", "INFO", "DEBUG", "CRITICAL"):
                if f'"{s}"' in line or f'{s}' in line:
                    severity = s
                    break
            import re
            clean = re.sub(r'\x1b\[[0-9;]*m', '', line)
            await ws.send_json({
                "type": "log_entry",
                "message": clean,
                "severity": severity,
                "timestamp": __import__("time").time(),
            })
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("[WS Logs] error: %s", e)


@router.websocket("/ws/agent_stream")
async def agent_stream_websocket(ws: WebSocket):
    import time
    from core.plugins import plugin_registry
    from core.routing import get_context_manager
    from core.routing.project_context import ProjectContext

    await ws.accept()
    session_id = str(id(ws))
    logger.info("[WS Agent] connected session_id=%s", session_id)
    session_ctx: ProjectContext | None = None
    cm = get_context_manager()

    await plugin_registry.run_hook("session_start", session_id=session_id, metadata={"source": "agent_websocket"})
    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type")

            # ── Session Init: store project context ────────────────────────
            if msg_type == "session_init":
                session_id = msg.get("session_id") or session_id
                pctx = msg.get("project_context", {})
                cwd = pctx.get("cwd", os.getcwd())
                session_ctx = cm.get_or_create_context(cwd)
                if pctx:
                    session_ctx.cwd = cwd
                    if not session_ctx.last_scan:
                        session_ctx.refresh()
                cm.update_session_context(session_id, cwd)
                session = cm.get_session(session_id)
                session.cwd = cwd

                summary = session_ctx.to_dict()
                await ws.send_json({
                    "type": "workspace_summary",
                    "project_type": summary.get("project_type", "unknown"),
                    "languages": summary.get("languages", []),
                    "build_system": summary.get("build_system", []),
                    "entrypoints": summary.get("entrypoints", []),
                    "branch": summary.get("branch", ""),
                    "cwd": cwd,
                    "tools_available": 38,
                })
                continue

            # ── Context Update: refresh project context ────────────────────
            if msg_type == "context_update":
                pctx = msg.get("project_context", {})
                cwd = pctx.get("cwd") or (session_ctx and session_ctx.cwd) or os.getcwd()
                session_ctx = cm.update_project_context(cwd)
                session = cm.get_session(session_id)
                session.cwd = cwd
                summary = session_ctx.to_dict()
                await ws.send_json({
                    "type": "workspace_summary",
                    "project_type": summary.get("project_type", "unknown"),
                    "languages": summary.get("languages", []),
                    "branch": summary.get("branch", ""),
                    "cwd": cwd,
                })
                continue

            # ── Chat Message ───────────────────────────────────────────────
            if msg_type == "chat":
                text = msg.get("text", "")
                if not text.strip():
                    continue
                from ..session import ConversationManager
                conv = ConversationManager(session_id=session_id)
                if conv.path.exists():
                    conv.load()

                from core.pipeline.adapters import ws_adapter
                result = await ws_adapter(text=text, user_id=session_id, session_id=session_id)
                response_text = result.get("response", "I had an issue processing that.") if result else "I had an issue processing that."
                conv.add_message("user", text)
                conv.add_message("assistant", response_text)
                conv.save()
                await ws.send_json({"type": "stream_token", "token": response_text, "complete": True})
                await ws.send_json({"type": "stream_end"})
                continue

            # ── Session Response (tool confirmation) ───────────────────────
            if msg_type == "session_response":
                # Forward to resume handler via state
                await ws.send_json({"type": "session_response_ack", "approved": msg.get("approved", False)})
                continue

            if msg_type == "ping":
                await ws.send_json({"type": "pong"})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("[WS Agent] Error: %s", e)
        try:
            await ws.close()
        except Exception as _e:
            logger.warning("[core.routes.websocket] broadcast_event failed: %s", _e)


@router.websocket("/ws/{device_id}/{user_id}")
async def websocket_endpoint(ws: WebSocket, device_id: str, user_id: int):
    from datetime import datetime

    from network.websocket_server import connection_manager, handle_message

    await connection_manager.connect(ws, device_id, user_id)
    try:
        await ws.send_json({
            "type": "connected",
            "payload": {
                "device_id": device_id,
                "user_id": user_id,
                "server_time": datetime.utcnow().isoformat(),
            },
        })
        while True:
            raw = await ws.receive_text()
            await handle_message(ws, device_id, user_id, raw)
    except WebSocketDisconnect:
        connection_manager.disconnect(device_id, user_id)
