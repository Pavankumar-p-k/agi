"""Autonomous Roadmap Generation (Phase 23) — produces multi-phase improvement plans.

Phase 17 finds opportunities. Phase 22 finds bottlenecks. Phase 19/20 models
dependencies. Phase 15.2 optimizes portfolios. Phase 23 combines them into a
structured, sequenced improvement roadmap.

The core algorithm:
  1. Score each opportunity with compounded priority:
       priority = base_score * unlock_value * (1 + bottleneck_weight)
  2. Compute dependency depth via DAG topological ordering
     (items that unlock others come first)
  3. Sort by depth ascending, priority descending within depth
  4. Group into named phases respecting item-per-phase limits
  5. Attach rationale explaining sequencing decisions

Example output:

  Quarter 1:
    1. Improve Opportunity Discovery (priority=0.97)
       - Unlocks self_modification, build_benchmark
    2. Improve Self Modification (priority=0.74)
       - Depends on: opportunity_discovery

  Quarter 2:
    3. Expand browser automation (priority=0.54)
       ...
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────

# Default items per phase
ITEMS_PER_PHASE = 3

# Phase naming prefix
PHASE_NAMES = [
    "Quarter 1",
    "Quarter 2",
    "Quarter 3",
    "Quarter 4",
    "Phase 5",
    "Phase 6",
    "Phase 7",
    "Phase 8",
    "Phase 9",
    "Phase 10",
]


# ── Models ────────────────────────────────────────────────────────────


@dataclass
class RoadmapItem:
    """A single improvement target within a roadmap phase.

    Attributes:
        system_name: canonical system name
        opportunity_id: source opportunity ID
        description: human-readable improvement description
        compounded_priority: final priority score (base * unlock * bottleneck)
        dependency_depth: position in dependency DAG (0 = no prerequisites)
        dependencies: system names that should be improved before this
        unlocks: system names that this improvement enables
        current_score: current capability score (0-1)
        expected_gain: compounded_priority (proxy for expected delta)
        rationale: why this item appears in this phase
    """

    system_name: str
    opportunity_id: str
    description: str
    compounded_priority: float
    dependency_depth: int = 0
    dependencies: list[str] = field(default_factory=list)
    unlocks: list[str] = field(default_factory=list)
    current_score: float = 0.0
    expected_gain: float = 0.0
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "system": self.system_name,
            "priority": round(self.compounded_priority, 3),
            "depth": self.dependency_depth,
            "dependencies": self.dependencies,
            "unlocks": self.unlocks[:3],
            "current_score": round(self.current_score, 3),
            "expected_gain": round(self.expected_gain, 3),
            "rationale": self.rationale,
        }


@dataclass
class RoadmapPhase:
    """A named phase containing a group of improvements.

    Attributes:
        name: display name (e.g. "Quarter 1")
        items: planned improvements in execution order
        total_priority: sum of compounded_priority for this phase
        rationale: high-level rationale for this phase's focus
    """

    name: str
    items: list[RoadmapItem] = field(default_factory=list)
    total_priority: float = 0.0
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "item_count": len(self.items),
            "total_priority": round(self.total_priority, 3),
            "items": [i.to_dict() for i in self.items],
            "rationale": self.rationale,
        }


@dataclass
class Roadmap:
    """A complete multi-phase improvement roadmap.

    Attributes:
        phases: ordered list of phases
        total_priority: sum of all item priorities across phases
        total_items: number of improvement items
        generated_at: when this roadmap was created
        summary: one-line summary of the plan
    """

    phases: list[RoadmapPhase] = field(default_factory=list)
    total_priority: float = 0.0
    total_items: int = 0
    generated_at: datetime | None = None
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "phases": [p.to_dict() for p in self.phases],
            "total_priority": round(self.total_priority, 3),
            "total_items": self.total_items,
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
            "summary": self.summary,
        }


# ── Roadmap Generator ────────────────────────────────────────────────


class RoadmapGenerator:
    """Generates multi-phase improvement roadmaps from opportunities, graph, and bottlenecks.

    Usage:
        generator = RoadmapGenerator()
        roadmap = generator.generate(
            opportunities=opportunities,
            graph=opportunity_graph,
            bottlenecks=bottleneck_list,
        )
        print(roadmap.summary)
    """

    def __init__(self, items_per_phase: int = ITEMS_PER_PHASE):
        self.items_per_phase = items_per_phase

    def generate(
        self,
        opportunities: list[Any],
        graph: Any,
        bottlenecks: list[Any] | None = None,
        system_scores: dict[str, float] | None = None,
    ) -> Roadmap:
        """Generate a complete improvement roadmap.

        Args:
            opportunities: list of Opportunity objects (Phase 17)
            graph: OpportunityGraph (Phase 19/20)
            bottlenecks: list of Bottleneck results (Phase 22), optional
            system_scores: capability scores for current_score, optional

        Returns:
            Roadmap with phased improvement plan
        """
        now = datetime.now(timezone.utc)

        # 1. Build bottleneck map
        bottleneck_map: dict[str, float] = {}
        if bottlenecks:
            for b in bottlenecks:
                bottleneck_map[b.subsystem] = b.total_constrained_value

        # 2. Compute depth and dependencies for each node
        depth_map = self._compute_dependency_depths(graph)
        dep_map = self._compute_dependencies(graph)
        unlock_map = self._compute_unlocks(graph)

        # 3. Score and build roadmap items
        items: list[RoadmapItem] = []
        for opp in opportunities:
            node = graph.get_node(opp.target_system)
            if node is None:
                continue

            # Base score: use node's base_score if opportunity attached,
            # otherwise compute from the opportunity's own dimensions
            if node.opportunity is not None:
                base = node.base_score
            else:
                base = (
                    opp.bottleneck_impact
                    * opp.improvement_headroom
                    * opp.success_probability
                    * opp.confidence
                    * opp.calibration_accuracy
                )
            unlock = node.unlock_value

            # Bottleneck weight: how constrained is this system
            bottleneck_w = bottleneck_map.get(opp.target_system, 0.0)

            # Final priority
            compounded = base * unlock
            priority = compounded * (1.0 + bottleneck_w)

            depth = depth_map.get(opp.target_system, 0)
            deps = dep_map.get(opp.target_system, [])
            unlocks = unlock_map.get(opp.target_system, [])
            current = (system_scores or {}).get(opp.target_system, 0.0)

            items.append(RoadmapItem(
                system_name=opp.target_system,
                opportunity_id=opp.id,
                description=opp.improvement_description,
                compounded_priority=round(priority, 3),
                dependency_depth=depth,
                dependencies=deps,
                unlocks=unlocks,
                current_score=current,
                expected_gain=round(base, 3),
                rationale="",
            ))

        if not items:
            return Roadmap(phases=[], generated_at=now, summary="No opportunities to plan.")

        # 4. Sort by depth ascending, priority descending
        items.sort(key=lambda i: (i.dependency_depth, -i.compounded_priority))

        # 5. Build phases
        phases = self._build_phases(items, graph)

        total_priority = sum(i.compounded_priority for p in phases for i in p.items)
        total_items = sum(len(p.items) for p in phases)

        summary = self._build_summary(phases, total_items)

        return Roadmap(
            phases=phases,
            total_priority=total_priority,
            total_items=total_items,
            generated_at=now,
            summary=summary,
        )

    def _compute_dependency_depths(self, graph: Any) -> dict[str, int]:
        """Compute longest path from root (no incoming) to each node.

        Items at depth 0 have no prerequisites. Depth n requires n
        sequential improvements before this item is actionable.
        """
        # Find root nodes (no incoming edges from other nodes in graph)
        all_nodes = set(graph.nodes.keys())
        has_incoming: set[str] = set()
        for node_name in all_nodes:
            for edge in graph.get_incoming(node_name):
                if edge.source_system in all_nodes:
                    has_incoming.add(node_name)

        roots = all_nodes - has_incoming
        if not roots:
            roots = all_nodes  # fallback: all are roots

        # BFS from roots, track longest path
        depth: dict[str, int] = {}
        queue: deque[tuple[str, int]] = deque()
        for r in roots:
            queue.append((r, 0))

        visited: set[str] = set()
        while queue:
            current, d = queue.popleft()
            if current in visited:
                # Update depth if this path is longer
                if d > depth.get(current, 0):
                    depth[current] = d
                continue
            visited.add(current)
            depth[current] = d

            for edge in graph.get_outgoing(current):
                if edge.target_system in all_nodes:
                    queue.append((edge.target_system, d + 1))

        # Fill missing
        for n in all_nodes:
            if n not in depth:
                depth[n] = 0

        return depth

    def _compute_dependencies(self, graph: Any) -> dict[str, list[str]]:
        """For each node, list systems that enable it (incoming edges)."""
        deps: dict[str, list[str]] = {}
        all_nodes = set(graph.nodes.keys())
        for node_name in all_nodes:
            incoming = [
                e.source_system for e in graph.get_incoming(node_name)
                if e.source_system in all_nodes
            ]
            if incoming:
                deps[node_name] = incoming
        return deps

    def _compute_unlocks(self, graph: Any) -> dict[str, list[str]]:
        """For each node, list systems it enables (outgoing edges)."""
        unlocks: dict[str, list[str]] = {}
        all_nodes = set(graph.nodes.keys())
        for node_name in all_nodes:
            outgoing = [
                e.target_system for e in graph.get_outgoing(node_name)
                if e.target_system in all_nodes
            ]
            if outgoing:
                unlocks[node_name] = outgoing
        return unlocks

    def _build_phases(
        self,
        items: list[RoadmapItem],
        graph: Any,
    ) -> list[RoadmapPhase]:
        """Group sorted items into named phases."""
        phases: list[RoadmapPhase] = []
        phase_idx = 0
        pos = 0

        while pos < len(items):
            name = self._phase_name(phase_idx)
            phase_items = items[pos:pos + self.items_per_phase]
            total = sum(i.compounded_priority for i in phase_items)

            # Build rationale per item
            for item in phase_items:
                item.rationale = self._item_rationale(item, phase_idx, graph)

            # Phase rationale
            systems = [i.system_name for i in phase_items]
            phase_rationale = (
                f"Phase focus: {', '.join(systems)}. "
                f"Total priority: {total:.3f}. "
                f"{'Foundation improvements — unlocks downstream systems.' if phase_idx == 0 else ''}"
                f"{'Builds on prior phases.' if phase_idx > 0 else ''}"
            )

            phases.append(RoadmapPhase(
                name=name,
                items=phase_items,
                total_priority=round(total, 3),
                rationale=phase_rationale,
            ))

            phase_idx += 1
            pos += self.items_per_phase

        return phases

    def _phase_name(self, idx: int) -> str:
        if idx < len(PHASE_NAMES):
            return PHASE_NAMES[idx]
        return f"Phase {idx + 1}"

    def _item_rationale(
        self,
        item: RoadmapItem,
        phase_idx: int,
        graph: Any,
    ) -> str:
        parts = []

        if item.dependency_depth == 0:
            parts.append("Root dependency — improving this unlocks downstream systems.")
        else:
            parts.append(f"Dependency depth {item.dependency_depth} — "
                         f"requires {len(item.dependencies)} prior improvements.")

        if item.unlocks:
            unlock_str = ", ".join(item.unlocks[:3])
            parts.append(f"Unlocks: {unlock_str}.")

        parts.append(f"Priority: {item.compounded_priority:.3f}.")

        return " ".join(parts)

    def _build_summary(
        self,
        phases: list[RoadmapPhase],
        total_items: int,
    ) -> str:
        if not phases:
            return "No improvements planned."

        phase_descs = []
        for p in phases:
            names = [i.system_name for i in p.items]
            phase_descs.append(f"{p.name}: {', '.join(names)}")

        return (
            f"{total_items} improvements across {len(phases)} phases. "
            + " -> ".join(phase_descs[:4])
            + ("..." if len(phases) > 4 else "")
        )
