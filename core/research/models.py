"""Fact dataclass — a single extracted claim with provenance."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Fact:
    """A structured fact extracted from a web page or other source.

    Each fact has:
    - A unique ID for cross-referencing
    - The source URL it came from
    - The claim text itself
    - A confidence score (0.0–1.0)
    - A category (general, technical, pricing, comparison, etc.)
    - Tags for filtering
    - Links back to the activity and node that produced it
    """

    fact_id: str
    source_url: str
    claim: str
    confidence: float = 0.5
    category: str = "general"
    tags: list[str] = field(default_factory=list)
    timestamp: datetime | None = None
    activity_id: str | None = None
    node_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
