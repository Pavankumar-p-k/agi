"""DesktopRoutineManager — verified-success routine proposals.

Observes verified action sequences and proposes reusable routines.
Nothing executes without an explicit human approval; proposals stay
pending until `approve()` is called.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

_MIN_CONFIDENCE = 0.6
_REPEATS_FOR_PROPOSAL = 2
_MAX_ROUTEINES = 200


@dataclass
class RoutineProposal:
    proposal_id: str
    label: str
    goal: str
    steps: list = field(default_factory=list)
    confidence: float = 0.0
    status: str = "pending"          # pending | approved | rejected
    created_at: float = 0.0
    decided_at: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "proposal_id": self.proposal_id,
            "label": self.label,
            "goal": self.goal,
            "steps": list(self.steps),
            "confidence": self.confidence,
            "status": self.status,
            "created_at": self.created_at,
        }


class DesktopRoutineManager:
    """Learns repeated verified action sequences as approval-gated routines."""

    def __init__(self, store_path: Optional[str] = None) -> None:
        self._store_path = Path(store_path) if store_path else None
        self._proposals: dict[str, RoutineProposal] = {}
        self._history: dict[str, list] = {}  # goal-signature -> [step sequences]
        self._load()

    # ── persistence ──────────────────────────────────────────────────
    def _load(self) -> None:
        if not self._store_path or not self._store_path.exists():
            return
        try:
            data = json.loads(self._store_path.read_text(encoding="utf-8"))
            for item in data.get("proposals", []):
                proposal = RoutineProposal(
                    proposal_id=item["proposal_id"],
                    label=item.get("label", ""),
                    goal=item.get("goal", ""),
                    steps=item.get("steps", []),
                    confidence=float(item.get("confidence", 0.0)),
                    status=item.get("status", "pending"),
                    created_at=float(item.get("created_at", 0.0)),
                )
                self._proposals[proposal.proposal_id] = proposal
        except Exception:  # noqa: BLE001 — store is best-effort
            pass

    def _save(self) -> None:
        if not self._store_path:
            return
        try:
            self._store_path.parent.mkdir(parents=True, exist_ok=True)
            data = {"proposals": [p.to_dict() for p in self._proposals.values()]}
            self._store_path.write_text(
                json.dumps(data, indent=1), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass

    # ── observation ──────────────────────────────────────────────────
    def observe(self, goal: str, actions: list, verified: bool = False) -> Optional[RoutineProposal]:
        """Record a verified action sequence; propose a routine on repetition.

        Only verified sequences count toward a proposal. Returns the new
        proposal when the same sequence has been verified enough times,
        else None.
        """
        if not verified or not actions:
            return None
        signature = json.dumps(
            [{"tool": a.get("tool"), "args": a.get("args", {})} for a in actions],
            sort_keys=True, default=str)
        seen = self._history.setdefault(signature, [])
        seen.append({"goal": str(goal), "actions": list(actions),
                     "at": time.time()})
        if len(seen) < _REPEATS_FOR_PROPOSAL:
            return None

        # Already proposed for this signature?
        for proposal in self._proposals.values():
            if proposal.goal == str(goal) and proposal.steps == list(actions):
                return proposal

        first = seen[0]
        proposal = RoutineProposal(
            proposal_id=f"rtn_{uuid.uuid4().hex[:10]}",
            label=self._label_for(str(goal), actions),
            goal=str(goal),
            steps=list(actions),
            confidence=min(0.95, _MIN_CONFIDENCE + 0.1 * len(seen)),
            status="pending",
            created_at=time.time(),
        )
        self._proposals[proposal.proposal_id] = proposal
        self._trim()
        self._save()
        return proposal

    @staticmethod
    def _label_for(goal: str, actions: list) -> str:
        tools = "+".join(str(a.get("tool", "?")) for a in actions[:3])
        base = goal.strip()[:40] or tools
        return f"{base} ({tools})" if len(actions) > 1 else base

    def _trim(self) -> None:
        if len(self._proposals) <= _MAX_ROUTEINES:
            return
        ordered = sorted(self._proposals.values(),
                         key=lambda p: p.created_at, reverse=True)
        self._proposals = {p.proposal_id: p
                           for p in ordered[:_MAX_ROUTEINES]}

    # ── approval gate ────────────────────────────────────────────────
    def approve(self, proposal_id: str) -> bool:
        proposal = self._proposals.get(proposal_id)
        if proposal is None or proposal.status != "pending":
            return False
        proposal.status = "approved"
        proposal.decided_at = time.time()
        self._save()
        return True

    def reject(self, proposal_id: str) -> bool:
        proposal = self._proposals.get(proposal_id)
        if proposal is None or proposal.status != "pending":
            return False
        proposal.status = "rejected"
        proposal.decided_at = time.time()
        self._save()
        return True

    def list_proposals(self, status: Optional[str] = None) -> list:
        proposals = list(self._proposals.values())
        if status:
            proposals = [p for p in proposals if p.status == status]
        return sorted(proposals, key=lambda p: p.created_at, reverse=True)


__all__ = ["DesktopRoutineManager", "RoutineProposal"]
