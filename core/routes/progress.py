"""Progress API routes — REST + WebSocket for the AI Reasoning Canvas.

The progress canvas shows the user what MJ is doing right now in a
clickable tree of execution nodes. This API is the backend for that view.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from core.workflow.events import get_bus
from core.workflow.graph import ExecutionNode
from core.workflow.tracker import FocusMode, get_tracker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/progress", tags=["Progress"])


class AddNodeRequest(BaseModel):
    session_id: str
    label: str
    node_type: str = "task"
    parent_id: str | None = None
    trust_level: str = "safe"
    can_skip: bool = True
    estimate_seconds: int | None = None


class UpdateNodeRequest(BaseModel):
    session_id: str
    node_id: str
    status: str | None = None
    confidence: float | None = None
    detail: str | None = None
    estimate_seconds: int | None = None
    agent_reasoning: str | None = None
    error: str | None = None


class NewGoalRequest(BaseModel):
    goal: str


class SkipNodeRequest(BaseModel):
    session_id: str
    node_id: str


class RemoveNodeRequest(BaseModel):
    session_id: str
    node_id: str


class ReorderRequest(BaseModel):
    session_id: str
    parent_id: str | None = None
    node_id: str
    new_index: int


class FocusRequest(BaseModel):
    action: str  # pause, resume, enqueue
    session_id: str | None = None
    request: dict | None = None


# ── Goal endpoints ───────────────────────────────────────────────────────────


@router.post("/goal")
async def create_goal(req: NewGoalRequest):
    tracker = get_tracker()
    session_id = tracker.create_goal(req.goal)
    return {
        "session_id": session_id,
        "goal": req.goal,
        "goal_id": session_id,
    }


@router.get("/goals")
async def list_goals(status: str | None = None):
    tracker = get_tracker()
    goals = tracker.list_goals(status)
    return {"goals": goals}


@router.post("/goal/{session_id}/complete")
async def complete_goal(session_id: str):
    tracker = get_tracker()
    tracker.complete_goal(session_id)
    return {"status": "completed"}


@router.post("/goal/{session_id}/fail")
async def fail_goal(session_id: str, error: str = "failed"):
    tracker = get_tracker()
    tracker.fail_goal(session_id, error)
    return {"status": "failed"}


# ── Graph endpoints ──────────────────────────────────────────────────────────


@router.get("/graph/{session_id}")
async def get_graph(session_id: str):
    tracker = get_tracker()
    graph = tracker.get_graph(session_id)
    if not graph:
        raise HTTPException(status_code=404, detail="Session not found")
    return graph.to_dict()


@router.post("/node")
async def add_node(req: AddNodeRequest):
    tracker = get_tracker()
    node = tracker.add_node(
        session_id=req.session_id,
        parent_id=req.parent_id,
        label=req.label,
        node_type=req.node_type,
        trust_level=req.trust_level,
        can_skip=req.can_skip,
        estimate_seconds=req.estimate_seconds,
    )
    if not node:
        raise HTTPException(status_code=404, detail="Session not found")
    return node.to_dict()


@router.patch("/node")
async def update_node(req: UpdateNodeRequest):
    tracker = get_tracker()
    updates = {}
    for field in ("status", "confidence", "detail", "estimate_seconds", "agent_reasoning", "error"):
        val = getattr(req, field, None)
        if val is not None:
            updates[field] = val
    node = tracker.update_node(req.session_id, req.node_id, **updates)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return node.to_dict()


@router.post("/node/skip")
async def skip_node(req: SkipNodeRequest):
    tracker = get_tracker()
    node = tracker.update_node(req.session_id, req.node_id, status="skipped")
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return node.to_dict()


@router.post("/node/remove")
async def remove_node(req: RemoveNodeRequest):
    tracker = get_tracker()
    ok = tracker.remove_node(req.session_id, req.node_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Node not found")
    return {"status": "removed"}


@router.post("/node/reorder")
async def reorder_node(req: ReorderRequest):
    tracker = get_tracker()
    ok = tracker.reorder_node(req.session_id, req.parent_id or "", req.node_id, req.new_index)
    if not ok:
        raise HTTPException(status_code=400, detail="Reorder failed")
    return {"status": "reordered"}


@router.post("/node/{node_id}/detail")
async def set_node_detail(session_id: str, node_id: str, detail: str):
    tracker = get_tracker()
    node = tracker.set_node_detail(session_id, node_id, detail)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return node.to_dict()


# ── Focus endpoints ──────────────────────────────────────────────────────────


@router.get("/focus")
async def get_focus():
    tracker = get_tracker()
    return tracker.focus.to_dict()


@router.post("/focus")
async def set_focus(req: FocusRequest):
    tracker = get_tracker()
    focus = tracker.focus
    if req.action == "pause":
        focus.pause()
    elif req.action == "resume":
        focus.resume()
    elif req.action == "enqueue" and req.request:
        focus.enqueue(req.request)
    elif req.action == "dequeue":
        next_req = focus.dequeue()
        return {"next_request": next_req}
    return focus.to_dict()


# ── Event subscription WebSocket ─────────────────────────────────────────────


@router.websocket("/ws/{session_id}")
async def progress_websocket(ws: WebSocket, session_id: str):
    """Real-time execution graph updates for a specific session.

    Receives all MJEvent types for this session as JSON.
    """
    await ws.accept()
    bus = get_bus()
    bus.register_ws(ws, session_id=session_id)
    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            if msg.get("type") == "ping":
                await ws.send_text(json.dumps({"event": "pong", "session_id": session_id}))
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("Progress WebSocket error: %s", e)
    finally:
        bus.unregister_ws(ws)
