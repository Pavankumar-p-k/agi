"""Core pipeline base definitions."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StageOutcome(str, Enum):
    CONTINUE = "continue"
    SHORT_CIRCUIT = "short_circuit"
    RETRY = "retry"
    FAIL = "fail"
    DEFER = "defer"
    STOP = "stop"
    ERROR = "error"
    FAILURE = "failure"


class PipelineStage:
    @property
    def name(self) -> str:
        return self.__class__.__name__

    async def execute(self, context: Any) -> "StageResult":
        raise NotImplementedError


@dataclass
class StageResult:
    outcome: StageOutcome = StageOutcome.CONTINUE
    context: Any = None
    identity: Any = None
    authentication_result: Any = None
    authorization_result: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)
    error: Any = None
    retry_count: int = 0
    metrics: dict[str, Any] = field(default_factory=dict)
    span_stack: list[Any] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.metadata = dict(self.metadata or {})
        self.metrics = dict(self.metrics or {})


STAGE_OWNERSHIP = frozenset()
