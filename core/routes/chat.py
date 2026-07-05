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
import logging
import os
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import verify_token
from ..database import User, get_db

logger = logging.getLogger("jarvis")

router = APIRouter(tags=["Chat"])

from ..schemas import ChatRequest
from memory.memory_facade import memory

# Lazy getter for three_pass_handler (heavy ~2.5s import, deferred until first request)
_three_pass_handler = None
def _get_three_pass_handler():
    global _three_pass_handler
    if _three_pass_handler is None:
        try:
            from routers.chat import chat_handler as h
            _three_pass_handler = h
        except Exception as e:
            logger.warning("[core.routes.chat] three-pass handler import failed: %s", e)
            _three_pass_handler = False
    return _three_pass_handler if _three_pass_handler is not False else None


@router.post("/api/chat")
async def chat_route(
    req: ChatRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token)
):
    user_id = req.session_id or "default_user"

    # ── Canonical pipeline path (preferred) ──────────────────────────────
    try:
        from core.pipeline.adapters import rest_adapter
        result = await rest_adapter(
            message=req.message,
            user_id=user_id,
            session_id=req.session_id,
            context=req.context,
        )
        if not result.get("response", "").startswith("Error:"):
            response_text = result.get("response", "")
            _persist_chat(req, result, response_text, db, user, user_id)
            return result
        # Pipeline returned error — fall through
    except Exception as exc:
        logger.warning("Pipeline unavailable for REST, falling back: %s", exc)

    # ── Legacy three-pass handler (backward compat) ──────────────────────
    handler = _get_three_pass_handler()
    if handler is None:
        return {"response": "Chat handler not available."}
    result = await handler(req)
    response_text = result.get("response", "")
    _persist_chat(req, result, response_text, db, user, user_id)
    # Legacy path needs explicit memory write (pipeline's MemoryStage
    # handles this for the pipeline path).
    try:
        memory.store(
            [{"role": "user", "content": req.message}, {"role": "assistant", "content": response_text}],
            user_id=user_id,
        )
    except Exception:
        logger.debug("memory.store (legacy) failed")
    return result


def _persist_chat(
    req: ChatRequest,
    result: dict,
    response_text: str,
    db: AsyncSession,
    user: User,
    user_id: str,
) -> None:
    """Persist conversation history to database.

    SQLite persistence is a REST API concern (needed for ``/api/chat/history``).
    Memory persistence is handled by the pipeline's MemoryStage when the
    canonical pipeline processes the request, or by the legacy handler
    inline.
    """

    # Immediate persistence to SQLite
    from core.database import ChatHistory
    db.add(ChatHistory(
        user_id=user.id,
        role="user",
        message=req.message,
        session_id=req.session_id,
        intent=result.get("intent", {}).get("intent", "chat")
    ))
    db.add(ChatHistory(
        user_id=user.id,
        role="assistant",
        message=response_text,
        session_id=req.session_id,
        intent=result.get("intent", {}).get("intent", "chat")
    ))
    await db.commit()


@router.post("/api/agent/stream")
async def agent_stream(req: ChatRequest):
    from core.agent_loop import stream_agent_loop
    from core.configuration import configuration

    endpoint_url = configuration.get("ollama.base_url")
    model = os.getenv("CHAT_MODEL") or configuration.get("llm.chat_model")

    messages: list[dict] = []
    if req.context:
        messages.append({"role": "system", "content": req.context})
    messages.append({"role": "user", "content": req.message})

    pause_enabled = False
    try:
        from core.configuration import configuration
        pause_enabled = bool(configuration.get("pause_before_effectful", False))
    except Exception as e:
        logger.warning("[core.routes.chat] process_chat_message failed: %s", e)

    async def _generate():
        async for event in stream_agent_loop(
            endpoint_url=endpoint_url,
            model=model,
            messages=messages,
            temperature=0.3,
            max_tokens=4096,
            session_id=req.session_id,
            pause_before_effectful=pause_enabled,
        ):
            yield event

    return StreamingResponse(_generate(), media_type="text/event-stream")


@router.post("/v1/chat/completions")
async def openai_compat(body: dict):
    messages = body.get("messages", [])
    if not messages:
        raise HTTPException(400, "No messages provided")

    last_msg = messages[-1].get("content", "")
    context = "\n".join([f"{m['role']}: {m['content']}" for m in messages[:-1]])

    req = ChatRequest(message=last_msg, context=context)

    try:
        handler = _get_three_pass_handler()
        if handler:
            result = await handler(req)
            content = result.get("response", "")
        else:
            from core.llm_router import complete
            res = await complete(last_msg, context=context)
            content = res.unwrap_or("Error processing request.")

        return {
            "id": f"chatcmpl-{uuid.uuid4()}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": body.get("model", "jarvis-reasoning"),
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": len(last_msg) // 4,
                "completion_tokens": len(content) // 4,
                "total_tokens": (len(last_msg) + len(content)) // 4
            }
        }
    except Exception as e:
        logger.error(f"[OpenAI Compat] Error: {e}")
        raise HTTPException(500, str(e))


@router.get("/api/chat/history")
async def get_chat_history(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
    limit: int = 50,
    session_id: str | None = Query(None),
):
    from sqlalchemy import select

    from core.database import ChatHistory
    q = select(ChatHistory).where(ChatHistory.user_id == user.id)
    if session_id:
        q = q.where(ChatHistory.session_id == session_id)
    result = await db.execute(
        q.order_by(ChatHistory.timestamp.desc()).limit(limit)
    )
    messages = result.scalars().all()
    return [{"role": m.role, "message": m.message, "ts": m.timestamp} for m in reversed(messages)]


@router.get("/api/sessions")
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
):
    from sqlalchemy import func, select

    from core.database import ChatHistory
    result = await db.execute(
        select(ChatHistory.session_id, func.count(ChatHistory.id), func.min(ChatHistory.timestamp), func.max(ChatHistory.timestamp))
        .where(ChatHistory.user_id == user.id)
        .where(ChatHistory.session_id.isnot(None))
        .group_by(ChatHistory.session_id)
        .order_by(func.max(ChatHistory.timestamp).desc())
    )
    return [
        {"session_id": row[0], "count": row[1], "first": row[2].isoformat() if row[2] else None, "last": row[3].isoformat() if row[3] else None}
        for row in result
    ]


@router.post("/api/agent/resume/{run_id}")
async def agent_resume(run_id: str, req: dict):
    action = req.get("action", "")
    if action not in ("approve", "reject"):
        raise HTTPException(400, "action must be 'approve' or 'reject'")

    from core.graph import build_default_graph
    from core.persistence.store import checkpoint_store

    state = checkpoint_store.load_agent_state(run_id)
    if not state:
        raise HTTPException(404, f"No paused agent state found for run {run_id}")

    state.resume_action = action
    state.resume_feedback = req.get("feedback", "")

    async def _stream():
        graph = build_default_graph()
        async for event in graph.execute(state):
            yield event

    return StreamingResponse(_stream(), media_type="text/event-stream")
