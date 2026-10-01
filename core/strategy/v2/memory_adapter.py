"""Memory adapter for v2 strategy (Phase 15.1)."""
from __future__ import annotations

from typing import List

_OPEN_STATUSES = {"generated", "approved"}


def _status(proposal) -> str:
    return getattr(proposal.status, "value", proposal.status)


class StrategyMemoryAdapter:
    """Read proposals from a proposal store."""

    def __init__(self, store) -> None:
        self.store = store

    def get_open_proposals(self) -> List:
        return [
            p for p in self.store.list_proposals()
            if _status(p) in _OPEN_STATUSES
        ]

    def get_experimenting_proposals(self) -> List:
        return [
            p for p in self.store.list_proposals()
            if _status(p) == "experimenting"
        ]

    def count_open_proposals(self) -> int:
        return len(self.get_open_proposals())

    def get_proposal(self, proposal_id: str):
        return self.store.get_proposal(proposal_id)
