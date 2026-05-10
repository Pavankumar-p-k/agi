from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Any, AsyncGenerator
import json
import asyncio

# Import from ai_os module (sibling package in backend)
from ai_os.orchestrator import AIOrchestrator
from ai_os.config import AIOSConfig

router = APIRouter(prefix="/ai_os", tags=["ai_os"])

orchestrator = AIOrchestrator(AIOSConfig())

class AIOSPrompt(BaseModel):
    prompt: str
    context: dict[str, Any] = Field(default_factory=dict)


async def event_stream_generator() -> AsyncGenerator[str, None]:
    """SSE event stream generator - streams real-time execution events."""
    queue = orchestrator.event_bus.subscribe_stream()
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                # Format as SSE: "data: {...}\n\n"
                yield f"data: {json.dumps(event)}\n\n"
            except asyncio.TimeoutError:
                # Send heartbeat every 30s
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
            except Exception:
                break
    finally:
        orchestrator.event_bus.unsubscribe_stream(queue)


@router.post("/execute")
async def execute_goal(req: AIOSPrompt):
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt cannot be empty")
    result = await orchestrator.run(req.prompt, req.context)
    status = 200 if result.get("success") else 400
    return {"status": status, "result": result}


@router.get("/events")
async def stream_events():
    """Server-Sent Events endpoint for real-time event streaming."""
    return StreamingResponse(
        event_stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@router.get("/status")
async def status():
    return {
        "status": "ok",
        "model_router": orchestrator.model_router.status(),
        "tools": orchestrator.tools.catalog(),
        "policy_config": {
            "allow_apps": orchestrator.policy.allow_apps,
            "block_patterns": [p.pattern for p in orchestrator.policy.block_patterns],
        },
        "memory": {
            "short_term_count": len(orchestrator.memory.get_short_term()),
            "latest": orchestrator.memory.query("session", 1),
        },
    }
