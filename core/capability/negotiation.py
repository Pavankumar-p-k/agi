from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from core.capability.graph import CapabilityGraph, CapabilityNode
from core.capability.models import Capability
from core.capability.registry import capability_registry
from core.providers.base import ExecutionProvider
from core.providers.router import ProviderRouter, provider_router
from core.providers.registry import provider_registry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CandidateScore:
    provider_id: str
    provider_version: str
    score: float
    confidence: float
    dimensions: dict[str, float]
    calibration_adjustment: float
    reason: str


@dataclass(frozen=True)
class NegotiationResult:
    capability_id: str
    capability_version: int
    chosen_provider_id: str
    chosen_provider_version: str
    score: float
    confidence: float
    candidates: tuple[CandidateScore, ...]
    fallback_chain: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict:
        return {
            "capability_id": self.capability_id,
            "capability_version": self.capability_version,
            "chosen_provider_id": self.chosen_provider_id,
            "chosen_provider_version": self.chosen_provider_version,
            "score": self.score,
            "confidence": self.confidence,
            "candidates": [
                {
                    "provider_id": c.provider_id,
                    "score": c.score,
                    "confidence": c.confidence,
                    "dimensions": c.dimensions,
                    "reason": c.reason,
                }
                for c in self.candidates
            ],
            "fallback_chain": list(self.fallback_chain),
            "reason": self.reason,
        }


class CapabilityNegotiator:
    def __init__(
        self,
        graph: CapabilityGraph | None = None,
        router: ProviderRouter | None = None,
        registry: Any = None,
    ) -> None:
        self._graph = graph or __import__("core.capability.graph", fromlist=["capability_graph"]).capability_graph
        self._router = router or provider_router
        self._registry = registry

    def resolve(
        self,
        node: CapabilityNode,
        task: dict[str, Any] | None = None,
        workflow_id: str = "",
        exclude: set[str] | None = None,
    ) -> NegotiationResult:
        reg = self._registry or provider_registry
        candidates = reg.get_providers_for_capability(node.capability_id)
        if not candidates:
            fallback = self._find_fallback(node.capability_id)
            return NegotiationResult(
                capability_id=node.capability_id,
                capability_version=node.version,
                chosen_provider_id="",
                chosen_provider_version="",
                score=0.0,
                confidence=0.0,
                candidates=(),
                fallback_chain=tuple(fallback),
                reason=f"No provider registered for capability '{node.capability_id}'. "
                       f"Fallback chain: {fallback if fallback else 'none available'}",
            )

        exclude = exclude or set()
        scored: list[tuple[float, ExecutionProvider]] = []
        candidates_info: list[CandidateScore] = []

        for provider in candidates:
            if provider.provider_id in exclude:
                continue
            if not provider.enabled:
                continue

            score = self._router._score(provider, task)
            scored.append((score, provider))

        if not scored:
            fallback = self._find_fallback(node.capability_id)
            return NegotiationResult(
                capability_id=node.capability_id,
                capability_version=node.version,
                chosen_provider_id="",
                chosen_provider_version="",
                score=0.0,
                confidence=0.0,
                candidates=(),
                fallback_chain=tuple(fallback),
                reason=f"No enabled provider for capability '{node.capability_id}'",
            )

        scored.sort(key=lambda x: x[0], reverse=True)

        for s, p in scored:
            pid = p.provider_id
            conf = self._router._memory.get_confidence(
                pid, node.capability_id,
                (task or {}).get("task_type", ""),
                (task or {}).get("model", ""),
                (task or {}).get("language", ""),
            ) if self._router._memory else 0.0
            dims = self._router._score_dimensions(p, task)
            dims["priority"] = provider_registry.get_priority(pid) / 100.0
            ctx = {}
            try:
                from core.providers.feedback.models import _extract_context
                ctx = _extract_context(task)
            except Exception:
                pass
            cal = 0.0
            try:
                engine = self._router._get_calibration_engine()
                if engine:
                    cal = engine.get_adjustment(
                        pid, node.capability_id,
                        language=ctx.get("language", ""),
                        framework=ctx.get("framework", ""),
                        project_size=ctx.get("project_size", ""),
                    )
            except Exception:
                pass
            candidates_info.append(CandidateScore(
                provider_id=pid,
                provider_version=p.version,
                score=s,
                confidence=conf,
                dimensions=dims,
                calibration_adjustment=cal,
                reason=self._explain_choice(s, dims, conf, cal),
            ))

        best = scored[0][1]
        best_score = scored[0][0]
        best_conf = self._router._memory.get_confidence(
            best.provider_id, node.capability_id,
            (task or {}).get("task_type", ""),
            (task or {}).get("model", ""),
            (task or {}).get("language", ""),
        ) if self._router._memory else 0.0

        fallback_ids = [p.provider_id for _, p in scored[1:]]
        reason = self._explain_choice(
            best_score, candidates_info[0].dimensions,
            best_conf, candidates_info[0].calibration_adjustment,
        )

        return NegotiationResult(
            capability_id=node.capability_id,
            capability_version=node.version,
            chosen_provider_id=best.provider_id,
            chosen_provider_version=best.version,
            score=best_score,
            confidence=best_conf,
            candidates=tuple(candidates_info),
            fallback_chain=tuple(fallback_ids),
            reason=reason,
        )

    def resolve_goal(
        self,
        goal: str,
        task: dict[str, Any] | None = None,
        workflow_id: str = "",
    ) -> list[NegotiationResult]:
        subgraph = self._graph.resolve_goal(goal)
        if not subgraph.nodes:
            logger.warning("[Negotiator] No capability subgraph for goal: %s", goal)
            return []

        # Resolve topologically (process dependencies first)
        exclude: set[str] = set()
        results: list[NegotiationResult] = []
        ordered = self._topological_sort(subgraph.nodes, subgraph.edges)
        for node in ordered:
            result = self.resolve(node, task, workflow_id, exclude=exclude)
            results.append(result)
            if result.chosen_provider_id:
                exclude.add(result.chosen_provider_id)
        return results

    def _find_fallback(self, capability_id: str) -> list[str]:
        from core.capability.models import BUILTIN_CAPABILITY_IDS
        reg = self._registry or provider_registry
        candidates_list = []
        for cid in BUILTIN_CAPABILITY_IDS:
            if cid != capability_id and reg.has_capability(cid):
                candidates_list.append(cid)
        cap = capability_registry.get(capability_id)
        if cap:
            for cid, other in capability_registry._capabilities.items():
                if cid != capability_id and other.category == cap.category:
                    if cid not in candidates_list and reg.has_capability(cid):
                        candidates_list.append(cid)
        return candidates_list[:3]

    def _topological_sort(
        self,
        nodes: tuple[CapabilityNode, ...],
        edges: tuple[Any, ...],
    ) -> list[CapabilityNode]:
        node_map = {n.capability_id: n for n in nodes}
        in_degree: dict[str, int] = {n.capability_id: 0 for n in nodes}
        adj: dict[str, list[str]] = {n.capability_id: [] for n in nodes}

        for edge in edges:
            if edge.from_id in adj and edge.to_id in in_degree:
                adj[edge.from_id].append(edge.to_id)
                in_degree[edge.to_id] = in_degree.get(edge.to_id, 0) + 1

        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        ordered: list[CapabilityNode] = []

        while queue:
            nid = queue.pop(0)
            if nid in node_map:
                ordered.append(node_map[nid])
            for neighbor in adj.get(nid, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        remaining = [n for n in nodes if n not in ordered]
        return ordered + remaining

    def _explain_choice(
        self,
        score: float,
        dims: dict[str, float],
        confidence: float,
        calibration: float,
    ) -> str:
        parts: list[str] = []
        if dims.get("historical_success", 0) > 0.7:
            parts.append("strong historical success")
        elif dims.get("historical_success", 0) > 0.4:
            parts.append("moderate historical success")

        if dims.get("benchmark_quality", 0) > 0.7:
            parts.append("high benchmark quality")

        if dims.get("health", 0) > 0.8:
            parts.append("healthy")
        elif dims.get("health", 0) < 0.3:
            parts.append("health concerns")

        if dims.get("latency", 0) > 0.7:
            parts.append("low latency")
        if dims.get("cost", 0) > 0.7:
            parts.append("low cost")

        if calibration > 0.05:
            parts.append(f"calibration bonus +{calibration:.3f}")

        if not parts:
            return f"Score: {score:.4f}, Confidence: {confidence:.3f}"

        return f"{', '.join(parts)} (score={score:.4f}, conf={confidence:.3f})"


capability_negotiator = CapabilityNegotiator()
