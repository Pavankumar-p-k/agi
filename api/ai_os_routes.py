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
import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any, Optional

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/ai_os", tags=["ai_os"])

_orchestrator: Optional["AIOrchestrator"] = None


def _get_orchestrator():
    global _orchestrator
    if _orchestrator is not None:
        return _orchestrator
    try:
        from ai_os.config import AIOSConfig
        from ai_os.orchestrator import AIOrchestrator
        _orchestrator = AIOrchestrator(AIOSConfig())
    except Exception as e:
        logger.warning("[api.ai_os_routes] orchestrator init failed: %s", e)
        _orchestrator = None
    return _orchestrator


class AIOSPrompt(BaseModel):
    prompt: str
    context: dict[str, Any] = Field(default_factory=dict)


def _require_orchestrator():
    o = _get_orchestrator()
    if o is None:
        raise HTTPException(status_code=503, detail="AI OS orchestrator not available (missing dependencies)")
    return o


async def event_stream_generator() -> AsyncGenerator[str, None]:
    """SSE event stream generator - streams real-time execution events."""
    o = _require_orchestrator()
    queue = o.event_bus.subscribe_stream()
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield f"data: {json.dumps(event)}\n\n"
            except TimeoutError:
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
            except Exception as e:
                logger.warning("[api.ai_os_routes] event stream error: %s", e)
                break
    finally:
        o.event_bus.unsubscribe_stream(queue)


@router.post("/execute")
async def execute_goal(req: AIOSPrompt):
    if not req.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt cannot be empty")
    o = _require_orchestrator()
    result = await o.run(req.prompt, req.context)
    status = 200 if result.get("success") else 400
    return {"status": status, "result": result}


@router.get("/events")
async def stream_events():
    _require_orchestrator()
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
    o = _require_orchestrator()
    return {
        "status": "ok",
        "model_router": o.model_router.status(),
        "tools": o.tools.as_dicts(),
        "policy_config": {
            "allow_apps": o.policy.allow_apps,
            "block_patterns": [p.pattern for p in o.policy.block_patterns],
        },
        "memory": {
            "short_term_count": len(o.memory.get_short_term()),
            "latest": o.memory.query("session", 1),
        },
    }
