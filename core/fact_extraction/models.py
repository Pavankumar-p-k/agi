from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ExtractedFact:
    fact_id: str
    entity: str | None
    claim: str
    source_url: str
    source_type: str
    category: str
    confidence: float
    tags: list[str] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)
    extracted_at: str = ""
