"""Bridge between BrowserFactExtractor (ExtractedFact) and research pipeline (Fact).

Converts browser-specific extracted facts into the research pipeline's
Fact model so cross-page aggregation, contradiction detection, and
report synthesis work seamlessly.
"""

from datetime import datetime
from typing import Any

from core.fact_extraction.models import ExtractedFact
from core.research.models import Fact


def to_research_fact(
    ef: ExtractedFact,
    activity_id: str | None = None,
    node_id: str | None = None,
) -> Fact:
    """Convert an ExtractedFact to the research pipeline's Fact model."""
    return Fact(
        fact_id=ef.fact_id,
        source_url=ef.source_url,
        claim=ef.claim,
        confidence=ef.confidence,
        category=ef.category,
        tags=ef.tags,
        timestamp=_parse_or_now(ef.extracted_at),
        activity_id=activity_id,
        node_id=node_id,
        metadata={
            "entity": ef.entity,
            "source_type": ef.source_type,
            "attributes": ef.attributes,
        },
    )


def bridge_batch(
    extracted: list[ExtractedFact],
    activity_id: str | None = None,
    node_id: str | None = None,
) -> list[Fact]:
    """Convert a batch of ExtractedFacts to Facts."""
    return [to_research_fact(ef, activity_id, node_id) for ef in extracted]


def _parse_or_now(ts: str | None) -> datetime:
    if ts:
        try:
            return datetime.fromisoformat(ts)
        except (ValueError, TypeError):
            pass
    return datetime.utcnow()
