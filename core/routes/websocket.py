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
    from core.intent_router import extract_intent
    from core.llm_router import route_request
    try:
        from core.plugins import plugin_registry
    except Exception:
        plugin_registry = None
        logger.exception("[WS] plugin registry unavailable")

    import asyncio
    import traceback as _tb
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

                from ..context_builder import build_unified_context
                logger.info("WS_STAGE_2_CONTEXT_START")
                print("[WS] build_unified_context...", flush=True)
                try:
                    history_context = await asyncio.wait_for(
                        build_unified_context(text, session_id=session_id), timeout=8
                    )
                except asyncio.TimeoutError:
                    logger.warning("[WS] build_unified_context timed out (8s), skipping context")
                    history_context = ""
                print("[WS] build_unified_context done", flush=True)
                logger.info("WS_STAGE_2_CONTEXT_DONE")

                system_prompt = "You are JARVIS, your AI assistant. Be concise."
                if history_context:
                    system_prompt = history_context + "\n\n" + system_prompt

                print("[WS] route_request...", flush=True)
                model, tier, processed_query = route_request(text)
                print(f"[WS] route_request done: model={model}", flush=True)

                logger.info("WS_STAGE_3_INTENT_START")
                print("[WS] extract_intent...", flush=True)
                try:
                    intent_data = await asyncio.wait_for(extract_intent(processed_query), timeout=15)
                except asyncio.TimeoutError:
                    logger.warning("[WS] extract_intent timed out")
                    intent_data = {"intent": "chat", "confidence": 0.0}
                print(f"[WS] extract_intent done: intent={intent_data.get('intent')}", flush=True)
                logger.info("WS_STAGE_3_INTENT_DONE")
                from ..main import execute_action
                logger.info("WS_STAGE_4_REASON_START")
                print("[WS] execute_action...", flush=True)
                try:
                    action_result = await asyncio.wait_for(
                        execute_action(intent_data, message=text, session_id=session_id), timeout=15
                    )
                except asyncio.TimeoutError:
                    logger.warning("[WS] execute_action timed out")
                    action_result = {"executed": False, "error": "timeout", "action": ""}
                print("[WS] execute_action done", flush=True)
                logger.info("WS_STAGE_4_REASON_DONE")
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
                        from memory.memory_facade import memory
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
                            if vision_result.is_err():
                                logger.warning("[WS] vision_result error: %s", vision_result._error)
                                resp_text = "Vision model unavailable. Check that Ollama is running."
                            else:
                                resp_text = vision_result.unwrap()
                            response_text = epistemic_tagger.tag_response(resp_text, ws_provenance)
                        else:
                            import httpx
                            from core.llm_router import get_ollama_url, model_for_role
                            models_to_try = [
                                model_for_role(current_intent),
                                *["qwen2.5:7b", "llama3.1:8b", "qwen2.5-coder:3b", "tinyllama"],
                            ]
                            deduped = []
                            seen = set()
                            for m in models_to_try:
                                if m not in seen:
                                    seen.add(m)
                                    deduped.append(m)
                            resp_text = None
                            for model_obj in deduped:
                                ollama_chat_url = get_ollama_url(model_obj) + "/api/chat"
                                try:
                                    async with httpx.AsyncClient(timeout=30) as client:
                                        r = await client.post(ollama_chat_url, json={
                                            "model": model_obj,
                                            "messages": [{"role": "system", "content": system_prompt},
                                                         {"role": "user", "content": processed_query}],
                                            "stream": False,
                                            "options": {"num_predict": 1024, "temperature": 0.7}})
                                        r.raise_for_status()
                                        resp_text = r.json().get("message", {}).get("content", "")
                                        if resp_text:
                                            break
                                except Exception:
                                    continue
                            if resp_text:
                                response_text = epistemic_tagger.tag_response(resp_text, ws_provenance)
                            else:
                                response_text = (
                                    "Ollama is not running or no model is installed. "
                                    "Run `ollama pull qwen2.5:7b` to install a model, then refresh."
                                )
                    except Exception as e:
                        logger.exception("[WS] All LLM fallbacks failed: %s", e)
                        response_text = "I had a temporary issue processing that request."

                try:
                    memory.store(
                        [{"role": "user", "content": text}, {"role": "assistant", "content": response_text}],
                        user_id=user_id,
                    )
                except Exception as e:
                    logger.warning("[WS] memory.store failed: %s", e)

                if plugin_registry:
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
                if plugin_registry:
                    for _, result in await plugin_registry.run_hook("reply_payload_sending", payload=reply_payload):
                        if isinstance(result, dict):
                            reply_payload = result

                words = reply_payload.get("tokens", response_text.split())
                for i, word in enumerate(words):
                    is_last = i == len(words) - 1
                    await ws.send_json({
                        'type': 'stream_token',
                        'token': word + ' ',
                        'complete': is_last,
                        'privacy_tier': reply_payload.get("privacy_tier", tier.value),
                        'model': reply_payload.get("model", model),
                        'intent': reply_payload.get("intent", current_intent),
                        'tier_status': f'Tier {reply_payload.get("privacy_tier", tier.value)}' if is_last else None,
                    })

                if plugin_registry:
                    await plugin_registry.run_hook("message_sent", message={"id": session_id, "text": response_text, "type": "response"})
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
    from core.agent_loop import stream_agent_loop
    from core.configuration import configuration
    from core.plugins import plugin_registry
    from core.routing import classify_request, RequestMode, Classification, get_context_manager, SafetyLevel, classify_tool
    from core.routing.project_context import ProjectContext

    await ws.accept()
    session_id = str(id(ws))
    _ws_connected = time.time()
    _time_first_token = 0.0
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
                _p0 = time.perf_counter()

                from ..session import ConversationManager
                conv = ConversationManager(session_id=session_id)
                messages = []
                if conv.path.exists():
                    conv.load()
                    messages = conv.get_context(last_n=10)
                _p_mem = time.perf_counter()
                logger.info("[PROFILE] conv_load %.3fs", _p_mem - _p0)

                # Classify request
                classification = classify_request(text)
                _p_cls = time.perf_counter()
                logger.info("[PROFILE] classify %.3fs", _p_cls - _p_mem)
                await ws.send_json({
                    "type": "classification",
                    "mode": classification.mode.value,
                    "sub_type": classification.sub_type or "",
                    "confidence": classification.confidence,
                })

                mode = classification.mode
                sub_type = classification.sub_type

                # ── DIRECT mode: fast handlers ─────────────────────────
                if mode == RequestMode.DIRECT:
                    from ..main import execute_action
                    from core.intent_router import extract_intent
                    intent_data = {"intent": text.split()[0] if text else "chat", "target": text}
                    try:
                        result = await execute_action(intent_data, message=text, session_id=session_id)
                        response_text = result.get("action", str(result.get("result", "Done.")))
                    except Exception as e:
                        response_text = f"Error: {e}"
                    await ws.send_json({"type": "stream_token", "token": response_text, "complete": True})
                    await ws.send_json({"type": "stream_end"})
                    conv.add_message("user", text)
                    conv.add_message("assistant", response_text)
                    conv.save()
                    continue

                # ── ACTION mode: fast path (no StateGraph) ─────────────
                if mode == RequestMode.ACTION:
                    result = await _fast_execute_action(text, sub_type, session_ctx, session_id, ws)
                    if result is not None:
                        await ws.send_json({"type": "stream_end"})
                        summary = result.get("summary", "Done.")
                        conv.add_message("user", text)
                        conv.add_message("assistant", summary)
                        conv.save()
                        continue
                    # Fast path failed → fall through to agent loop

                # ── Inject project context into system prompt ──────────
                project_block = ""
                if session_ctx:
                    ctx = session_ctx
                    project_block = (
                        f"\n## CURRENT PROJECT\n"
                        f"cwd: {ctx.cwd}\n"
                        f"git: {bool(ctx.git_root)} | branch: {ctx.branch}\n"
                        f"languages: {', '.join(ctx.languages)}\n"
                        f"build system: {', '.join(ctx.build_system)}\n"
                        f"project type: {ctx.project_type}\n"
                    )

                # Build appropriate system prompt for mode
                if mode == RequestMode.CODEBASE:
                    sys_extra = (
                        "\n## CODEBASE ANALYSIS\n"
                        "You are analyzing a codebase. Search files, read code, "
                        "and synthesize your findings. Provide file paths and summaries.\n"
                        "Do not execute shell commands unless necessary.\n"
                    )
                elif mode == RequestMode.ACTION:
                    sys_extra = (
                        "\n## TOOL-FIRST EXECUTION\n"
                        "When the user asks you to perform an action:\n"
                        "1. Select the appropriate tool immediately.\n"
                        "2. Execute it.\n"
                        "3. Return the result.\n\n"
                        "DO NOT:\n"
                        "- Explain what command you would run\n"
                        "- Describe the steps you would take\n"
                        "- Suggest the user run a command themselves\n\n"
                        "ONLY explain when the user explicitly asks 'how' or 'explain'.\n"
                    )
                elif mode == RequestMode.AGENT:
                    sys_extra = (
                        "\n## FULL AGENT MODE\n"
                        "You are in full agent mode. Plan, execute, verify, and iterate.\n"
                        "Show progress with step-by-step visibility.\n"
                    )
                else:
                    sys_extra = ""

                system_prompt = f"You are JARVIS, an autonomous coding agent. Be concise and helpful.{project_block}{sys_extra}"
                messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": text})

                session = cm.get_session(session_id)
                session.last_commands.append(text)
                if len(session.last_commands) > 20:
                    session.last_commands.pop(0)

                endpoint_url = configuration.get("ollama.base_url")
                model = os.getenv("CHAT_MODEL") or configuration.get("llm.chat_model")

                pause_enabled = False
                try:
                    from core.configuration import configuration
                    pause_enabled = bool(configuration.get("pause_before_effectful", False))
                except Exception:
                    pass

                _p_prep = time.perf_counter()
                logger.info("[PROFILE] prep_before_agent %.3fs (classify+context+prompt)", _p_prep - _p_cls)

                # Send phase_change to keep WS alive while agent loop initializes
                _agent_start = time.time()
                await ws.send_json({"type": "phase_change", "phase": "thinking", "message": "Processing your request..."})
                logger.info("[WS Agent] agent loop starting (%.2fs after connect)", _agent_start - _ws_connected)

                full_response = ""
                _p_agent = time.perf_counter()
                _token_count = 0
                async for sse_event in stream_agent_loop(
                    endpoint_url=endpoint_url,
                    model=model,
                    messages=messages,
                    temperature=0.3,
                    max_tokens=4096,
                    session_id=session_id,
                    pause_before_effectful=pause_enabled,
                    mode=mode.value,
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

                        # Log first meaningful event from agent
                        if _time_first_token == 0.0 and (event_type or payload.get("delta")):
                            _time_first_token = time.perf_counter()
                            _ttft = time.time() - _agent_start
                            logger.info("[PROFILE] ttft_agent %.3fs (%.2fs wall) type=%s", _time_first_token - _p_agent, _ttft, event_type or "delta")

                        if event_type:
                            if event_type == "phase_change":
                                continue  # skip internal phase changes, send our own
                            await ws.send_json(payload)
                            continue

                        delta = payload.get("delta", "")
                        if delta:
                            full_response += delta
                            _token_count += 1
                            await ws.send_json({
                                "type": "stream_token",
                                "token": delta,
                                "complete": False,
                            })
                            continue

                    elif sse_event.startswith("event: "):
                        continue

                _p_done = time.perf_counter()
                _agent_dur = _p_done - _p_agent
                _tok_sec = _token_count / _agent_dur if _agent_dur > 0 else 0
                _ttft_val = _time_first_token - _p_agent if _time_first_token > 0 else 0
                logger.info("[PROFILE] agent_loop %.3fs tokens=%d tok/s=%.1f ttft=%.3fs",
                    _agent_dur, _token_count, _tok_sec, _ttft_val)
                logger.info("[WS Agent] agent loop finished (total=%.2fs)", time.time() - _ws_connected)
                await ws.send_json({
                    "type": "stream_token",
                    "token": "",
                    "complete": True,
                })

                _p_save = time.perf_counter()
                conv.add_message("user", text)
                conv.add_message("assistant", full_response)
                conv.save()
                logger.info("[PROFILE] conv_save %.3fs", time.perf_counter() - _p_save)

                _p_end = time.perf_counter()
                logger.info("[PROFILE] TOTAL_REQUEST %.3fs (ws_recv->done)", _p_end - _p0)
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


async def _fast_execute_action(text: str, sub_type: str | None, ctx: ProjectContext | None, session_id: str, ws: WebSocket) -> dict | None:
    """Fast path for simple actions — no LLM, no StateGraph."""
    lowered = text.lower().strip()
    cwd = ctx.cwd if ctx else os.getcwd()

    try:
        # ACTION_FILE: list files
        if sub_type == "ACTION_FILE" and any(kw in lowered for kw in ("list", "ls", "dir", "show files", "display")):
            import subprocess, platform
            cmd = ["cmd", "/c", "dir", "/b"] if platform.system() == "Windows" else ["ls", "-la"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, cwd=cwd)
            output = result.stdout if result.stdout else result.stderr
            await ws.send_json({"type": "tool_start", "tool": "shell", "args": cmd, "safety": "SAFE"})
            for line in output.splitlines():
                await ws.send_json({"type": "stream_token", "token": line + "\n", "complete": False})
            await ws.send_json({"type": "tool_end", "tool": "shell", "result": f"Listed {len(output.splitlines())} entries", "exit_code": result.returncode})
            return {"exit_code": 0, "summary": f"Listed {len(output.splitlines())} entries"}

        # ACTION_FILE: read file
        if sub_type == "ACTION_FILE" and lowered.startswith("read "):
            fname = text[5:].strip().strip("\"'")
            fpath = os.path.join(cwd, fname)
            if not os.path.exists(fpath):
                await ws.send_json({"type": "error", "message": f"File not found: {fname}"})
                return {"exit_code": 1, "summary": f"File not found: {fname}"}
            if not os.path.abspath(fpath).startswith(os.path.abspath(cwd)):
                await ws.send_json({"type": "error", "message": "Path traversal denied"})
                return {"exit_code": 1, "summary": "Path traversal denied"}
            safety = classify_tool("read_file", fname)
            if safety == SafetyLevel.CONFIRM:
                await ws.send_json({"type": "tool_confirm", "tool": "read_file", "args": fname, "safety": "CONFIRM", "prompt": f"Read {fname}?"})
            try:
                with open(fpath, encoding="utf-8", errors="replace") as f:
                    content = f.read()
                await ws.send_json({"type": "tool_start", "tool": "read_file", "args": fname, "safety": "SAFE"})
                await ws.send_json({"type": "stream_token", "token": content, "complete": False})
                await ws.send_json({"type": "tool_end", "tool": "read_file", "result": f"Read {fname} ({len(content)} chars)", "exit_code": 0})
            except Exception as e:
                await ws.send_json({"type": "error", "message": "Failed to read file"})
            return {"exit_code": 0, "summary": f"Read {fname}"}

        # ACTION_SHELL: direct shell commands (git, npm, poetry, pytest, etc.)
        if sub_type == "ACTION_SHELL":
            import subprocess, platform, shlex
            is_windows = platform.system() == "Windows"

            # Map common commands
            if any(kw in lowered for kw in ("git status",)):
                cmd = ["git", "status"]
            elif any(kw in lowered for kw in ("git diff",)):
                cmd = ["git", "diff"]
            elif any(kw in lowered for kw in ("git log",)):
                cmd = ["git", "log", "--oneline", "-10"]
            elif any(kw in lowered for kw in pytest for pytest in ("pytest ", "run tests",)):
                cmd = ["pytest"]
            elif any(kw in lowered for kw in ("npm install",)):
                cmd = ["npm", "install"]
            elif any(kw in lowered for kw in ("npm build", "npm run build")):
                cmd = ["npm", "run", "build"]
            elif any(kw in lowered for kw in ("poetry build",)):
                cmd = ["poetry", "build"]
            elif any(kw in lowered for kw in ("poetry install",)):
                cmd = ["poetry", "install"]
            elif lowered.startswith("git "):
                cmd = text.split()
            else:
                return None  # Unrecognized → fallback to agent loop

            safety = classify_tool("shell", " ".join(cmd))
            if safety == SafetyLevel.DANGEROUS:
                await ws.send_json({"type": "error", "message": f"Dangerous command rejected: {' '.join(cmd)}"})
                return {"exit_code": 1, "summary": "Dangerous command rejected"}

            await ws.send_json({"type": "tool_start", "tool": "shell", "args": " ".join(cmd), "safety": safety.value})
            shell_output = ""
            shell_exit = 0
            try:
                _result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=cwd)
                shell_output = _result.stdout if _result.stdout else _result.stderr
                shell_exit = _result.returncode
                for line in shell_output.splitlines():
                    await ws.send_json({"type": "stream_token", "token": line + "\n", "complete": False})
                await ws.send_json({"type": "tool_end", "tool": "shell", "result": f"Exit code: {shell_exit}", "exit_code": shell_exit})
            except subprocess.TimeoutExpired:
                await ws.send_json({"type": "error", "message": "Command timed out (120s)"})
                return {"exit_code": 1, "summary": "Command timed out"}
            except FileNotFoundError:
                await ws.send_json({"type": "error", "message": f"Command not found: {cmd[0]}"})
                return {"exit_code": 1, "summary": f"Command not found: {cmd[0]}"}
            return {"exit_code": shell_exit, "summary": f"Ran {' '.join(cmd)} (exit {shell_exit})"}

        # ACTION_BROWSER: open chrome / search
        if sub_type == "ACTION_BROWSER":
            import webbrowser, urllib.parse
            if "search google" in lowered or "search for" in lowered:
                query = text.lower().replace("search google for", "").replace("search google", "").replace("search for", "").strip()
                url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
            elif "search amazon" in lowered:
                query = text.lower().replace("search amazon for", "").replace("search amazon", "").strip()
                url = f"https://www.amazon.com/s?k={urllib.parse.quote(query)}"
            else:
                url = text.strip()
                if not url.startswith("http"):
                    url = "https://" + url
            webbrowser.open(url)
            await ws.send_json({"type": "tool_start", "tool": "browser", "args": url, "safety": "SAFE"})
            await ws.send_json({"type": "stream_token", "token": f"Opened: {url}\n", "complete": False})
            await ws.send_json({"type": "tool_end", "tool": "browser", "result": f"Opened {url}", "exit_code": 0})
            return {"exit_code": 0, "summary": f"Opened {url}"}

        # ACTION_SYSTEM: open chrome/applications
        if sub_type == "ACTION_SYSTEM":
            import subprocess, platform
            if "chrome" in lowered or "browser" in lowered:
                if platform.system() == "Windows":
                    subprocess.Popen(["cmd", "/c", "start", "chrome"])
                elif platform.system() == "Darwin":
                    subprocess.Popen(["open", "-a", "Google Chrome"])
                else:
                    subprocess.Popen(["google-chrome"])
                await ws.send_json({"type": "tool_start", "tool": "system", "args": "open chrome", "safety": "SAFE"})
                await ws.send_json({"type": "stream_token", "token": "Chrome launched\n", "complete": False})
                await ws.send_json({"type": "tool_end", "tool": "system", "result": "Chrome launched", "exit_code": 0})
                return {"exit_code": 0, "summary": "Chrome launched"}
            if "vscode" in lowered or "code" in lowered:
                subprocess.Popen(["code", cwd])
                await ws.send_json({"type": "tool_start", "tool": "system", "args": "launch vscode", "safety": "SAFE"})
                await ws.send_json({"type": "stream_token", "token": "VS Code launched\n", "complete": False})
                await ws.send_json({"type": "tool_end", "tool": "system", "result": "VS Code launched", "exit_code": 0})
                return {"exit_code": 0, "summary": "VS Code launched"}

    except Exception as e:
        logger.warning("[fast_execute] error: %s", e)
        return None

    return None


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
