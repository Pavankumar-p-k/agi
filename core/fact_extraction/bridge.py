"""Bridge between extracted facts and research facts."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from core.fact_extraction.models import ExtractedFact


@dataclass
class ResearchFact:
    fact_id: str = ""
    entity: str = ""
    claim: str = ""
    source_url: str = ""
    source_type: str = ""
    category: str = "general"
    confidence: float = 0.0
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str | None = None
    activity_id: str | None = None
    node_id: str | None = None


def to_research_fact(extracted: ExtractedFact | dict[str, Any], *, activity_id: str | None = None, node_id: str | None = None) -> ResearchFact:
    if isinstance(extracted, dict):
        fact = ExtractedFact(**extracted)
    else:
        fact = extracted

    metadata = {
        "entity": fact.entity,
        "source_type": fact.source_type,
        "category": fact.category,
        "attributes": dict(fact.attributes or {}),
    }
    timestamp = fact.extracted_at or datetime.now(timezone.utc).isoformat()

    return ResearchFact(
        fact_id=fact.fact_id,
        entity=fact.entity,
        claim=fact.claim,
        source_url=fact.source_url,
        source_type=fact.source_type,
        category=fact.category,
        confidence=fact.confidence,
        tags=list(fact.tags or []),
        metadata=metadata,
        timestamp=timestamp,
        activity_id=activity_id,
        node_id=node_id,
    )


def bridge_batch(facts: list[ExtractedFact | dict[str, Any]], *, activity_id: str | None = None) -> list[ResearchFact]:
    if not facts:
        return []
    return [to_research_fact(f, activity_id=activity_id) for f in facts]


async def async_to_research_fact(*args, **kwargs) -> ResearchFact:
    return to_research_fact(*args, **kwargs)


async def async_bridge_batch(*args, **kwargs) -> list[ResearchFact]:
    return bridge_batch(*args, **kwargs)
