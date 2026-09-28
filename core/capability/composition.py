"""CompositionEngine — composes capability graphs into replayable plans.

Gate 5: capabilities denied by the permission layer never reach
negotiation — they produce blocked steps with no provider assigned.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Tuple

from core.capability.graph import CapabilityGraph, capability_graph
from core.capability.models import CapabilityNode
from core.capability.negotiation import CapabilityNegotiator, capability_negotiator
from core.permission.manager import permission_manager
from core.permission.models import Decision


@dataclass
class CompositionStep:
    capability_id: str
    capability_version: int
    provider_id: str
    provider_version: str
    score: float
    confidence: float
    reason: str = ""
    permission: dict = field(default_factory=dict)
    blocked: bool = False

    def to_dict(self) -> dict:
        return {
            "capability_id": self.capability_id,
            "capability_version": self.capability_version,
            "provider_id": self.provider_id,
            "provider_version": self.provider_version,
            "score": self.score,
            "confidence": self.confidence,
            "reason": self.reason,
            "permission": dict(self.permission),
        }


@dataclass
class CompositionPlan:
    goal: str
    steps: Tuple[CompositionStep, ...] = ()
    subgraph_fingerprint: str = ""
    total_score: float = 0.0
    avg_confidence: float = 0.0
    blocked: bool = False

    def to_dict(self) -> dict:
        return {
            "goal": self.goal,
            "steps": [s.to_dict() for s in self.steps],
            "subgraph_fingerprint": self.subgraph_fingerprint,
            "total_score": self.total_score,
            "avg_confidence": self.avg_confidence,
            "blocked": self.blocked,
        }


class CompositionEngine:
    """Composes a goal's capability subgraph into a provider plan.

    Default-constructible: without arguments it wires the module-level
    capability graph, negotiator and permission manager.
    """

    def __init__(self, graph: Any = None, negotiator: Any = None,
                 registry: Any = None) -> None:
        self.graph = graph if graph is not None else capability_graph
        self.negotiator = negotiator if negotiator is not None else capability_negotiator
        self.registry = registry

    def compose(self, goal: str) -> CompositionPlan:
        subgraph = self.graph.resolve_goal(goal)
        steps: list = []
        scores: list = []
        confidences: list = []
        any_denied = False

        for node in subgraph.nodes:
            node = self._as_node(node)
            permission = permission_manager.resolve(node.capability_id).to_dict()
            overall = permission.get("overall")

            if overall == Decision.DENY.value:
                # Gate 5: denied capabilities stop before negotiation.
                any_denied = True
                steps.append(CompositionStep(
                    capability_id=node.capability_id,
                    capability_version=getattr(node, "version", 1),
                    provider_id="",
                    provider_version="",
                    score=0.0,
                    confidence=0.0,
                    reason="denied by permission policy",
                    permission=permission,
                    blocked=True,
                ))
                continue

            result = self.negotiator.resolve(node)
            steps.append(CompositionStep(
                capability_id=node.capability_id,
                capability_version=getattr(node, "version", 1),
                provider_id=result.chosen_provider_id,
                provider_version=result.chosen_provider_version,
                score=result.score,
                confidence=result.confidence,
                reason=result.reason,
                permission=permission,
                blocked=False,
            ))
            scores.append(result.score)
            confidences.append(result.confidence)

        total = round(sum(scores), 3)
        avg = round(sum(confidences) / len(confidences), 3) if confidences else 0.0
        return CompositionPlan(
            goal=goal,
            steps=tuple(steps),
            subgraph_fingerprint=subgraph.fingerprint,
            total_score=total,
            avg_confidence=avg,
            blocked=any_denied,
        )

    @staticmethod
    def _as_node(node: Any) -> CapabilityNode:
        if isinstance(node, CapabilityNode):
            return node
        # Tolerate plain strings or dicts in the subgraph node list.
        if isinstance(node, str):
            return CapabilityNode(capability_id=node)
        if isinstance(node, dict):
            return CapabilityNode(
                capability_id=node.get("capability_id", ""),
                version=int(node.get("version", 1)),
            )
        return CapabilityNode(
            capability_id=str(getattr(node, "capability_id", "")),
            version=int(getattr(node, "version", 1)),
        )


# Module-level default engine (tests import these singletons directly).
composition_engine = CompositionEngine()


__all__ = ["CompositionEngine", "CompositionPlan", "CompositionStep",
           "composition_engine"]
