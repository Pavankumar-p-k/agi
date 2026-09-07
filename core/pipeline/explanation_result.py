"""Explainability result contract."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExplanationResult:
    explanation_id: str = ""
    activity_id: str = ""
    summary: str = ""
    components: dict[str, Any] = field(default_factory=dict)
