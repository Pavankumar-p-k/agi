"""core/routes/activity.py — REST API + WebSocket for the Activity Graph.

Exposes ActivityManager, ActivityStore, and ResumeEngine as HTTP endpoints.
Enables frontends to inspect, search, and control activity execution.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

import importlib as _il
ActivityManager = _il.import_module("core.activity.manager").ActivityManager
_as_mod = _il.import_module("core.activity.models")
ActivityEdge = _as_mod.ActivityEdge
ActivityNode = _as_mod.ActivityNode
ActivityStatus = _as_mod.ActivityStatus
from core.activity.replay import ReplayAssembler, ReplayDAG, ReplayNode
from core.activity.resume import ResumeEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/activity", tags=["Activity Graph"])

# ── Singleton instances ─────────────────────────────────────────────────────

_manager: ActivityManager | None = None
_resume: ResumeEngine | None = None

# WebSocket subscriptions: activity_id -> set of WebSocket connections
_ws_subscriptions: dict[str, set[WebSocket]] = {}


def _get_manager() -> ActivityManager:
    global _manager
    if _manager is None:
        _manager = ActivityManager()
    return _manager


def _get_resume() -> ResumeEngine:
    global _resume
    if _resume is None:
        _resume = ResumeEngine(_get_manager())
    return _resume


# ── Pydantic response models ────────────────────────────────────────────────


class ActivityNodeResponse(BaseModel):
    node_id: str
    activity_id: str
    node_type: str
    label: str
    status: str
    depth: int
    parent_id: str | None = None
    agent_id: str | None = None
    origin_node_id: str | None = None
    artifacts: dict[str, str] = {}
    workflow_id: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    created_at: str | None = None
    metadata: dict[str, Any] = {}


class ActivityEdgeResponse(BaseModel):
    edge_id: str
    from_node_id: str
    to_node_id: str
    edge_type: str
    created_at: str | None = None


class ActivityTreeResponse(BaseModel):
    nodes: list[ActivityNodeResponse]
    edges: list[ActivityEdgeResponse]


class ActivitySummaryResponse(BaseModel):
    activity_id: str
    goal: str | None = None
    status: str | None = None
    total_nodes: int = 0
    by_status: dict[str, int] = {}
    by_type: dict[str, int] = {}
    depth: int = 0
    agents_used: list[str] = []
    created_at: str | None = None


class ResumeContextResponse(BaseModel):
    activity_id: str
    target_node: ActivityNodeResponse
    ancestors: list[ActivityNodeResponse] = []
    accumulated_artifacts: dict[str, str] = {}
    accumulated_input: dict[str, Any] = {}


class ActivityCountsResponse(BaseModel):
    total: int
    running: int
    pending: int
    completed: int
    failed: int
    suspended: int
    cancelled: int


# ── Request models ──────────────────────────────────────────────────────────


class GoalRequest(BaseModel):
    goal: str


class PauseRequest(BaseModel):
    activity_id: str


class CancelRequest(BaseModel):
    activity_id: str
    error: str = "cancelled by user"


# ── Serialization helpers ───────────────────────────────────────────────────


def _node_to_response(n: ActivityNode) -> ActivityNodeResponse:
    return ActivityNodeResponse(
        node_id=n.node_id,
        activity_id=n.activity_id,
        node_type=n.node_type,
        label=n.label,
        status=n.status.value,
        depth=n.depth,
        parent_id=n.parent_id,
        agent_id=n.agent_id,
        origin_node_id=n.origin_node_id,
        artifacts=n.artifacts,
        workflow_id=n.workflow_id,
        started_at=n.started_at.isoformat() if n.started_at else None,
        completed_at=n.completed_at.isoformat() if n.completed_at else None,
        created_at=n.created_at.isoformat() if n.created_at else None,
        metadata=n.metadata,
    )


def _edge_to_response(e: ActivityEdge) -> ActivityEdgeResponse:
    return ActivityEdgeResponse(
        edge_id=e.edge_id,
        from_node_id=e.from_node_id,
        to_node_id=e.to_node_id,
        edge_type=e.edge_type,
        created_at=e.created_at.isoformat() if e.created_at else None,
    )


# ── Replay DAG serialization ──────────────────────────────────────────────


def _replay_node_to_dict(n: ReplayNode) -> dict[str, Any]:
    """Serialize a ReplayNode to a flat JSON-safe dict with child IDs."""
    return {
        "node_id": n.node_id,
        "activity_id": n.activity_id,
        "node_type": n.node_type,
        "label": n.label,
        "status": n.status,
        "depth": n.depth,
        "parent_id": n.parent_id,
        "agent_id": n.agent_id,
        "workflow_id": n.workflow_id,
        "started_at": n.started_at,
        "completed_at": n.completed_at,
        "duration_seconds": n.duration_seconds,
        "tool": n.tool,
        "provider": n.provider,
        "model": n.model,
        "retry_count": n.retry_count,
        "cost": n.cost,
        "input_preview": n.input_preview,
        "output_preview": n.output_preview,
        "error": n.error,
        "children": [c.node_id for c in n.children],
        "timeline_index": n.timeline_index,
        "metadata": n.metadata,
        "artifacts": n.artifacts,
    }


def _replay_dag_to_dict(dag: ReplayDAG) -> dict[str, Any]:
    """Serialize a ReplayDAG to a JSON-safe dict with flat node map."""
    return {
        "activity_id": dag.activity_id,
        "root_id": dag.root.node_id if dag.root else None,
        "all_nodes": {
            nid: _replay_node_to_dict(n)
            for nid, n in dag.all_nodes.items()
        },
        "all_edges": [dataclasses.asdict(e) for e in dag.all_edges],
        "timeline": [dataclasses.asdict(e) for e in dag.timeline],
        "decisions": [_decision_trace_to_dict(d) for d in dag.decisions],
        "total_nodes": dag.total_nodes,
        "failed_nodes": dag.failed_nodes,
        "total_duration_seconds": dag.total_duration_seconds,
        "unique_tools": dag.unique_tools,
        "unique_providers": dag.unique_providers,
        "total_retries": dag.total_retries,
        "total_cost": dag.total_cost,
        "experience": dag.experience,
        "knowledge": dag.knowledge,
    }


def _decision_trace_to_dict(d: Any) -> dict[str, Any]:
    """Serialize a DecisionTrace to a JSON-safe dict."""
    base = dataclasses.asdict(d)
    base["outcome"] = dataclasses.asdict(d.outcome) if d.outcome else None
    return base


# ── WebSocket broadcast ─────────────────────────────────────────────────────


async def _broadcast(activity_id: str, event: dict[str, Any]) -> None:
    """Push an event to all WebSocket clients subscribed to an activity."""
    subs = _ws_subscriptions.get(activity_id, set())
    if not subs:
        return
    message = json.dumps(event)
    stale: list[WebSocket] = []
    for ws in subs:
        try:
            await ws.send_text(message)
        except Exception:
            stale.append(ws)
    for ws in stale:
        subs.discard(ws)


async def _broadcast_active(event: dict[str, Any]) -> None:
    """Push an event to all clients subscribed to the 'active' feed."""
    await _broadcast("__active__", event)


# ── REST Endpoints ──────────────────────────────────────────────────────────


@router.get("")
async def list_active_activities():
    """Return all root-level activities that are still in progress."""
    mgr = _get_manager()
    nodes = mgr.get_active_activities()
    return {"activities": [_node_to_response(n) for n in nodes]}


@router.get("/counts")
async def activity_counts():
    """Return aggregate counts of activities by status."""
    mgr = _get_manager()
    nodes = mgr.get_active_activities()
    all_nodes = mgr.store.get_activity_tree
    total = 0
    running = 0
    pending = 0
    completed = 0
    failed = 0
    suspended = 0
    cancelled = 0
    for n in nodes:
        total += 1
        counts = mgr.store.count_by_status(n.activity_id)
        running += counts.get("RUNNING", 0)
        pending += counts.get("PENDING", 0)
        completed += counts.get("COMPLETED", 0)
        failed += counts.get("FAILED", 0)
        suspended += counts.get("SUSPENDED", 0)
        cancelled += counts.get("CANCELLED", 0)
    return ActivityCountsResponse(
        total=total,
        running=running,
        pending=pending,
        completed=completed,
        failed=failed,
        suspended=suspended,
        cancelled=cancelled,
    )


@router.get("/search")
async def search_activities(q: str, limit: int = 20):
    """Search activity nodes by label (LIKE match)."""
    mgr = _get_manager()
    nodes = mgr.store.search_nodes(q, limit)
    return {"results": [_node_to_response(n) for n in nodes]}


@router.get("/by-agent/{agent_id}")
async def get_activities_by_agent(agent_id: str, limit: int = 50):
    """Return nodes associated with a specific agent."""
    mgr = _get_manager()
    nodes = mgr.store.get_nodes_by_agent(agent_id, limit)
    return {"nodes": [_node_to_response(n) for n in nodes]}


@router.get("/{activity_id}")
async def get_activity(activity_id: str):
    """Get a single activity node by ID."""
    mgr = _get_manager()
    node = mgr.get_activity(activity_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"Activity {activity_id} not found")
    return _node_to_response(node)


@router.get("/{activity_id}/tree")
async def get_activity_tree(activity_id: str):
    """Return the full activity tree (nodes + edges)."""
    mgr = _get_manager()
    nodes = mgr.get_tree(activity_id)
    if not nodes:
        raise HTTPException(status_code=404, detail=f"Activity {activity_id} not found")
    edges: list[ActivityEdge] = []
    seen: set[str] = set()
    for n in nodes:
        for e in mgr.store.get_outgoing_edges(n.node_id):
            edges.append(e)
            seen.add(e.edge_id)
    return ActivityTreeResponse(
        nodes=[_node_to_response(n) for n in nodes],
        edges=[_edge_to_response(e) for e in edges],
    )


@router.get("/{activity_id}/replay")
async def get_activity_replay(activity_id: str):
    """Return the full ReplayDAG produced by ReplayAssembler.

    Contains the execution DAG, chronological timeline, decision traces,
    provider/tool/workflow metadata, and summary metrics.
    """
    mgr = _get_manager()
    store = mgr.store

    # Verify activity exists
    nodes = mgr.get_tree(activity_id)
    if not nodes:
        raise HTTPException(status_code=404, detail=f"Activity {activity_id} not found")

    try:
        assembler = ReplayAssembler(activity_store=store)
        dag = assembler.build(activity_id)
        return _replay_dag_to_dict(dag)
    except Exception as e:
        logger.error("Replay assembly failed for %s: %s", activity_id, e)
        raise HTTPException(status_code=500, detail=f"Replay assembly failed: {e}")


@router.get("/{activity_id}/timeline")
async def get_activity_timeline(activity_id: str):
    """Return all nodes in chronological order."""
    mgr = _get_manager()
    nodes = mgr.get_timeline(activity_id)
    if not nodes:
        raise HTTPException(status_code=404, detail=f"Activity {activity_id} not found")
    return {"timeline": [_node_to_response(n) for n in nodes]}


@router.get("/{activity_id}/summary")
async def get_activity_summary(activity_id: str):
    """Return a summary of an activity (counts, agents, depth)."""
    mgr = _get_manager()
    summary = mgr.summarize(activity_id)
    if "error" in summary:
        raise HTTPException(status_code=404, detail=summary["error"])
    return ActivitySummaryResponse(**summary)


@router.get("/{activity_id}/resume")
async def find_resume_point(activity_id: str):
    """Find where to resume execution in an activity."""
    engine = _get_resume()
    ctx = engine.find_resume_point(activity_id)
    if not ctx:
        raise HTTPException(
            status_code=404,
            detail=f"No resume point found for activity {activity_id}",
        )
    return ResumeContextResponse(
        activity_id=ctx.activity_id,
        target_node=_node_to_response(ctx.target_node),
        ancestors=[_node_to_response(n) for n in ctx.ancestors],
        accumulated_artifacts=ctx.accumulated_artifacts,
        accumulated_input=ctx.accumulated_input,
    )


@router.post("/{activity_id}/resume")
async def resume_activity(activity_id: str):
    """Mark a resume point as RUNNING and continue execution."""
    engine = _get_resume()
    ctx = engine.find_resume_point(activity_id)
    if not ctx:
        raise HTTPException(status_code=404, detail=f"No resume point found for activity {activity_id}")
    engine.mark_resumed(ctx)
    await _broadcast(activity_id, {
        "event": "activity_resumed",
        "activity_id": activity_id,
        "node_id": ctx.target_node.node_id,
        "status": "RUNNING",
        "timestamp": datetime.utcnow().isoformat(),
    })
    await _broadcast_active({
        "event": "activity_resumed",
        "activity_id": activity_id,
        "status": "RUNNING",
        "timestamp": datetime.utcnow().isoformat(),
    })
    return ResumeContextResponse(
        activity_id=ctx.activity_id,
        target_node=_node_to_response(ctx.target_node),
        ancestors=[_node_to_response(n) for n in ctx.ancestors],
        accumulated_artifacts=ctx.accumulated_artifacts,
        accumulated_input=ctx.accumulated_input,
    )


@router.post("/{activity_id}/pause")
async def pause_activity(activity_id: str):
    """Suspend a running activity."""
    mgr = _get_manager()
    mgr.suspend_activity(activity_id)
    await _broadcast(activity_id, {
        "event": "activity_updated",
        "activity_id": activity_id,
        "status": "SUSPENDED",
        "timestamp": datetime.utcnow().isoformat(),
    })
    await _broadcast_active({
        "event": "activity_updated",
        "activity_id": activity_id,
        "status": "SUSPENDED",
        "timestamp": datetime.utcnow().isoformat(),
    })
    return {"status": "paused", "activity_id": activity_id}


@router.post("/{activity_id}/cancel")
async def cancel_activity(activity_id: str, req: CancelRequest):
    """Mark an activity as cancelled."""
    mgr = _get_manager()
    mgr.fail_activity(activity_id, req.error)
    await _broadcast(activity_id, {
        "event": "activity_completed",
        "activity_id": activity_id,
        "status": "CANCELLED",
        "error": req.error,
        "timestamp": datetime.utcnow().isoformat(),
    })
    await _broadcast_active({
        "event": "activity_completed",
        "activity_id": activity_id,
        "status": "CANCELLED",
        "timestamp": datetime.utcnow().isoformat(),
    })
    return {"status": "cancelled", "activity_id": activity_id}


# ── WebSocket ───────────────────────────────────────────────────────────────


@router.websocket("/ws")
async def activity_websocket(ws: WebSocket):
    """Real-time activity event stream.

    Subscribe to an activity's events by sending:
        {"type": "subscribe", "activity_id": "act_..."}

    Subscribe to the active feed (all non-terminal activities):
        {"type": "subscribe", "activity_id": "__active__"}

    Events pushed:
        {"event": "activity_updated", "activity_id": "...", "status": "...", ...}
    """
    await ws.accept()
    subscribed: set[str] = set()
    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            if msg.get("type") == "subscribe":
                activity_id = msg.get("activity_id", "__active__")
                subscribed.add(activity_id)
                if activity_id not in _ws_subscriptions:
                    _ws_subscriptions[activity_id] = set()
                _ws_subscriptions[activity_id].add(ws)
                await ws.send_text(json.dumps({
                    "event": "subscribed",
                    "activity_id": activity_id,
                }))
            elif msg.get("type") == "unsubscribe":
                activity_id = msg.get("activity_id", "__active__")
                subscribed.discard(activity_id)
                subs = _ws_subscriptions.get(activity_id)
                if subs:
                    subs.discard(ws)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("Activity WebSocket error: %s", e)
    finally:
        for activity_id in list(subscribed):
            subs = _ws_subscriptions.get(activity_id)
            if subs:
                subs.discard(ws)
                if not subs:
                    _ws_subscriptions.pop(activity_id, None)
