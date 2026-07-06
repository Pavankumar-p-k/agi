from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Decision:
    activity_id: str
    stage: str
    timestamp: float
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    rationale: str
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
