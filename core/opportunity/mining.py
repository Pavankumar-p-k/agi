"""Sequential Pattern Miner (Phase 20.0) — learns opportunity dependency edges from historical evidence.

Phase 19 introduced the opportunity dependency graph, but edges were mostly
human-seeded. Phase 20 changes the source of truth from developer knowledge
to historical evidence.

Three mining sources:
  1. ActivityGraph — sequential tool_call patterns within activities
  2. OpportunityStore — chronological opportunity completion sequences
  3. Experiment history — sequential experiment patterns

Each mined edge is scored with three metrics:
  - support:    count(A → B)
  - confidence: P(B|A) = support / count(A → any)
  - lift:       P(B|A) / P(B) — filters spurious edges from high-frequency nodes

Promotion gates (configurable):
  - support >= 5
  - confidence >= 0.6
  - lift >= 1.2

Edges that pass are merged with the default graph. When a learned edge
exceeds the default's confidence, it becomes authoritative.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.opportunity.graph import OpportunityGraph, OpportunityGraphEdge

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────

# Promotion gates — a learned edge must pass all three
MIN_SUPPORT = 5
MIN_CONFIDENCE = 0.6
MIN_LIFT = 1.2

# Default confidence when no learned edge exists
DEFAULT_EDGE_CONFIDENCE = 0.5


# ── Helpers (local copy avoids circular import with graph.py) ────────

_TOOL_SYSTEM_MAP: dict[str, str] = {
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


def _tool_to_system(tool_label: str) -> str:
    """Map a tool_call label to a canonical system name."""
    label = tool_label.lower()
    for key, system in _TOOL_SYSTEM_MAP.items():
        if key in label:
            return system
    return label.replace("_", " ").title().replace(" ", "_").lower()


# ── Enums ─────────────────────────────────────────────────────────────


class EdgeSource(str, Enum):
    """Origin of an opportunity dependency edge."""

    DEFAULT = "default"      # Hand-authored domain knowledge
    LEARNED = "learned"      # Discovered from historical evidence
    MERGED = "merged"        # Default edge elevated by learned statistics


# ── Data Structures ───────────────────────────────────────────────────


@dataclass
class MinedEdge:
    """A mined dependency with full statistics.

    Metrics:
      support:         how many times A→B was observed
      confidence:      P(B|A) — how often B follows A
      lift:            P(B|A) / P(B) — >1.0 means B is likelier after A
    """

    source_system: str
    target_system: str
    support: int = 0
    confidence: float = 0.0
    lift: float = 1.0
    total_observations: int = 0
    source_type: str = "activity_graph"

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source_system,
            "target": self.target_system,
            "support": self.support,
            "confidence": round(self.confidence, 3),
            "lift": round(self.lift, 3),
            "total_observations": self.total_observations,
            "source_type": self.source_type,
        }


@dataclass
class PromotionRules:
    """Thresholds a MinedEdge must pass to be promoted to the graph."""

    min_support: int = MIN_SUPPORT
    min_confidence: float = MIN_CONFIDENCE
    min_lift: float = MIN_LIFT

    def is_promotable(self, edge: MinedEdge) -> bool:
        if edge.support < self.min_support:
            return False
        if edge.confidence < self.min_confidence:
            return False
        if edge.lift < self.min_lift:
            return False
        return True


# ── Sequential Pattern Miner ──────────────────────────────────────────


class SequentialPatternMiner:
    """Mines opportunity dependency edges from historical execution data.

    Usage:
        miner = SequentialPatternMiner()
        edges = miner.mine_all(activity_store, opportunity_store, experiment_runner)
        promotable = miner.get_promotable_edges(edges)
        graph_edges = miner.merge_with_defaults(promotable, default_graph)
    """

    def __init__(self, rules: PromotionRules | None = None):
        self.rules = rules or PromotionRules()

    # ── Public API ─────────────────────────────────────────────────

    def mine_all(
        self,
        activity_store: Any | None = None,
        opportunity_store: Any | None = None,
        experiment_runner: Any | None = None,
    ) -> list[MinedEdge]:
        """Run all three mining methods and merge results by deduplication.

        When the same edge is found by multiple sources, the one with the
        highest total_observations wins (accumulates evidence).
        """
        all_edges: dict[tuple[str, str], MinedEdge] = {}

        if activity_store:
            for edge in self.mine_activity_graph(activity_store):
                key = (edge.source_system, edge.target_system)
                if key not in all_edges or edge.total_observations > all_edges[key].total_observations:
                    all_edges[key] = edge

        if opportunity_store:
            for edge in self.mine_opportunity_store(opportunity_store):
                key = (edge.source_system, edge.target_system)
                if key not in all_edges or edge.total_observations > all_edges[key].total_observations:
                    all_edges[key] = edge

        if experiment_runner:
            for edge in self.mine_experiments(experiment_runner):
                key = (edge.source_system, edge.target_system)
                if key not in all_edges or edge.total_observations > all_edges[key].total_observations:
                    all_edges[key] = edge

        return list(all_edges.values())

    def mine_activity_graph(
        self, activity_store: Any
    ) -> list[MinedEdge]:
        """Mine ActivityGraph for sequential tool_call patterns.

        Extracts (A → B) pairs from chronologically ordered tool_calls
        within the same activity tree. Maps tool labels to canonical
        system names. Counts frequencies and computes confidence + lift.
        """
        try:
            nodes = activity_store.get_nodes_by_type("tool_call", limit=1000)
            if not nodes:
                return []
        except Exception as e:
            logger.warning(f"Activity graph mining: cannot fetch nodes — {e}")
            return []

        # Group by activity_id
        activities: dict[str, list[Any]] = defaultdict(list)
        for node in nodes:
            aid = getattr(node, "activity_id", "") or ""
            if aid:
                activities[aid].append(node)

        # Counters
        pair_count: dict[tuple[str, str], int] = defaultdict(int)
        src_count: dict[str, int] = defaultdict(int)
        tgt_count: dict[str, int] = defaultdict(int)
        total_pairs = 0

        for aid, activity_nodes in activities.items():
            completed = [
                n for n in activity_nodes
                if getattr(n, "status", "") in ("COMPLETED", "SUCCESS", "DONE")
            ]
            if len(completed) < 2:
                continue
            completed.sort(key=lambda n: (
                getattr(n, "completed_at", "") or getattr(n, "created_at", "") or ""
            ))

            # Generate all ordered pairs (A → B) where A completed before B
            for i in range(len(completed) - 1):
                for j in range(i + 1, len(completed)):
                    src = _tool_to_system(
                        getattr(completed[i], "label", "") or ""
                    )
                    tgt = _tool_to_system(
                        getattr(completed[j], "label", "") or ""
                    )
                    if src != tgt:  # skip self-loops
                        pair_count[(src, tgt)] += 1
                        src_count[src] += 1
                        tgt_count[tgt] += 1
                        total_pairs += 1

        if total_pairs == 0:
            return []

        return self._build_edges(
            pair_count, src_count, tgt_count, total_pairs, "activity_graph"
        )

    def mine_opportunity_store(
        self, opportunity_store: Any
    ) -> list[MinedEdge]:
        """Mine OpportunityStore for chronological completion sequences.

        Looks at completed opportunities sorted by completion time.
        (A → B) is counted when A completed before B was selected.
        """
        try:
            records = opportunity_store.list_records(limit=500)
            if not records:
                return []
        except Exception as e:
            logger.warning(f"Opportunity store mining: cannot fetch records — {e}")
            return []

        completed = [
            r for r in records
            if r.actual_success and r.completed_at and r.selected_at
        ]
        if len(completed) < 2:
            return []
        completed.sort(key=lambda r: r.completed_at or "")

        pair_count: dict[tuple[str, str], int] = defaultdict(int)
        src_count: dict[str, int] = defaultdict(int)
        tgt_count: dict[str, int] = defaultdict(int)
        total_pairs = 0

        for i in range(len(completed) - 1):
            for j in range(i + 1, len(completed)):
                a, b = completed[i], completed[j]
                # B must have been selected after A completed
                if b.selected_at >= a.completed_at:
                    src, tgt = a.target_system, b.target_system
                    if src != tgt:
                        pair_count[(src, tgt)] += 1
                        src_count[src] += 1
                        tgt_count[tgt] += 1
                        total_pairs += 1

        if total_pairs == 0:
            return []

        return self._build_edges(
            pair_count, src_count, tgt_count, total_pairs, "opportunity_store"
        )

    def mine_experiments(
        self, experiment_runner: Any
    ) -> list[MinedEdge]:
        """Mine experiment history for sequential improvement patterns.

        Groups experiments by timestamp proximity. Adjacent experiments
        where the earlier one succeeded and later one also succeeded
        form (A → B) candidates.
        """
        try:
            experiments = experiment_runner.get_experiments(limit=200)
            if not experiments:
                return []
        except Exception as e:
            logger.warning(f"Experiment mining: cannot fetch experiments — {e}")
            return []

        # Extract into comparable records
        records = []
        for exp in experiments:
            ts = (
                getattr(exp, "created_at", None)
                or getattr(exp, "started_at", None)
                or ""
            )
            status = (
                getattr(exp, "status", "") or ""
            )
            knob_changes = getattr(exp, "knob_changes", []) or []
            systems = set()
            for change in knob_changes:
                name = change.knob_name if hasattr(change, "knob_name") else str(change)
                systems.add(name)
            if ts and status:
                records.append({
                    "timestamp": ts,
                    "success": "complete" in status.lower() and "fail" not in status.lower(),
                    "systems": systems or {"unknown"},
                })

        if len(records) < 2:
            return []
        records.sort(key=lambda r: r["timestamp"])

        pair_count: dict[tuple[str, str], int] = defaultdict(int)
        src_count: dict[str, int] = defaultdict(int)
        tgt_count: dict[str, int] = defaultdict(int)
        total_pairs = 0

        for i in range(len(records) - 1):
            a, b = records[i], records[i + 1]
            if not a["success"] or not b["success"]:
                continue
            for src_sys in a["systems"]:
                for tgt_sys in b["systems"]:
                    if src_sys != tgt_sys:
                        pair_count[(src_sys, tgt_sys)] += 1
                        src_count[src_sys] += 1
                        tgt_count[tgt_sys] += 1
                        total_pairs += 1

        if total_pairs == 0:
            return []

        return self._build_edges(
            pair_count, src_count, tgt_count, total_pairs, "experiment"
        )

    # ── Merge ──────────────────────────────────────────────────────

    def merge_with_defaults(
        self,
        learned_edges: list[MinedEdge],
        default_graph: Any | None = None,
    ) -> list[Any]:
        """Merge learned edges with default dependency graph.

        Strategy:
          - Default edges are always kept.
          - If a learned edge exists for the same (src → tgt) AND its
            confidence exceeds the default's, the MERGED edge takes the
            learned statistics with EdgeSource.MERGED.
          - Learned edges not in the default graph are added if promotable.
          - Learned edges that fail promotion are discarded.

        Returns:
            Combined list of OpportunityGraphEdge ready for the graph.
        """
        from core.opportunity.graph import (
            OpportunityGraphEdge,
            build_default_graph,
        )

        graph = default_graph or build_default_graph()
        result: list[Any] = []
        learned_map: dict[tuple[str, str], MinedEdge] = {
            (e.source_system, e.target_system): e for e in learned_edges
        }
        seen_pairs: set[tuple[str, str]] = set()

        # Process default edges
        for edge in graph.edges:
            pair = (edge.source_system, edge.target_system)
            learned = learned_map.get(pair)
            if learned and learned.confidence > edge.confidence:
                # Learned statistics exceed default → promote to merged
                merged = OpportunityGraphEdge(
                    source_system=edge.source_system,
                    target_system=edge.target_system,
                    confidence=learned.confidence,
                    evidence_count=learned.support,
                    source_type=EdgeSource.MERGED.value,
                )
                merged.lift = learned.lift
                merged.support_count = learned.support
                result.append(merged)
            else:
                result.append(edge)
            seen_pairs.add(pair)

        # Add promotable learned edges not in defaults
        for pair, learned in learned_map.items():
            if pair in seen_pairs:
                continue
            if self.rules.is_promotable(learned):
                promoted = OpportunityGraphEdge(
                    source_system=learned.source_system,
                    target_system=learned.target_system,
                    confidence=learned.confidence,
                    evidence_count=learned.support,
                    source_type=EdgeSource.LEARNED.value,
                )
                promoted.lift = learned.lift
                promoted.support_count = learned.support
                result.append(promoted)
                seen_pairs.add(pair)

        return result

    # ── Promotion ──────────────────────────────────────────────────

    def get_promotable_edges(
        self, edges: list[MinedEdge]
    ) -> list[MinedEdge]:
        """Filter edges that pass all promotion gates."""
        return [e for e in edges if self.rules.is_promotable(e)]

    # ── Statistics ─────────────────────────────────────────────────

    @staticmethod
    def compute_confidence(count_ab: int, count_a: int) -> float:
        """P(B|A) = count(A→B) / count(A→any)."""
        if count_a <= 0:
            return 0.0
        return count_ab / count_a

    @staticmethod
    def compute_lift(confidence: float, count_b: int, total: int) -> float:
        """P(B|A) / P(B) = confidence / (count(B)/total)."""
        if total <= 0:
            return 1.0
        prob_b = count_b / total
        if prob_b <= 0:
            return 1.0
        return confidence / prob_b

    # ── Internal ───────────────────────────────────────────────────

    def _build_edges(
        self,
        pair_count: dict[tuple[str, str], int],
        src_count: dict[str, int],
        tgt_count: dict[str, int],
        total_pairs: int,
        source_type: str,
    ) -> list[MinedEdge]:
        """Convert raw counters into MinedEdge list with confidence + lift."""
        edges: list[MinedEdge] = []

        for (src, tgt), count_ab in pair_count.items():
            count_a = src_count.get(src, 0)
            count_b = tgt_count.get(tgt, 0)
            confidence = self.compute_confidence(count_ab, count_a)
            lift = self.compute_lift(confidence, count_b, total_pairs)

            edges.append(MinedEdge(
                source_system=src,
                target_system=tgt,
                support=count_ab,
                confidence=confidence,
                lift=lift,
                total_observations=total_pairs,
                source_type=source_type,
            ))

        edges.sort(key=lambda e: e.support, reverse=True)
        return edges
