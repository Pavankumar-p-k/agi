from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from core.capability.graph import (
    CapabilityEdge,
    CapabilityGraph,
    CapabilityNode,
    CapabilitySubgraph,
    capability_graph,
)
from core.capability.negotiation import (
    CapabilityNegotiator,
    NegotiationResult,
    capability_negotiator,
)
from core.permission.manager import PermissionManager, PermissionResolution, permission_manager

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CompositionStep:
    order: int
    capability_id: str
    version: int
    provider_id: str
    provider_version: str
    score: float
    confidence: float
    dependencies: tuple[str, ...]
    reason: str
    permission: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "order": self.order,
            "capability_id": self.capability_id,
            "version": self.version,
            "provider_id": self.provider_id,
            "provider_version": self.provider_version,
            "score": self.score,
            "confidence": self.confidence,
            "dependencies": list(self.dependencies),
            "reason": self.reason,
            "permission": dict(self.permission),
        }


@dataclass(frozen=True)
class CompositionPlan:
    goal: str
    steps: tuple[CompositionStep, ...]
    subgraph_fingerprint: str
    total_score: float
    avg_confidence: float
    blocked: bool = False
    block_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "goal": self.goal,
            "subgraph_fingerprint": self.subgraph_fingerprint,
            "total_score": self.total_score,
            "avg_confidence": self.avg_confidence,
            "steps": [s.to_dict() for s in self.steps],
            "blocked": self.blocked,
            "block_reason": self.block_reason,
        }


class CompositionEngine:
    def __init__(
        self,
        graph: CapabilityGraph | None = None,
        negotiator: CapabilityNegotiator | None = None,
        permission_mgr: PermissionManager | None = None,
        registry: Any = None,
    ) -> None:
        self._graph = graph or capability_graph
        self._negotiator = negotiator or capability_negotiator
        self._permission_mgr = permission_mgr or permission_manager
        self._registry = registry

    def compose(self, goal: str) -> CompositionPlan:
        subgraph = self._graph.resolve_goal(goal)
        if not subgraph.nodes:
            return CompositionPlan(
                goal=goal,
                steps=(),
                subgraph_fingerprint=subgraph.fingerprint,
                total_score=0.0,
                avg_confidence=0.0,
            )

        edge_map: dict[str, list[str]] = {}
        for edge in subgraph.edges:
            if edge.edge_type == "depends_on":
                if edge.to_id not in edge_map:
                    edge_map[edge.to_id] = []
                edge_map[edge.to_id].append(edge.from_id)

        ordered = self._negotiator._topological_sort(subgraph.nodes, subgraph.edges)

        steps: list[CompositionStep] = []
        blocked = False
        block_reason = ""

        for i, node in enumerate(ordered):
            cap_id = node.capability_id
            deps = tuple(edge_map.get(cap_id, []))

            # Phase C gate: check permissions before negotiation
            perm_result = self._permission_mgr.resolve(cap_id)

            if perm_result.denied:
                blocked = True
                block_reason = perm_result.reason
                steps.append(CompositionStep(
                    order=i,
                    capability_id=cap_id,
                    version=node.version,
                    provider_id="",
                    provider_version="",
                    score=0.0,
                    confidence=0.0,
                    dependencies=deps,
                    reason=block_reason,
                    permission=perm_result.to_dict(),
                ))
                continue

            if perm_result.needs_confirmation:
                steps.append(CompositionStep(
                    order=i,
                    capability_id=cap_id,
                    version=node.version,
                    provider_id="",
                    provider_version="",
                    score=0.0,
                    confidence=0.0,
                    dependencies=deps,
                    reason=f"Awaiting user confirmation: {perm_result.reason}",
                    permission=perm_result.to_dict(),
                ))
                continue

            # Permission granted — proceed to negotiation
            result = self._negotiator.resolve(node)
            steps.append(CompositionStep(
                order=i,
                capability_id=cap_id,
                version=node.version,
                provider_id=result.chosen_provider_id,
                provider_version=result.chosen_provider_version,
                score=result.score,
                confidence=result.confidence,
                dependencies=deps,
                reason=result.reason,
                permission=perm_result.to_dict(),
            ))

        total_score = sum(s.score for s in steps) / len(steps) if steps else 0.0
        avg_conf = sum(s.confidence for s in steps) / len(steps) if steps else 0.0

        return CompositionPlan(
            goal=goal,
            steps=tuple(steps),
            subgraph_fingerprint=subgraph.fingerprint,
            total_score=total_score,
            avg_confidence=avg_conf,
            blocked=blocked,
            block_reason=block_reason,
        )


composition_engine = CompositionEngine()
