"""ExplanationResult — output of the explainability stage."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExplanationResult:
    explanation_id: str = ""
    request_id: str = ""
    activity_id: str = ""
    summary: str = ""
    confidence: float = 0.0
    reasoning_trace: tuple = ()
    key_findings: tuple = ()
    metadata: dict = field(default_factory=dict)


__all__ = ["ExplanationResult"]
