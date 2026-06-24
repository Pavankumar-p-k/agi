"""core/routes/negotiations.py — Multi-agent negotiation API.

Provides:
  - POST /api/negotiations — create a negotiation session for a goal
  - GET /api/negotiations — list sessions
  - GET /api/negotiations/{id} — get session detail
  - POST /api/negotiations/{id}/resolve — accept/reject consensus
  - POST /api/negotiations/{id}/renegotiate — re-collect opinions
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/negotiations", tags=["Negotiations"])


class NegotiateRequest(BaseModel):
    goal: str


class ResolveRequest(BaseModel):
    accepted: bool = True


def _get_engine():
    from core.negotiation.engine import NegotiationEngine
    return NegotiationEngine()


@router.post("", status_code=201)
def create_negotiation(req: NegotiateRequest) -> dict[str, Any]:
    """Create a multi-agent negotiation session for a goal."""
    engine = _get_engine()
    session = engine.create_session(req.goal)
    return session


@router.get("")
def list_negotiations(status: str | None = None) -> list[dict[str, Any]]:
    engine = _get_engine()
    return engine.list_sessions(status=status)


@router.get("/{session_id}")
def get_negotiation(session_id: str) -> dict[str, Any]:
    engine = _get_engine()
    session = engine.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.post("/{session_id}/resolve")
def resolve_negotiation(session_id: str, req: ResolveRequest) -> dict[str, Any]:
    engine = _get_engine()
    session = engine.resolve_session(session_id, accepted=req.accepted)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.post("/{session_id}/renegotiate", status_code=201)
def renegotiate(session_id: str) -> dict[str, Any]:
    engine = _get_engine()
    session = engine.renegotiate(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session
