"""Phase 15.1 — Memory Adapter (Strategy v2).

Bridges the Strategic Reasoning Layer to existing stores:

  - PrincipleStore (principles, proposals)
  - KnowledgeStore (historical experiences)
  - ActivityGraph (past execution patterns)

Provides a unified interface for the planner to query open proposals,
active experiments, and relevant historical data.
"""

from __future__ import annotations

import logging
from typing import Any

from core.generalization.models import (
    ImprovementProposal,
    ProposalStatus,
)
from core.generalization.store import PrincipleStore

logger = logging.getLogger(__name__)


class StrategyMemoryAdapter:
    """Unified interface to existing stores for the strategic reasoning layer.

    Usage:
        adapter = StrategyMemoryAdapter(principle_store)
        proposals = adapter.get_open_proposals()
    """

    def __init__(self, principle_store: PrincipleStore):
        self._store = principle_store

    def get_open_proposals(self) -> list[ImprovementProposal]:
        """Get all proposals that are ready for strategic evaluation.

        Returns GENERATED and APPROVED proposals (not yet experimenting).
        """
        generated = self._store.list_proposals(status=ProposalStatus.GENERATED.value)
        approved = self._store.list_proposals(status=ProposalStatus.APPROVED.value)
        return generated + approved

    def get_experimenting_proposals(self) -> list[ImprovementProposal]:
        """Get proposals currently being experimented on."""
        return self._store.list_proposals(
            status=ProposalStatus.EXPERIMENTING.value,
        )

    def get_proposal(self, proposal_id: str) -> ImprovementProposal | None:
        """Get a single proposal by ID."""
        return self._store.get_proposal(proposal_id)

    def count_open_proposals(self) -> int:
        """Count proposals available for strategic selection."""
        return (
            self._store.count_proposals(status=ProposalStatus.GENERATED.value)
            + self._store.count_proposals(status=ProposalStatus.APPROVED.value)
        )
