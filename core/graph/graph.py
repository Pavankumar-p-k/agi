from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.graph.state import AgentState


@dataclass
class StateGraph:
    state: AgentState = field(default_factory=AgentState)

    def __iter__(self):
        return iter((self.state,))

    def step(self) -> AgentState:
        return self.state

    def set_state(self, state: AgentState) -> None:
        self.state = state
