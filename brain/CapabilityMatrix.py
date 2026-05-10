"""CapabilityMatrix evaluates subsystem capability and suitability for each task."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class CapabilityProfile:
    subsystem: str
    reasoning: float
    execution: float
    automation: float
    context_depth: float
    emotional_intelligence: float
    realtime: float
    cost: float
    reliability: float
    latency: float
    risk: float


class CapabilityMatrix:
    """Defines capability scores for every specialized subsystem."""

    def __init__(self):
        self.profiles: Dict[str, CapabilityProfile] = {
            "JarvisBrain": CapabilityProfile(
                subsystem="JarvisBrain",
                reasoning=0.8,
                execution=0.4,
                automation=0.2,
                context_depth=0.9,
                emotional_intelligence=0.85,
                realtime=0.7,
                cost=0.6,
                reliability=0.85,
                latency=0.6,
                risk=0.3,
            ),
            "AIOrchestrator": CapabilityProfile(
                subsystem="AIOrchestrator",
                reasoning=0.9,
                execution=0.6,
                automation=0.7,
                context_depth=0.75,
                emotional_intelligence=0.5,
                realtime=0.5,
                cost=0.7,
                reliability=0.8,
                latency=0.7,
                risk=0.4,
            ),
            "HybridOrchestrator": CapabilityProfile(
                subsystem="HybridOrchestrator",
                reasoning=0.7,
                execution=0.95,
                automation=0.95,
                context_depth=0.6,
                emotional_intelligence=0.3,
                realtime=0.4,
                cost=0.8,
                reliability=0.75,
                latency=0.8,
                risk=0.5,
            ),
            "CognitiveAgent": CapabilityProfile(
                subsystem="CognitiveAgent",
                reasoning=0.85,
                execution=0.6,
                automation=0.65,
                context_depth=0.8,
                emotional_intelligence=0.7,
                realtime=0.6,
                cost=0.75,
                reliability=0.78,
                latency=0.65,
                risk=0.35,
            ),
        }

    def score(self, subsystem: str, task: Dict[str, Any]) -> float:
        profile = self.profiles.get(subsystem)
        if not profile:
            return 0.0

        base_score = (
            profile.reasoning * task.get("reasoning_weight", 1.0)
            + profile.execution * task.get("execution_weight", 1.0)
            + profile.automation * task.get("automation_weight", 1.0)
            + profile.context_depth * task.get("context_weight", 1.0)
            + profile.emotional_intelligence * task.get("emotion_weight", 1.0)
            - profile.cost * task.get("cost_weight", 0.5)
            - profile.risk * task.get("risk_weight", 0.5)
        )
        return max(0.0, min(1.0, base_score / 5.0))

    def best_fit(self, task: Dict[str, Any]) -> str:
        best: str = "JarvisBrain"
        best_score = -1.0
        for subsystem, profile in self.profiles.items():
            score = self.score(subsystem, task)
            if score > best_score:
                best_score = score
                best = subsystem
        return best

    def get_profile(self, subsystem: str) -> CapabilityProfile | None:
        return self.profiles.get(subsystem)
