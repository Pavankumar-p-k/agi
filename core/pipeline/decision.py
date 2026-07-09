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


@dataclass
class ReasonResult:
    answer: str
    thinking_trace: str = ""
    confidence: float = 0.0
    steps_taken: int = 0
    provenance: dict[str, str] = field(default_factory=dict)
    model_group: str = "reasoning"

    def to_decision(
        self,
        activity_id: str,
        stage: str = "reasoner",
        timestamp: float | None = None,
        inputs: dict[str, Any] | None = None,
    ) -> Decision:
        import time

        return Decision(
            activity_id=activity_id,
            stage=stage,
            timestamp=timestamp or time.time(),
            inputs=inputs or {},
            outputs={"answer": self.answer, "thinking_trace": self.thinking_trace},
            rationale=self.thinking_trace,
            confidence=self.confidence,
            metadata={
                "steps_taken": self.steps_taken,
                "provenance": self.provenance,
                "model_group": self.model_group,
            },
        )

    def to_dict(self) -> dict:
        return {
            "conclusion": self.answer,
            "trace": [t for t in self.thinking_trace.split("\n") if t.strip()] if self.thinking_trace else [],
            "confidence": self.confidence,
            "model_group": self.model_group,
        }
