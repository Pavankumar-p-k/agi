"""Architectural Bottleneck Prediction (Phase 22) — which subsystem weaknesses cause the most downstream damage.

Phase 17 finds opportunities via local success rates. Phase 22 extends this
by propagating impact through the learned opportunity graph.

Key formula:

    total_constrained_value = local_impact + propagated_impact

    local_impact — how bad is this subsystem's current weakness
    propagated_impact — sum of downstream weakness enabled by this node

    propagated_impact(node) = SUM over reachable downstream nodes of:
        downstream.local_impact * edge.confidence * depth_discount^depth

This answers a fundamentally different question than Phase 17:

  Phase 17: "This subsystem is weak."
  Phase 22:  "This subsystem's weakness causes these 5 other subsystems
              to be weak too."

A node with moderate local impact but high graph centrality (many downstream
dependents with high edge confidence) may be a more valuable improvement
target than a node with severe local impact but no dependents.
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────

# Depth discount for propagation (matches Phase 19 unlock_value discount)
DEPTH_DISCOUNT = 0.5

# Minimum edge confidence to consider for propagation
MIN_EDGE_CONFIDENCE = 0.15

# Default local impact when no data is available (moderate)
DEFAULT_LOCAL_IMPACT = 0.25

# Minimum total_constrained_value to report a bottleneck
MIN_REPORTABLE_IMPACT = 0.05


# ── Models ────────────────────────────────────────────────────────────


@dataclass
class BottleneckImpact:
    """Per-system contribution to a downstream system's weakness.

    Attributes:
        target_system: the system being constrained
        edge_confidence: confidence of the dependency edge
        propagated_fraction: how much of the target's local impact is
                             attributable to this bottleneck
    """

    target_system: str
    edge_confidence: float
    propagated_fraction: float


@dataclass
class Bottleneck:
    """A subsystem whose weakness propagates to constrain downstream systems.

    Attributes:
        subsystem: the bottleneck system name
        local_impact: 0.0–1.0 direct weakness of this subsystem
        propagated_impact: sum of downstream weakness attributable to this node
        total_constrained_value: local_impact + propagated_impact
        confidence: how confident we are in this assessment
        affected_systems: list of (system, impact) pairs this node constrains
        depth_reach: maximum graph depth reached during propagation
        evidence: supporting data (success rates, edge stats, etc.)
    """

    subsystem: str
    local_impact: float
    propagated_impact: float
    total_constrained_value: float
    confidence: float
    affected_systems: list[BottleneckImpact] = field(default_factory=list)
    depth_reach: int = 0
    evidence: list[str] = field(default_factory=list)

    @property
    def impact_ratio(self) -> float:
        """Ratio of propagated to local impact.

        > 1.0 means this node constrains more downstream value than
        its own local weakness. High-leverage improvement target.
        """
        if self.local_impact <= 0:
            return 0.0
        return round(self.propagated_impact / self.local_impact, 3)

    def to_dict(self) -> dict[str, Any]:
        return {
            "subsystem": self.subsystem,
            "local_impact": round(self.local_impact, 3),
            "propagated_impact": round(self.propagated_impact, 3),
            "total_constrained_value": round(self.total_constrained_value, 3),
            "impact_ratio": self.impact_ratio,
            "confidence": round(self.confidence, 3),
            "affected_systems": [
                {"system": a.target_system,
                 "confidence": round(a.edge_confidence, 3),
                 "fraction": round(a.propagated_fraction, 3)}
                for a in self.affected_systems
            ],
            "depth_reach": self.depth_reach,
            "evidence": self.evidence[:5],
        }


# ── Bottleneck Analyzer ──────────────────────────────────────────────


class BottleneckAnalyzer:
    """Analyzes which subsystem weaknesses cause the most downstream damage.

    Uses the learned opportunity graph (Phase 19/20) to propagate local
    impact scores through dependency edges. The result is a ranked list
    of bottlenecks ordered by total_constrained_value.

    Usage:
        analyzer = BottleneckAnalyzer()
        bottlenecks = analyzer.analyze(
            graph=opportunity_graph,
            activity_store=activity_store,
        )
        for b in bottlenecks[:5]:
            print(f"{b.subsystem}: {b.total_constrained_value:.2f}")
    """

    def __init__(self, depth_discount: float = DEPTH_DISCOUNT):
        self.depth_discount = depth_discount

    def analyze(
        self,
        graph: Any,
        activity_store: Any | None = None,
        system_scores: dict[str, float] | None = None,
    ) -> list[Bottleneck]:
        """Rank all systems in the graph by total_constrained_value.

        Args:
            graph: OpportunityGraph instance (Phase 19)
            activity_store: optional ActivityStore for data-driven local_impact
            system_scores: optional override of system capability scores

        Returns:
            Sorted list of Bottleneck, highest total_constrained_value first.
        """
        # 1. Compute local_impact for every node
        local_impacts = self._compute_local_impacts(
            graph, activity_store, system_scores
        )
        if not local_impacts:
            return []

        # 2. Propagate impact through the graph
        bottlenecks = []
        for node_name in graph.nodes:
            bottleneck = self._compute_bottleneck(
                graph, node_name, local_impacts
            )
            if bottleneck and bottleneck.total_constrained_value >= MIN_REPORTABLE_IMPACT:
                bottlenecks.append(bottleneck)

        bottlenecks.sort(
            key=lambda b: b.total_constrained_value, reverse=True
        )
        return bottlenecks

    def _compute_local_impacts(
        self,
        graph: Any,
        activity_store: Any | None = None,
        system_scores: dict[str, float] | None = None,
    ) -> dict[str, float]:
        """Compute local_impact for every node in the graph.

        Priority order (first available wins):
          1. ActivityStore tool_call failure rates
          2. system_scores headroom (1.0 - score)
          3. DEFAULT_SYSTEM_SCORES headroom
          4. DEFAULT_LOCAL_IMPACT
        """
        impacts: dict[str, float] = {}

        # Try activity store first
        if activity_store:
            try:
                tool_stats = self._aggregate_tool_stats(activity_store)
                for node_name in graph.nodes:
                    impact = self._tool_stat_impact(node_name, tool_stats)
                    if impact is not None:
                        impacts[node_name] = impact
            except Exception as e:
                logger.warning(f"Activity store stats failed: {e}")

        # Fill remaining from system scores
        for node_name in graph.nodes:
            if node_name in impacts:
                continue
            score = None
            if system_scores and node_name in system_scores:
                score = system_scores[node_name]
            else:
                try:
                    from core.opportunity.engine import DEFAULT_SYSTEM_SCORES
                    score = DEFAULT_SYSTEM_SCORES.get(node_name)
                except ImportError:
                    pass
            if score is not None:
                impacts[node_name] = max(0.02, 1.0 - score)
            else:
                impacts[node_name] = DEFAULT_LOCAL_IMPACT

        return impacts

    def _compute_bottleneck(
        self,
        graph: Any,
        node_name: str,
        local_impacts: dict[str, float],
    ) -> Bottleneck | None:
        """Compute bottleneck metrics for a single node via forward BFS.

        For each reachable downstream node, the propagated contribution is:
            downstream.local_impact × path_confidence_product × depth_discount^(depth-1)

        where path_confidence_product is the product of edge confidences
        along the unique path from root to the downstream node.
        """
        local = local_impacts.get(node_name, DEFAULT_LOCAL_IMPACT)
        if local <= 0:
            return None

        # BFS tracking (current, depth, cumulative_confidence_product)
        visited: set[str] = set()
        queue: deque[tuple[str, int, float]] = deque()
        queue.append((node_name, 0, 1.0))

        total_propagated = 0.0
        affected_map: dict[str, BottleneckImpact] = {}
        max_depth = 0

        while queue:
            current, depth, conf_product = queue.popleft()
            if current in visited:
                continue
            visited.add(current)

            if depth > 0:
                max_depth = max(max_depth, depth)
                downstream_local = local_impacts.get(current, DEFAULT_LOCAL_IMPACT)
                discount = self.depth_discount ** (depth - 1)
                propagated = downstream_local * conf_product * discount
                total_propagated += propagated
                affected_map[current] = BottleneckImpact(
                    target_system=current,
                    edge_confidence=round(conf_product, 4),
                    propagated_fraction=round(propagated, 4),
                )

            # Enqueue children with sufficient edge confidence
            for edge in graph.get_outgoing(current):
                if edge.confidence >= MIN_EDGE_CONFIDENCE:
                    new_conf = conf_product * edge.confidence
                    queue.append((edge.target_system, depth + 1, new_conf))

        total = local + total_propagated
        affected_list = list(affected_map.values())

        # Confidence: weighted by data source quality.
        # Data-driven local_impact = higher confidence.
        confidence = 0.50  # base
        if local > DEFAULT_LOCAL_IMPACT + 0.05:
            confidence += 0.20  # data-supported
        if total_propagated > 0:
            confidence += 0.15  # propagation adds signal
        confidence = min(1.0, confidence)

        evidence = self._build_evidence(node_name, local, total_propagated,
                                        affected_list, local_impacts)

        return Bottleneck(
            subsystem=node_name,
            local_impact=round(local, 3),
            propagated_impact=round(total_propagated, 3),
            total_constrained_value=round(total, 3),
            confidence=round(confidence, 3),
            affected_systems=affected_list,
            depth_reach=max_depth,
            evidence=evidence,
        )

    def _aggregate_tool_stats(self, activity_store: Any) -> dict[str, dict[str, float | int]]:
        """Aggregate tool_call success/failure from activity store.

        Returns:
            dict[tool_name, {"successes": int, "failures": int, "total": int}]
        """
        from collections import defaultdict

        tool_stats: dict[str, dict[str, float | int]] = defaultdict(
            lambda: {"successes": 0, "failures": 0, "total": 0}
        )

        nodes = activity_store.get_nodes_by_type("tool_call")
        if not nodes:
            return dict(tool_stats)

        for node in nodes:
            label = getattr(node, "label", "") or ""
            status = getattr(node, "status", "") or ""
            tool_name = label.lower().strip()
            if not tool_name:
                continue
            stats = tool_stats[tool_name]
            stats["total"] += 1
            if status and "fail" not in status.lower() and "error" not in status.lower():
                stats["successes"] += 1
            else:
                stats["failures"] += 1

        return dict(tool_stats)

    def _tool_stat_impact(
        self,
        system_name: str,
        tool_stats: dict[str, dict[str, float | int]],
    ) -> float | None:
        """Derive local_impact for a system from its tool stats.

        Maps system names to known tool prefixes and aggregates
        failure rates across all matching tools.
        """
        system_tool_map: dict[str, list[str]] = {
            "browser_automation": ["browser_navigate", "browser_click",
                                   "browser_fill", "browser_snapshot",
                                   "browser_screenshot", "browser_"],
            "automated_build": ["build_project", "run_tests"],
            "execution_infrastructure": ["send_email"],
            "research_infrastructure": ["research", "extract_facts"],
            "coding_intelligence": ["edit_file", "create_file"],
        }

        prefixes = system_tool_map.get(system_name, [])
        if not prefixes:
            return None

        total_successes = 0
        total_failures = 0

        for tool_name, stats in tool_stats.items():
            for prefix in prefixes:
                if tool_name.startswith(prefix) or prefix in tool_name:
                    total_successes += stats["successes"]
                    total_failures += stats["failures"]
                    break

        total = total_successes + total_failures
        if total < 3:  # minimum evidence threshold
            return None

        failure_rate = total_failures / total if total > 0 else 0.0
        return max(0.02, failure_rate)

    def _build_evidence(
        self,
        node_name: str,
        local_impact: float,
        propagated_impact: float,
        affected: list[BottleneckImpact],
        local_impacts: dict[str, float],
    ) -> list[str]:
        evidence = [
            f"Local impact: {local_impact:.2f}",
            f"Propagated impact: {propagated_impact:.2f} ({len(affected)} downstream systems)",
        ]
        if affected:
            systems_str = ", ".join(
                f"{a.target_system}({a.propagated_fraction:.2f})"
                for a in affected[:5]
            )
            evidence.append(f"Affected systems: {systems_str}")
        # Add top-constrained system note
        if affected:
            most = max(affected, key=lambda a: a.propagated_fraction)
            evidence.append(
                f"Most constrained: {most.target_system} "
                f"(fraction={most.propagated_fraction:.3f}, "
                f"edge_confidence={most.edge_confidence:.2f})"
            )
        return evidence
