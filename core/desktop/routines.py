from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable
import json
import os
import time
import uuid


ROUTINES_PATH = Path(os.path.expanduser("~/.jarvis/desktop_routines.json"))


@dataclass
class RoutineProposal:
    proposal_id: str
    label: str
    actions: list[dict[str, Any]]
    observations: int
    confidence: float
    status: str = "pending"
    created_at: float = field(default_factory=time.time)
    expires_at: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class DesktopRoutineManager:
    """Stores suggestions; execution is impossible until explicit approval."""

    def __init__(self, path: str | Path = ROUTINES_PATH):
        self.path = Path(path)
        self.proposals: dict[str, RoutineProposal] = {}
        self._observations: dict[str, dict[str, Any]] = {}
        self.audit_log: list[dict[str, Any]] = []
        self._load()

    def observe(self, label: str, actions: list[dict[str, Any]], verified: bool = True) -> RoutineProposal | None:
        if not verified or not label or not actions:
            return None
        key = json.dumps({"label": label, "actions": actions}, sort_keys=True, default=str)
        record = self._observations.setdefault(key, {"label": label, "actions": actions, "count": 0})
        record["count"] += 1
        if record["count"] < 3:
            self._save()
            return None
        confidence = min(0.99, 0.5 + (record["count"] - 2) * 0.1)
        existing = next((p for p in self.proposals.values() if p.metadata.get("observation_key") == key), None)
        if existing:
            existing.observations = record["count"]
            existing.confidence = confidence
            self._save()
            return existing
        proposal = RoutineProposal(
            proposal_id=f"routine_{uuid.uuid4().hex[:12]}",
            label=label,
            actions=actions,
            observations=record["count"],
            confidence=confidence,
            metadata={"observation_key": key},
        )
        self.proposals[proposal.proposal_id] = proposal
        self._audit("proposed", proposal)
        self._save()
        return proposal

    def list_pending(self) -> list[RoutineProposal]:
        self.expire()
        return [p for p in self.proposals.values() if p.status == "pending"]

    def approve(self, proposal_id: str) -> RoutineProposal:
        proposal = self._get(proposal_id)
        self._expire_if_needed(proposal)
        if proposal.status != "pending":
            raise ValueError("only pending routine proposals can be approved")
        proposal.status = "approved"
        self._audit("approved", proposal)
        self._save()
        return proposal

    def reject(self, proposal_id: str) -> RoutineProposal:
        proposal = self._get(proposal_id)
        self._expire_if_needed(proposal)
        if proposal.status != "pending":
            raise ValueError("only pending routine proposals can be rejected")
        proposal.status = "rejected"
        self._audit("rejected", proposal)
        self._save()
        return proposal

    def revoke(self, proposal_id: str) -> RoutineProposal:
        proposal = self._get(proposal_id)
        if proposal.status != "approved":
            raise ValueError("only approved routines can be revoked")
        proposal.status = "revoked"
        self._audit("revoked", proposal)
        self._save()
        return proposal

    def expire(self, now: float | None = None) -> list[RoutineProposal]:
        now = time.time() if now is None else now
        expired = []
        for proposal in self.proposals.values():
            if proposal.status in {"pending", "approved"} and proposal.expires_at is not None and proposal.expires_at <= now:
                proposal.status = "expired"
                self._audit("expired", proposal)
                expired.append(proposal)
        if expired:
            self._save()
        return expired

    def execute_approved(self, proposal_id: str, execute: Callable[[dict[str, Any]], Any]) -> list[Any]:
        proposal = self._get(proposal_id)
        self._expire_if_needed(proposal)
        if proposal.status != "approved":
            raise PermissionError("routine requires explicit approval")
        results = [execute(action) for action in proposal.actions]
        self._audit("executed", proposal)
        self._save()
        return results

    def _expire_if_needed(self, proposal: RoutineProposal) -> None:
        if proposal.expires_at is not None and proposal.expires_at <= time.time():
            proposal.status = "expired"
            self._audit("expired", proposal)
            self._save()

    def _audit(self, event: str, proposal: RoutineProposal) -> None:
        self.audit_log.append({
            "timestamp": time.time(),
            "event": event,
            "proposal_id": proposal.proposal_id,
            "status": proposal.status,
        })

    def _get(self, proposal_id: str) -> RoutineProposal:
        proposal = self.proposals.get(proposal_id)
        if proposal is None:
            raise KeyError(f"unknown routine proposal: {proposal_id}")
        return proposal

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "observations": self._observations,
            "proposals": {key: asdict(value) for key, value in self.proposals.items()},
            "audit_log": self.audit_log,
        }
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(temp, self.path)

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            self._observations = payload.get("observations", {})
            self.audit_log = payload.get("audit_log", [])
            self.proposals = {
                key: RoutineProposal(**value)
                for key, value in payload.get("proposals", {}).items()
            }
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            self._observations = {}
            self.proposals = {}
            self.audit_log = []
