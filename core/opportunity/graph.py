"""Opportunity Graph (Phase 19) — dependency discovery and unlock value computation.

Extends Phase 17's flat opportunity scoring with a graph model that captures
which improvements enable which future improvements.

Key insight:
    A small improvement that unlocks ten future improvements
    can be more valuable than a large improvement that unlocks nothing.

Formula extension:
    opportunity_score = impact × headroom × success_probability
                      × confidence × calibration_accuracy × unlock_value

Where unlock_value = sum(discounted future opportunities reachable from this node).
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from core.opportunity.models import Opportunity

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────

# Discount factor per depth level (0.5^depth)
DEPTH_DISCOUNT = 0.5

# Minimum edge confidence to include in graph traversal
MIN_EDGE_CONFIDENCE = 0.15

# Default unlock_value when no graph data is available
DEFAULT_UNLOCK_VALUE = 1.0

# ── Models ────────────────────────────────────────────────────────────


@dataclass
class OpportunityGraphNode:
    """A node in the opportunity dependency graph.

    Wraps an Opportunity with its unlock_value (computed from reachable nodes).
    """

    system_name: str
    opportunity: Opportunity | None = None
    unlock_value: float = DEFAULT_UNLOCK_VALUE
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def base_score(self) -> float:
        """The opportunity score without unlock_value."""
        if self.opportunity is None:
            return 0.0
        return (
            self.opportunity.bottleneck_impact
            * self.opportunity.improvement_headroom
            * self.opportunity.success_probability
            * self.opportunity.confidence
            * self.opportunity.calibration_accuracy
        )

    @property
    def compounded_score(self) -> float:
        """Full opportunity score including unlock_value."""
        return self.base_score * self.unlock_value

    def to_dict(self) -> dict[str, Any]:
        return {
            "system_name": self.system_name,
            "base_score": round(self.base_score, 3),
            "unlock_value": round(self.unlock_value, 3),
            "compounded_score": round(self.compounded_score, 4),
            "has_opportunity": self.opportunity is not None,
        }


@dataclass
class OpportunityGraphEdge:
    """A directed dependency edge between two opportunity targets.

    source -> target means "improving source enables improving target".
    """

    source_system: str
    target_system: str
    confidence: float = 0.5
    evidence_count: int = 1
    source_type: str = "mined"  # "mined", "manual", "learned"

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source_system,
            "target": self.target_system,
            "confidence": round(self.confidence, 3),
            "evidence": self.evidence_count,
            "source_type": self.source_type,
        }


# ── Graph ─────────────────────────────────────────────────────────────


class OpportunityGraph:
    """Directed graph of opportunity dependencies.

    Nodes are system names (e.g. "browser_automation").
    Edges are directed: A -> B means "A enables B".
    """

    def __init__(self):
        self._nodes: dict[str, OpportunityGraphNode] = {}
        self._edges: dict[str, list[OpportunityGraphEdge]] = defaultdict(list)
        self._reverse_edges: dict[str, list[OpportunityGraphEdge]] = defaultdict(list)

    # ── Node Management ────────────────────────────────────────────

    def add_node(
        self,
        system_name: str,
        opportunity: Opportunity | None = None,
    ) -> OpportunityGraphNode:
        if system_name not in self._nodes:
            self._nodes[system_name] = OpportunityGraphNode(
                system_name=system_name, opportunity=opportunity
            )
        elif opportunity is not None and self._nodes[system_name].opportunity is None:
            self._nodes[system_name].opportunity = opportunity
        return self._nodes[system_name]

    def get_node(self, system_name: str) -> OpportunityGraphNode | None:
        return self._nodes.get(system_name)

    def remove_node(self, system_name: str) -> None:
        self._nodes.pop(system_name, None)
        self._edges.pop(system_name, None)
        self._reverse_edges.pop(system_name, None)
        # Clean up edges referencing this node
        for src in list(self._edges.keys()):
            self._edges[src] = [
                e for e in self._edges[src] if e.target_system != system_name
            ]
        for tgt in list(self._reverse_edges.keys()):
            self._reverse_edges[tgt] = [
                e for e in self._reverse_edges[tgt] if e.source_system != system_name
            ]

    @property
    def nodes(self) -> dict[str, OpportunityGraphNode]:
        return dict(self._nodes)

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    # ── Edge Management ────────────────────────────────────────────

    def add_edge(self, edge: OpportunityGraphEdge) -> None:
        self._edges[edge.source_system].append(edge)
        self._reverse_edges[edge.target_system].append(edge)
        # Ensure both nodes exist
        if edge.source_system not in self._nodes:
            self.add_node(edge.source_system)
        if edge.target_system not in self._nodes:
            self.add_node(edge.target_system)

    def get_outgoing(self, system_name: str) -> list[OpportunityGraphEdge]:
        return list(self._edges.get(system_name, []))

    def get_incoming(self, system_name: str) -> list[OpportunityGraphEdge]:
        return list(self._reverse_edges.get(system_name, []))

    @property
    def edges(self) -> list[OpportunityGraphEdge]:
        result = []
        for edges in self._edges.values():
            result.extend(edges)
        return result

    @property
    def edge_count(self) -> int:
        return sum(len(edges) for edges in self._edges.values())

    # ── Graph Analysis ─────────────────────────────────────────────

    def has_outgoing(self, system_name: str) -> bool:
        return len(self._edges.get(system_name, [])) > 0

    def has_incoming(self, system_name: str) -> bool:
        return len(self._reverse_edges.get(system_name, [])) > 0

    def predecessors(self, system_name: str) -> list[str]:
        """Systems that enable this one."""
        return [e.source_system for e in self._reverse_edges.get(system_name, [])]

    def successors(self, system_name: str) -> list[str]:
        """Systems enabled by this one."""
        return [e.target_system for e in self._edges.get(system_name, [])]

    # ── Serialization ──────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "nodes": [
                {"name": name, **node.to_dict()}
                for name, node in sorted(self._nodes.items())
            ],
            "edges": [e.to_dict() for e in self.edges],
        }


# ── Unlock Value Scorer ───────────────────────────────────────────────


class UnlockValueScorer:
    """Computes unlock_value for each node via forward reachability analysis.

    unlock_value = 1.0 + sum(discounted scores of all reachable nodes)

    Discount by depth: a directly enabled node contributes its full score,
    a node two hops away contributes 0.25× its score, etc.
    """

    def __init__(self, discount: float = DEPTH_DISCOUNT):
        self.discount = discount

    def compute(self, graph: OpportunityGraph) -> dict[str, float]:
        """Compute unlock_value for every node in the graph.

        Returns:
            dict[system_name, unlock_value]
        """
        result: dict[str, float] = {}

        for node_name in graph.nodes:
            # BFS from this node, following outgoing edges
            visited: set[str] = set()
            queue: deque[tuple[str, int]] = deque()
            queue.append((node_name, 0))
            total_unlock = 1.0  # base: at minimum, value of itself

            while queue:
                current, depth = queue.popleft()
                if current in visited:
                    continue
                visited.add(current)

                if depth > 0:
                    # Score of this node (only if it has an opportunity)
                    node = graph.get_node(current)
                    if node and node.opportunity:
                        discount = self.discount ** (depth - 1)
                        total_unlock += discount * node.base_score

                # Explore children
                for edge in graph.get_outgoing(current):
                    if edge.confidence >= MIN_EDGE_CONFIDENCE:
                        queue.append((edge.target_system, depth + 1))

            result[node_name] = round(total_unlock, 3)

        return result

    def compute_for_node(
        self, graph: OpportunityGraph, system_name: str
    ) -> float:
        """Compute unlock_value for a single node."""
        scores = self.compute(graph)
        return scores.get(system_name, DEFAULT_UNLOCK_VALUE)


# ── Default Dependency Rules ──────────────────────────────────────────
# Hardcoded domain knowledge about which improvements enable others.
# These provide the initial graph skeleton before data mining kicks in.

DEFAULT_DEPENDENCIES: list[tuple[str, str, float, str]] = [
    # Reliability → Benchmarking
    ("browser_automation", "build_benchmark", 0.50, "manual"),
    ("automated_build", "build_benchmark", 0.40, "manual"),
    # Benchmarking → Calibration
    ("build_benchmark", "belief_quality", 0.45, "manual"),
    ("build_benchmark", "strategic_reasoning", 0.30, "manual"),
    # Calibration → Promotion
    ("belief_quality", "browser_automation", 0.35, "manual"),
    ("strategic_reasoning", "self_modification", 0.40, "manual"),
    # Memory → Strategy → Improvement
    ("long_term_memory", "strategic_reasoning", 0.35, "manual"),
    ("strategic_reasoning", "improvement", 0.45, "manual"),
    ("improvement", "self_modification", 0.50, "manual"),
    # Execution → Generalization
    ("execution_infrastructure", "generalization", 0.30, "manual"),
    ("generalization", "belief_quality", 0.35, "manual"),
    # Opportunity Discovery feeds Self-Modification
    ("opportunity_discovery", "self_modification", 0.50, "manual"),
    # Self-Modification unlocks everything downstream
    ("self_modification", "build_benchmark", 0.30, "manual"),
    ("self_modification", "browser_automation", 0.25, "manual"),
]


def build_default_graph() -> OpportunityGraph:
    """Build an OpportunityGraph from hardcoded dependency rules."""
    graph = OpportunityGraph()
    for src, tgt, conf, stype in DEFAULT_DEPENDENCIES:
        graph.add_edge(OpportunityGraphEdge(
            source_system=src,
            target_system=tgt,
            confidence=conf,
            source_type=stype,
        ))
    return graph


# ── Graph Builder ──────────────────────────────────────────────────────


class OpportunityGraphBuilder:
    """Mines stores for opportunity dependency patterns.

    Three discovery methods:
      1. ActivityGraph mining — sequential tool_call patterns
      2. OpportunityStore mining — chronological opportunity completion
      3. Default rules — hardcoded domain knowledge (always applied)
    """

    def __init__(self, discount: float = DEPTH_DISCOUNT):
        self.scorer = UnlockValueScorer(discount=discount)

    def build(
        self,
        opportunities: list[Opportunity],
        activity_store: Any | None = None,
        opportunity_store: Any | None = None,
    ) -> OpportunityGraph:
        """Build a complete opportunity graph.

        Combines default dependencies with mined dependencies.
        """
        graph = build_default_graph()

        # Add all discovered opportunities as nodes
        for opp in opportunities:
            graph.add_node(opp.target_system, opp)

        # Mine activity history for sequential patterns
        if activity_store:
            self._mine_activity_graph(graph, activity_store)

        # Mine opportunity completion history
        if opportunity_store:
            self._mine_opportunity_store(graph, opportunity_store)

        # Compute unlock values
        unlock_scores = self.scorer.compute(graph)

        # Apply unlock values to nodes
        for node_name, unlock_val in unlock_scores.items():
            node = graph.get_node(node_name)
            if node:
                node.unlock_value = unlock_val

        return graph

    def rank_opportunities(
        self,
        opportunities: list[Opportunity],
        activity_store: Any | None = None,
        opportunity_store: Any | None = None,
    ) -> list[Opportunity]:
        """Rank opportunities by compounded score (includes unlock_value).

        Returns a new sorted list — original opportunities are NOT mutated
        (unlock_value is stored on the graph node, not the opportunity).
        """
        graph = self.build(opportunities, activity_store, opportunity_store)

        # Augment each opportunity with its unlock_value and compute new score
        scored: list[tuple[float, Opportunity]] = []
        for opp in opportunities:
            node = graph.get_node(opp.target_system)
            unlock = node.unlock_value if node else DEFAULT_UNLOCK_VALUE
            compounded = opp.opportunity_score * unlock
            scored.append((compounded, opp))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [opp for _, opp in scored]

    # ── Mining Methods ─────────────────────────────────────────────

    def _mine_activity_graph(
        self, graph: OpportunityGraph, activity_store: Any
    ) -> int:
        """Mine ActivityGraph for sequential tool_call patterns.

        Looks for pairs of tool_call nodes in the same activity tree where:
          - A completed before B started
          - B's label suggests calibration/benchmark/reliability
        """
        added = 0
        try:
            nodes = activity_store.get_nodes_by_type("tool_call", limit=500)
            if not nodes:
                return 0

            # Group by activity_id
            activities: dict[str, list[Any]] = defaultdict(list)
            for node in nodes:
                aid = getattr(node, "activity_id", "") or ""
                if aid:
                    activities[aid].append(node)

            # Within each activity, find sequential completions
            for aid, activity_nodes in activities.items():
                completed = [
                    n for n in activity_nodes
                    if getattr(n, "status", "") == "COMPLETED"
                ]
                completed.sort(key=lambda n: (
                    getattr(n, "completed_at", "") or getattr(n, "created_at", "") or ""
                ))

                for i in range(len(completed) - 1):
                    for j in range(i + 1, len(completed)):
                        a = completed[i]
                        b = completed[j]
                        src = getattr(a, "label", "") or ""
                        tgt = getattr(b, "label", "") or ""
                        if self._is_dependency(src, tgt):
                            graph.add_edge(OpportunityGraphEdge(
                                source_system=_tool_to_system(src),
                                target_system=_tool_to_system(tgt),
                                confidence=0.25,
                                evidence_count=1,
                                source_type="mined",
                            ))
                            added += 1
        except Exception as e:
            logger.warning(f"Activity graph mining error: {e}")

        return added

    def _mine_opportunity_store(
        self, graph: OpportunityGraph, opportunity_store: Any
    ) -> int:
        """Mine OpportunityStore for chronological sequences."""
        added = 0
        try:
            records = opportunity_store.list_records(limit=200)
            if not records:
                return 0

            completed = [
                r for r in records
                if r.actual_success and r.completed_at
            ]
            completed.sort(key=lambda r: r.completed_at or "")

            for i in range(len(completed) - 1):
                for j in range(i + 1, len(completed)):
                    a = completed[i]
                    b = completed[j]
                    # Check if b started after a completed
                    if b.selected_at and a.completed_at:
                        if b.selected_at >= a.completed_at:
                            graph.add_edge(OpportunityGraphEdge(
                                source_system=a.target_system,
                                target_system=b.target_system,
                                confidence=0.20,
                                evidence_count=1,
                                source_type="mined",
                            ))
                            added += 1
        except Exception as e:
            logger.warning(f"Opportunity store mining error: {e}")

        return added

    @staticmethod
    def _is_dependency(src_label: str, tgt_label: str) -> bool:
        """Heuristic: does src_label enabling tgt_label?"""
        src = src_label.lower()
        tgt = tgt_label.lower()

        # retry/fix -> benchmark/test/validate
        if any(w in src for w in ["retry", "repair", "fix"]):
            if any(w in tgt for w in ["benchmark", "test", "validat", "check"]):
                return True

        # navigate/click -> snapshot/screenshot
        if any(w in src for w in ["navigate", "click", "fill"]):
            if any(w in tgt for w in ["snapshot", "screenshot"]):
                return True

        # build -> test
        if "build" in src and "test" in tgt:
            return True

        return False


# ── Helpers ───────────────────────────────────────────────────────────


def _tool_to_system(tool_label: str) -> str:
    """Map a tool_call label to a canonical system name."""
    label = tool_label.lower()
    mapping = {
        "browser_navigate": "browser_automation",
        "browser_click": "browser_automation",
        "browser_fill": "browser_automation",
        "browser_snapshot": "browser_automation",
        "browser_screenshot": "browser_automation",
        "browser_": "browser_automation",
        "build_project": "automated_build",
        "run_tests": "automated_build",
        "send_email": "execution_infrastructure",
        "research": "research_infrastructure",
        "extract_facts": "research_infrastructure",
        "edit_file": "coding_intelligence",
        "create_file": "coding_intelligence",
    }
    for key, system in mapping.items():
        if key in label:
            return system
    return label.replace("_", " ").title().replace(" ", "_").lower()
