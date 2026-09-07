"""Data models for extracted browser facts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExtractedFact:
    fact_id: str = ""
    entity: str = ""
    claim: str = ""
    source_url: str = ""
    source_type: str = ""
    category: str = "general"
    confidence: float = 0.0
    tags: list[str] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)
    extracted_at: str | None = None

    def __post_init__(self) -> None:
        if self.tags is None:
            self.tags = []
        if self.attributes is None:
            self.attributes = {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "fact_id": self.fact_id,
            "entity": self.entity,
            "claim": self.claim,
            "source_url": self.source_url,
            "source_type": self.source_type,
            "category": self.category,
            "confidence": self.confidence,
            "tags": list(self.tags),
            "attributes": dict(self.attributes),
            "extracted_at": self.extracted_at,
        }
