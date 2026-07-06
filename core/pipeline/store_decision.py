from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StoreAction(Enum):
    """What the Memory stage decided to do with the conversation turn."""

    STORE = "store"
    """Store a new entry (default for new conversations)."""

    UPDATE = "update"
    """Update an existing memory entry (e.g. contradiction resolved)."""

    MERGE = "merge"
    """Merge multiple entries (e.g. consolidated facts)."""

    DELETE = "delete"
    """Delete an existing entry (e.g. user requested removal)."""

    IGNORE = "ignore"
    """Skip storing (e.g. verification failed, no output)."""


@dataclass
class StoreDecision:
    """Decision from the Memory stage after processing a conversation turn."""

    action: StoreAction
    """What to do with this turn."""

    store_type: str = "conversation"
    """Category of content: ``"conversation"``, ``"preference"``, ``"project"``, ``"fact"``."""

    reason: str = ""
    """Human-readable reason for the decision."""

    confidence: float = 0.95
    """Confidence in the decision."""

    fact_count: int = 0
    """Number of extracted facts stored during this turn."""

    contradictions: list[dict[str, Any]] | None = None
    """Any contradictions detected during this turn."""

    memory_refs: list[str] = field(default_factory=list)
    """References stored (fact IDs, conversation IDs, etc.)."""
