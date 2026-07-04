"""Inbox API routes — REST + WebSocket for the unified inbox."""

from __future__ import annotations

import json
import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from core.inbox import InboxStore, get_inbox
from core.workflow.events import MJEvent, get_bus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/inbox", tags=["Inbox"])

_ws_clients: set[WebSocket] = set()


class AddItemRequest(BaseModel):
    message: str
    category: str = "update"
    session_id: str | None = None
    goal_id: str | None = None
    action_label: str | None = None
    action_data: dict | None = None


class MarkReadRequest(BaseModel):
    item_id: str


# ── REST endpoints ───────────────────────────────────────────────────────────


@router.get("")
async def list_inbox(
    limit: int = 50,
    unread_only: bool = False,
    category: str | None = None,
):
    store = get_inbox()
    items = store.list(limit=limit, unread_only=unread_only, category=category)
    return {
        "items": items,
        "unread_count": store.unread_count(),
    }


@router.get("/unread-count")
async def unread_count():
    store = get_inbox()
    return {"unread_count": store.unread_count()}


@router.get("/{item_id}")
async def get_item(item_id: str):
    store = get_inbox()
    item = store.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Inbox item not found")
    return item


@router.post("/add")
async def add_item(req: AddItemRequest):
    store = get_inbox()
    item_id = store.add(
        message=req.message,
        category=req.category,
        session_id=req.session_id,
        goal_id=req.goal_id,
        action_label=req.action_label,
        action_data=req.action_data,
    )
    for ws in list(_ws_clients):
        try:
            await ws.send_text(json.dumps({"event": "inbox_new", "item_id": item_id}))
        except Exception:
            _ws_clients.discard(ws)
    return {"item_id": item_id}


@router.post("/mark-read")
async def mark_read(req: MarkReadRequest):
    store = get_inbox()
    store.mark_read(req.item_id)
    return {"status": "ok"}


@router.post("/mark-all-read")
async def mark_all_read():
    store = get_inbox()
    store.mark_all_read()
    return {"status": "ok"}


@router.delete("/{item_id}")
async def delete_item(item_id: str):
    store = get_inbox()
    store.delete(item_id)
    return {"status": "deleted"}


@router.delete("")
async def clear_inbox():
    store = get_inbox()
    store.clear()
    return {"status": "cleared"}


# ── WebSocket ────────────────────────────────────────────────────────────────


@router.websocket("/ws")
async def inbox_websocket(ws: WebSocket):
    """Real-time inbox event stream.

    Receive inbox_new events when new items are added.
    """
    await ws.accept()
    _ws_clients.add(ws)
    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            if msg.get("type") == "ping":
                await ws.send_text(json.dumps({"event": "pong"}))
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("Inbox WebSocket error: %s", e)
    finally:
        _ws_clients.discard(ws)
