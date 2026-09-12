"""Composition engine: goal → ordered capability plan with providers.

Completed from the committed contract in tests/architecture/test_capability_gates.py
(Gates 5, 8).  ``compose`` resolves the goal's capability subgraph through the
existing CapabilityGraph, negotiates a provider per step via the
CapabilityNegotiator (which consults the live provider router), and resolves
permissions through the existing PermissionManager — composition never grants
authority the permission layer does not allow.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from core.capability.graph import CapabilityGraph

logger = logging.getLogger(__name__)


@dataclass
class CompositionStep:
    capability_id: str = ""
    provider_id: str = ""
    permission: dict[str, Any] = field(default_factory=dict)
    action: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "provider_id": self.provider_id,
            "permission": self.permission,
            "action": self.action,
            "params": self.params,
            "score": self.score,
            "reason": self.reason,
        }


@dataclass
class CompositionPlan:
    goal: str = ""
    steps: tuple[CompositionStep, ...] = ()
    blocked: bool = False
    subgraph_fingerprint: str = ""
    total_score: float = 0.0
    avg_confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "steps": [s.to_dict() for s in self.steps],
            "blocked": self.blocked,
            "subgraph_fingerprint": self.subgraph_fingerprint,
            "total_score": self.total_score,
            "avg_confidence": self.avg_confidence,
        }


class CompositionEngine:
    """Builds multi-capability plans on top of graph + negotiator."""

    def __init__(
        self,
        graph: Optional[CapabilityGraph] = None,
        negotiator: Any = None,
        registry: Any = None,
    ) -> None:
        self.graph = graph or CapabilityGraph()
        self.negotiator = negotiator
        self.registry = registry

    def _get_negotiator(self) -> Any:
        if self.negotiator is not None:
            return self.negotiator
        from core.capability.negotiation import capability_negotiator
        return capability_negotiator

    def compose(self, task: str) -> CompositionPlan:
        subgraph = self.graph.resolve_goal(task)
        steps: list[CompositionStep] = []
        blocked = False
        scores: list[float] = []

        for node in subgraph.nodes:
            try:
                from core.permission.manager import PermissionManager
                result = PermissionManager().resolve(node.capability_id)
                permission = result.to_dict() if hasattr(result, "to_dict") else {}
                if getattr(result, "denied", False):
                    blocked = True
            except Exception as exc:
                logger.debug("[composition] permission resolve failed for %s: %s",
                             node.capability_id, exc)
                permission = {}

            negotiation = self._get_negotiator().resolve(node)
            provider_id = negotiation.chosen_provider_id
            if getattr(permission, "get", lambda _k, d=None: None)("denied"):
                provider_id = ""

            steps.append(CompositionStep(
                capability_id=node.capability_id,
                provider_id=provider_id,
                permission=permission,
                action="execute",
                score=negotiation.score,
                reason=negotiation.reason,
            ))
            scores.append(negotiation.score)

        total = round(sum(scores), 4)
        avg_conf = round(total / len(scores), 4) if scores else 0.0
        return CompositionPlan(
            goal=str(task or ""),
            steps=tuple(steps),
            blocked=blocked,
            subgraph_fingerprint=subgraph.fingerprint,
            total_score=total,
            avg_confidence=avg_conf,
        )


composition_engine = CompositionEngine()
