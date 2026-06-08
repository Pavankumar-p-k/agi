import time
import json
import os
import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import verify_token
from ..database import get_db, User

logger = logging.getLogger("jarvis")

router = APIRouter(tags=["Chat"])

try:
    from routers.chat import chat_handler as three_pass_handler
except Exception:
    three_pass_handler = None


from ..schemas import ChatRequest


if three_pass_handler:
    @router.post("/api/chat")
    async def chat_route(req: ChatRequest):
        user_id = req.session_id or "default_user"

        from memory.memory_facade import memory
        memories = memory.recall(req.message, user_id=user_id, limit=5)
        memory_context = memory.format_context(memories)

        from tools.ragflow_tool import ragflow_search, format_rag_context
        rag_result = await ragflow_search(req.message, top_k=5)
        rag_context = format_rag_context(rag_result.get("chunks", []))

        combined_context = req.context or ""
        if memory_context:
            combined_context = memory_context + "\n\n" + combined_context
        if rag_context:
            combined_context = rag_context + "\n\n" + combined_context

        req.context = combined_context.strip()

        result = await three_pass_handler(req)

        response_text = result.get("response", "")
        memory.store(
            [{"role": "user", "content": req.message}, {"role": "assistant", "content": response_text}],
            user_id=user_id,
        )

        return result


@router.post("/api/agent/stream")
async def agent_stream(req: ChatRequest):
    from core.config import OLLAMA_URL, OLLAMA_MODEL
    from core.agent_loop import stream_agent_loop

    endpoint_url = OLLAMA_URL
    model = OLLAMA_MODEL or os.getenv("CHAT_MODEL", "qwen3:4b")

    messages: list[dict] = []
    if req.context:
        messages.append({"role": "system", "content": req.context})
    messages.append({"role": "user", "content": req.message})

    pause_enabled = False
    try:
        from core.settings_legacy import get_setting as _gs
        pause_enabled = bool(_gs("pause_before_effectful", False))
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
        if three_pass_handler:
            result = await three_pass_handler(req)
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
    session_id: Optional[str] = Query(None),
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
    from sqlalchemy import select, func
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

    from core.persistence.store import checkpoint_store
    from core.graph import build_default_graph, AgentState

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
