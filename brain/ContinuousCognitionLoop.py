from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from jarvis_os.runtime.exceptions import RuntimeBoundaryViolation


@dataclass
class CognitionCycle:
    input_text: str
    decision: dict[str, Any]


class ContinuousCognitionLoop:
    """
    Canonical cognition loop that produces bounded decisions from explicit input.
    """

    def __init__(self, world_state=None, memory_core=None, simulator=None, archive=None, self_repair=None, metacognition=None):
        self.world_state = world_state
        self.memory_core = memory_core
        self.simulator = simulator
        self.archive = archive
        self.self_repair = self_repair
        self.metacognition = metacognition

    def run_cycle(self, text: str, planner: Any) -> CognitionCycle:
        if not text.strip():
            raise RuntimeBoundaryViolation("Cognition loop requires non-empty input.")
        decision = planner.build_plan(text, {"type": "auto"}, {"recommended_tools": []}).to_dict()
        return CognitionCycle(input_text=text, decision=decision)
