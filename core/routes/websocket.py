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
import json
import logging
import os

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger("jarvis")

router = APIRouter(tags=["WebSocket"])


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


@router.websocket("/ws/mcp/bridge")
async def mcp_bridge_websocket(websocket: WebSocket):
    from mcp.server import mcp_server
    await mcp_server.handle_websocket(websocket)


@router.websocket("/ws/chat_stream")
async def chat_stream_websocket(ws: WebSocket):
    from core.intent_router import extract_intent
    from core.llm_router import get_router
    from core.model_router import get_router_model, route_request
    from core.plugins import plugin_registry

    await ws.accept()
    session_id = str(id(ws))
    await plugin_registry.run_hook("session_start", session_id=session_id, metadata={"source": "websocket"})
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

                from ..context_builder import build_unified_context
                history_context = await build_unified_context(text, session_id=session_id)

                system_prompt = "You are JARVIS, your AI assistant. Be concise."
                if history_context:
                    system_prompt = history_context + "\n\n" + system_prompt

                model, tier, processed_query = route_request(text)

                intent_data = await extract_intent(processed_query)
                from ..main import execute_action
                action_result = await execute_action(intent_data, message=text, session_id=session_id)
                current_intent = intent_data.get("intent", "chat")

                non_chat_intents = ("build", "pc_control", "open_url", "play_media",
                                    "reminder", "weather", "news", "stocks", "sports", "time", "web_search", "search")
                ws_provenance = {"source": "inference", "confidence": 0.5, "url": None}
                ws_source_intents = {"web_search": "web_search", "search": "web_search", "news": "tool_result", "weather": "tool_result", "stocks": "tool_result", "time": "tool_result", "sports": "tool_result"}
                ws_detected = ws_source_intents.get(current_intent)
                if ws_detected:
                    ws_provenance["source"] = ws_detected
                    ws_provenance["confidence"] = 0.9
                if current_intent in non_chat_intents and action_result.get("executed") and not action_result.get("error"):
                    response_text = action_result.get("action", f"{current_intent} completed")
                else:
                    try:
                        from brain.epistemic_tagger import epistemic_tagger
                        _vision_kw = ["screen", "screenshot", "see", "look", "what is on", "what's on", "what do you see", "what am i looking"]
                        _is_vision = any(kw in text.lower() for kw in _vision_kw)
                        if _is_vision or current_intent == "vision":
                            from core.llm_router import complete_vision
                            try:
                                from core.vision_agent import VisionAgent
                                agent = VisionAgent()
                                state = await agent._capture()
                                screen_desc = await agent._describe(state)
                                text += f"\n[SCREEN CAPTURE: {screen_desc}]"
                            except Exception as e:
                                logger.exception("[WS] Vision capture failed: %s", e)
                            vision_result = await complete_vision([
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": processed_query}], timeout=60)
                            resp_text = vision_result.unwrap_or("")
                            response_text = epistemic_tagger.tag_response(resp_text, ws_provenance)
                        else:
                            model_group = "cloud" if model == "cloud" else get_router_model(current_intent)
                            try:
                                resp = await get_router().acompletion(
                                    model=model_group,
                                    messages=[{"role": "system", "content": system_prompt},
                                              {"role": "user", "content": processed_query}],
                                    timeout=60,
                                )
                                response_text = epistemic_tagger.tag_response(resp.choices[0].message.content, ws_provenance)
                            except Exception as e:
                                logger.exception("[WS] LiteLLM fallback to Ollama: %s", e)
                                from core.model_router import get_ollama_url, model_for_role
                                model_obj = model_for_role(current_intent)
                                direct_url = get_ollama_url(model_obj)
                                import httpx
                                async with httpx.AsyncClient(timeout=60) as client:
                                    r = await client.post(f"{direct_url}/api/chat", json={
                                        "model": model_obj,
                                        "messages": [{"role": "system", "content": system_prompt},
                                                     {"role": "user", "content": processed_query}],
                                        "stream": False,
                                        "options": {"num_predict": 1024, "temperature": 0.7, "num_gpu": 99}})
                                    resp_text = r.json().get("message", {}).get("content", "")
                                response_text = epistemic_tagger.tag_response(resp_text, ws_provenance)
                    except Exception as e:
                        logger.exception("[WS] All LLM fallbacks failed: %s", e)
                        response_text = "I had a temporary issue processing that request."

                memory.store(
                    [{"role": "user", "content": text}, {"role": "assistant", "content": response_text}],
                    user_id=user_id,
                )

                for _, result in await plugin_registry.run_hook("before_agent_reply", reply=response_text):
                    if isinstance(result, str) and result:
                        response_text = result

                reply_payload = {
                    'type': 'stream_tokens',
                    'tokens': response_text.split(),
                    'privacy_tier': tier.value,
                    'model': model,
                    'intent': current_intent,
                }
                for _, result in await plugin_registry.run_hook("reply_payload_sending", payload=reply_payload):
                    if isinstance(result, dict):
                        reply_payload = result

                words = reply_payload.get("tokens", response_text.split())
                for i, word in enumerate(words):
                    await ws.send_json({
                        'type': 'stream_token',
                        'token': word + ' ',
                        'complete': i == len(words) - 1,
                        'privacy_tier': reply_payload.get("privacy_tier", tier.value),
                        'model': reply_payload.get("model", model),
                        'intent': reply_payload.get("intent", current_intent),
                    })

                await ws.send_json({
                    'type': 'tier_status',
                    'tier': f'Tier {reply_payload.get("privacy_tier", tier.value)}',
                    'status': 'completed',
                })

                await plugin_registry.run_hook("message_sent", message={"id": session_id, "text": response_text, "type": "response"})
            elif msg_type == 'ping':
                await ws.send_json({'type': 'pong'})
    except WebSocketDisconnect:
        await plugin_registry.run_hook("session_end", session_id=session_id, summary={"disconnect": "websocket_disconnect"})
        pass
    except Exception as e:
        logger.error('[WS Chat] Error: %s', e)
        await plugin_registry.run_hook("session_end", session_id=session_id, summary={"error": str(e)})
        try:
            await ws.close()
        except Exception as _e:
            logger.warning("[core.routes.websocket] handle_websocket_message failed: %s", _e)
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
    from core.agent_loop import stream_agent_loop
    from core.config import OLLAMA_MODEL, OLLAMA_URL
    from core.plugins import plugin_registry
    from core.settings_legacy import get_setting as _gs

    await ws.accept()
    session_id = str(id(ws))
    await plugin_registry.run_hook("session_start", session_id=session_id, metadata={"source": "agent_websocket"})
    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type")

            if msg_type == "chat":
                text = msg.get("text", "")
                if not text.strip():
                    continue

                pause_enabled = bool(_gs("pause_before_effectful", False))

                from core.config_registry import config as _c
                endpoint_url = _c.get("ollama.base_url")
                model = os.getenv("CHAT_MODEL") or _c.get("llm.chat_model")

                session_id = msg.get("session_id") or str(id(ws))
                from ..session import ConversationManager
                cm = ConversationManager(session_id=session_id)
                messages = []
                if cm.path.exists():
                    cm.load()
                    messages = cm.get_context(last_n=10)
                
                messages.append({"role": "user", "content": text})

                async for sse_event in stream_agent_loop(
                    endpoint_url=endpoint_url,
                    model=model,
                    messages=messages,
                    temperature=0.3,
                    max_tokens=4096,
                    session_id=session_id,
                    pause_before_effectful=pause_enabled,
                ):
                    if sse_event.startswith("data: [DONE]"):
                        await ws.send_json({"type": "stream_end"})
                        continue

                    if sse_event.startswith("data: "):
                        try:
                            payload = json.loads(sse_event[6:])
                        except json.JSONDecodeError:
                            continue

                        event_type = payload.get("type", "")

                        if event_type:
                            await ws.send_json(payload)
                            continue

                        delta = payload.get("delta", "")
                        if delta:
                            await ws.send_json({
                                "type": "stream_token",
                                "token": delta,
                                "complete": False,
                            })
                            continue

                    elif sse_event.startswith("event: "):
                        continue

                await ws.send_json({
                    "type": "stream_token",
                    "token": "",
                    "complete": True,
                })

            elif msg_type == "ping":
                await ws.send_json({"type": "pong"})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("[WS Agent] Error: %s", e)
        try:
            await ws.close()
        except Exception as _e:
            logger.warning("[core.routes.websocket] broadcast_event failed: %s", _e)
