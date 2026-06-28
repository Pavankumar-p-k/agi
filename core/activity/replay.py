"""Activity Replay DAG — read-only reconstruction and aggregation layer.

Assembles the full execution DAG for a single activity_id from all existing
storage systems. No mutation, no execution — pure aggregation and querying.

Layers:
  3A — DAG nodes + tree structure
  3B — Execution metadata (provider, tool, model, latency, cost, retries)
  3C — Decision trace (candidate scores, evidence, reasons)
  3D — Chronological timeline with DAG node cross-reference
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


# ── Replay DAG data model ────────────────────────────────────────────────────

@dataclass
class ReplayNode:
    """A single node in the replay DAG.

    Maps 1:1 to an ActivityNode, enriched with metadata from other systems.
    """
    node_id: str
    activity_id: str
    node_type: str        # goal / subgoal / agent_call / tool_call / artifact / milestone
    label: str
    status: str
    depth: int
    parent_id: str | None
    agent_id: str | None
    workflow_id: str | None

    # Timing
    started_at: str | None
    completed_at: str | None
    duration_seconds: float | None = None

    # Execution
    tool: str | None = None              # For tool_call nodes
    provider: str | None = None          # For agent_call nodes
    model: str | None = None
    retry_count: int = 0
    cost: float = 0.0

    # Input / Output
    input_preview: str = ""
    output_preview: str = ""
    error: str | None = None

    # Tree
    children: list[ReplayNode] = field(default_factory=list)

    # Cross-reference
    edges: list[ReplayEdge] = field(default_factory=list)
    timeline_index: int | None = None    # Position in flattened timeline

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    # Artifact refs (name -> artifact_id)
    artifacts: dict[str, str] = field(default_factory=dict)


@dataclass
class ReplayEdge:
    """An edge between two replay DAG nodes.

    Maps 1:1 to an ActivityEdge plus enriched metadata.
    """
    edge_id: str
    from_node_id: str
    to_node_id: str
    edge_type: str        # depends_on / produces / triggers / references
    label: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DecisionTrace:
    """Provider routing decision attached to an agent_call node.

    Maps to RoutingDecision + ScoreBreakdown + RoutingOutcome.
    """
    decision_id: str
    capability: str
    selected_provider: str
    candidates: list[CandidateScore] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    outcome: DecisionOutcome | None = None


@dataclass
class CandidateScore:
    provider_id: str
    total_score: float
    priority_score: float = 0.0
    historical_score: float = 0.0
    benchmark_score: float = 0.0
    health_score: float = 0.0
    latency_score: float = 0.0
    cost_score: float = 0.0
    budget_score: float = 0.0
    offline_score: float = 0.0
    calibration_adjustment: float = 0.0


@dataclass
class DecisionOutcome:
    success: bool
    duration_ms: float
    quality_score: float
    cost: float
    retries: int
    error: str | None = None


@dataclass
class TimelineEvent:
    """A single event in the chronological timeline.

    Each event links back to its DAG node(s) via node_id.
    """
    timestamp: float          # Unix timestamp
    label: str
    node_id: str
    node_type: str
    status: str
    duration_seconds: float | None = None
    detail: str = ""


@dataclass
class ReplayDAG:
    """Complete replay DAG for one activity.

    Immutable after construction — pure query interface.
    """
    activity_id: str
    root: ReplayNode | None
    all_nodes: dict[str, ReplayNode]   # node_id -> node
    all_edges: list[ReplayEdge]
    timeline: list[TimelineEvent]
    decisions: list[DecisionTrace]

    # Summary
    total_nodes: int = 0
    failed_nodes: int = 0
    total_duration_seconds: float = 0.0
    unique_tools: list[str] = field(default_factory=list)
    unique_providers: list[str] = field(default_factory=list)
    total_retries: int = 0
    total_cost: float = 0.0

    # Experience / Knowledge
    experience: dict[str, Any] | None = None
    knowledge: list[dict[str, Any]] = field(default_factory=list)


# ── DAG assembler ────────────────────────────────────────────────────────────

class ReplayAssembler:
    """Assembles a ReplayDAG from existing storage systems.

    Reads only — never writes. Aggregates data from:
      - ActivityStore (nodes + edges)
      - WorkflowStore (steps, context, artifacts)
      - ProviderFeedbackStore (decisions + outcomes)
      - KnowledgeStore (experiences + knowledge)
      - StrategyStore (strategy decisions)

    Call ``build(activity_id)`` to produce a ``ReplayDAG``.
    """

    def __init__(
        self,
        activity_store: Any = None,
        workflow_store: Any = None,
        feedback_store: Any = None,
        knowledge_store: Any = None,
    ):
        self._activity_store = activity_store
        self._workflow_store = workflow_store
        self._feedback_store = feedback_store
        self._knowledge_store = knowledge_store

    # ── Public API ──────────────────────────────────────────

    def build(self, activity_id: str) -> ReplayDAG:
        """Build a complete ReplayDAG for the given activity_id."""
        dag = self._build_structure(activity_id)
        self._enrich_metadata(dag)
        self._attach_decisions(dag)
        self._build_timeline(dag)
        self._compute_summary(dag)
        self._attach_knowledge(dag)
        return dag

    # ── Phase 3A: Structure ─────────────────────────────────

    def _build_structure(self, activity_id: str) -> ReplayDAG:
        """Load nodes and edges from ActivityStore and assemble the tree."""
        nodes_raw = self._get_activity_tree(activity_id) or []
        edges_raw = self._get_activity_edges(activity_id) or []

        all_nodes: dict[str, ReplayNode] = {}
        root: ReplayNode | None = None

        # Convert raw dicts to ReplayNodes
        for n in nodes_raw:
            node = self._raw_to_node(n)
            all_nodes[node.node_id] = node
            if node.depth == 0:
                root = node

        # Convert edges
        edges = [self._raw_to_edge(e) for e in edges_raw]

        # Build tree (parent -> children)
        for node in all_nodes.values():
            if node.parent_id and node.parent_id in all_nodes:
                parent = all_nodes[node.parent_id]
                if node not in parent.children:
                    parent.children.append(node)

        return ReplayDAG(
            activity_id=activity_id,
            root=root,
            all_nodes=all_nodes,
            all_edges=edges,
            timeline=[],
            decisions=[],
        )

    def _raw_to_node(self, raw: dict) -> ReplayNode:
        """Convert a raw ActivityNode dict to a ReplayNode."""
        node_id = raw.get("node_id", "") or raw.get("id", "")
        started_at = raw.get("started_at") or None
        completed_at = raw.get("completed_at") or None

        duration = None
        if started_at and completed_at:
            try:
                t0 = _parse_ts(started_at)
                t1 = _parse_ts(completed_at)
                duration = (t1 - t0).total_seconds()
            except Exception:
                pass

        output = raw.get("output") or raw.get("output_json") or raw.get("output_data") or {}
        if isinstance(output, str):
            output = _try_parse_json(output) or {}

        input_data = raw.get("input") or raw.get("input_json") or raw.get("input_data") or {}
        if isinstance(input_data, str):
            input_data = _try_parse_json(input_data) or {}

        artifacts = {}
        art_raw = raw.get("artifacts") or raw.get("artifacts_json") or {}
        if isinstance(art_raw, str):
            art_raw = _try_parse_json(art_raw) or {}
        if isinstance(art_raw, dict):
            artifacts = art_raw

        metadata = raw.get("metadata") or raw.get("metadata_json") or {}
        if isinstance(metadata, str):
            metadata = _try_parse_json(metadata) or {}

        return ReplayNode(
            node_id=node_id,
            activity_id=raw.get("activity_id", ""),
            node_type=raw.get("node_type", "unknown"),
            label=raw.get("label", raw.get("title", node_id[:12])),
            status=raw.get("status", "unknown"),
            depth=int(raw.get("depth", 0)),
            parent_id=raw.get("parent_id") or None,
            agent_id=raw.get("agent_id") or None,
            workflow_id=raw.get("workflow_id") or None,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration,
            input_preview=_preview(input_data, 200),
            output_preview=_preview(output, 200),
            error=_extract_error(output),
            artifacts=artifacts,
            metadata=metadata,
        )

    def _raw_to_edge(self, raw: dict) -> ReplayEdge:
        return ReplayEdge(
            edge_id=raw.get("edge_id", "") or raw.get("id", ""),
            from_node_id=raw.get("from_node_id", ""),
            to_node_id=raw.get("to_node_id", ""),
            edge_type=raw.get("edge_type", "depends_on"),
            label=f"{raw.get('edge_type', 'depends_on')}: {raw.get('from_node_id', '?')[:8]} -> "
                  f"{raw.get('to_node_id', '?')[:8]}",
            metadata=raw.get("metadata") or raw.get("metadata_json") or {},
        )

    # ── Phase 3B: Execution Metadata ────────────────────────

    def _enrich_metadata(self, dag: ReplayDAG) -> None:
        """Attach workflow step details, provider info, tool metadata to nodes."""
        for node in dag.all_nodes.values():
            # Tool calls: metadata about the tool
            if node.node_type == "tool_call":
                self._enrich_tool_call(node)
            # Agent calls: provider/decision data
            elif node.node_type == "agent_call":
                self._enrich_agent_call(node, dag)
            # Workflow: step-level data
            if node.workflow_id:
                self._enrich_workflow(node)

    def _enrich_tool_call(self, node: ReplayNode) -> None:
        """Extract tool name from label or input for tool_call nodes."""
        # Label often starts with the tool name
        tool = node.metadata.get("tool") if isinstance(node.metadata, dict) else None
        if not tool:
            tool = node.label.split("(")[0].split(":")[0].strip()
        node.tool = tool

        # Input preview
        if node.input_preview:
            node.tool = node.tool or node.input_preview.split("(")[0].strip()
            # Extract args portion
            if "(" in node.input_preview:
                node.metadata["args"] = node.input_preview.split("(", 1)[1].rstrip(")")

    def _enrich_agent_call(self, node: ReplayNode, dag: ReplayDAG) -> None:
        """Extract provider info for agent_call nodes."""
        meta = node.metadata if isinstance(node.metadata, dict) else {}
        node.provider = meta.get("provider") or node.agent_id or ""
        node.model = meta.get("model", "")

    def _enrich_workflow(self, node: ReplayNode) -> None:
        """Attach workflow step data if workflow store is available."""
        if not self._workflow_store:
            return
        try:
            steps = self._workflow_store.get_workflow(node.workflow_id)
            if hasattr(steps, "steps"):
                for step in steps.steps if hasattr(steps, "steps") else []:
                    if step.get("step_id") == node.node_id:
                        node.retry_count = step.get("retry_count", 0)
                        node.error = step.get("error") or node.error
                        node.metadata["timeout_seconds"] = step.get("timeout_seconds")
                        break
        except Exception as e:
            logger.debug("enrich_workflow %s: %s", node.workflow_id, e)

    # ── Phase 3C: Decision Trace ────────────────────────────

    def _attach_decisions(self, dag: ReplayDAG) -> None:
        """Attach provider routing decisions to agent_call nodes."""
        if not self._feedback_store:
            return

        for node in dag.all_nodes.values():
            if node.node_type != "agent_call":
                continue

            decision = self._load_decision_for_node(node)
            if decision:
                dag.decisions.append(decision)

    def _load_decision_for_node(self, node: ReplayNode) -> DecisionTrace | None:
        """Load RoutingDecision from feedback store for this node."""
        try:
            if not self._feedback_store:
                return None

            # Find decisions matching this agent call
            decisions = self._get_decisions_for_agent(node)
            if not decisions:
                return None

            dec = decisions[0]  # Most recent matching decision

            candidates = []
            for cs in (dec.get("candidate_scores") or []):
                candidates.append(CandidateScore(
                    provider_id=cs.get("provider_id", "?"),
                    total_score=cs.get("total_score", 0),
                    priority_score=cs.get("priority_score", 0),
                    historical_score=cs.get("historical_score", 0),
                    benchmark_score=cs.get("benchmark_score", 0),
                    health_score=cs.get("health_score", 0),
                    latency_score=cs.get("latency_score", 0),
                    cost_score=cs.get("cost_score", 0),
                    budget_score=cs.get("budget_score", 0),
                    offline_score=cs.get("offline_score", 0),
                    calibration_adjustment=cs.get("calibration_adjustment", 0),
                ))

            reasons = []
            if candidates:
                selected = next((c for c in candidates if c.provider_id == dec.get("selected_provider")), None)
                if selected:
                    # Build interpretable reasons from score dimensions
                    score_parts = [
                        ("priority", selected.priority_score),
                        ("historical", selected.historical_score),
                        ("benchmark", selected.benchmark_score),
                        ("health", selected.health_score),
                        ("latency", selected.latency_score),
                        ("cost", selected.cost_score),
                        ("offline", selected.offline_score),
                        ("calibration", selected.calibration_adjustment),
                    ]
                    score_parts.sort(key=lambda x: -abs(x[1]))
                    for name, val in score_parts[:4]:
                        if abs(val) > 0.01:
                            reasons.append(f"{name}={val:+.2f}")

            outcome = None
            outcomes = self._get_outcomes_for_decision(dec.get("decision_id", ""))
            if outcomes:
                oc = outcomes[0]
                outcome = DecisionOutcome(
                    success=oc.get("success", False),
                    duration_ms=oc.get("duration_ms", 0),
                    quality_score=oc.get("quality_score", 0),
                    cost=oc.get("cost", 0),
                    retries=oc.get("retries", 0),
                    error=oc.get("error"),
                )

            return DecisionTrace(
                decision_id=dec.get("decision_id", ""),
                capability=dec.get("capability", ""),
                selected_provider=dec.get("selected_provider", ""),
                candidates=candidates,
                reasons=reasons or ["(no detailed scores)"],
                outcome=outcome,
            )

        except Exception as e:
            logger.debug("load_decision_for_node %s: %s", node.node_id, e)
            return None

    def _get_decisions_for_agent(self, node: ReplayNode) -> list[dict]:
        """Fetch decisions from the feedback store."""
        if not self._feedback_store:
            return []
        try:
            store = self._feedback_store
            # Try get_decisions first
            if hasattr(store, "get_decisions"):
                return store.get_decisions(limit=10)
            # Try get_routing_decisions
            if hasattr(store, "get_routing_decisions"):
                return store.get_routing_decisions(limit=10)
            # Direct SQL as last resort
            return self._query_decisions_from_db(store)
        except Exception:
            return []

    def _get_outcomes_for_decision(self, decision_id: str) -> list[dict]:
        """Fetch outcomes matching a decision."""
        if not self._feedback_store:
            return []
        try:
            store = self._feedback_store
            if hasattr(store, "get_outcomes_for_decision"):
                return store.get_outcomes_for_decision(decision_id)
            return []
        except Exception:
            return []

    def _query_decisions_from_db(self, store) -> list[dict]:
        """Fallback: fetch decisions directly if store API not available."""
        try:
            if hasattr(store, "_db_path") or hasattr(store, "_db"):
                return []
            return []
        except Exception:
            return []

    # ── Phase 3D: Timeline ──────────────────────────────────

    def _build_timeline(self, dag: ReplayDAG) -> None:
        """Flatten all nodes into chronological timeline."""
        events: list[TimelineEvent] = []

        for node in dag.all_nodes.values():
            ts = self._node_timestamp(node)
            if ts is None:
                continue

            detail_parts = []
            if node.tool:
                detail_parts.append(f"tool={node.tool}")
            if node.provider:
                detail_parts.append(f"provider={node.provider}")
            if node.retry_count:
                detail_parts.append(f"retries={node.retry_count}")
            if node.error:
                detail_parts.append(f"error={node.error[:60]}")

            events.append(TimelineEvent(
                timestamp=ts,
                label=node.label[:80],
                node_id=node.node_id,
                node_type=node.node_type,
                status=node.status,
                duration_seconds=node.duration_seconds,
                detail=" | ".join(detail_parts) if detail_parts else "",
            ))

        events.sort(key=lambda e: e.timestamp)

        # Assign timeline indices to nodes
        for i, ev in enumerate(events):
            ev.timestamp = float(i)  # Normalize to sequential index
            node = dag.all_nodes.get(ev.node_id)
            if node:
                node.timeline_index = i

        dag.timeline = events

    def _node_timestamp(self, node: ReplayNode) -> float | None:
        """Get a numeric timestamp for a node, for timeline sorting."""
        ts_str = node.started_at or node.metadata.get("created_at") if isinstance(node.metadata, dict) else None
        if ts_str:
            try:
                return _parse_ts(ts_str).timestamp()
            except Exception:
                pass
        return None

    # ── Summary ─────────────────────────────────────────────

    def _compute_summary(self, dag: ReplayDAG) -> None:
        """Compute aggregate metrics."""
        dag.total_nodes = len(dag.all_nodes)
        dag.failed_nodes = sum(1 for n in dag.all_nodes.values() if n.status in ("FAILED", "ERROR"))
        dag.total_retries = sum(n.retry_count for n in dag.all_nodes.values())
        dag.total_cost = sum(n.cost for n in dag.all_nodes.values())

        tools: set[str] = set()
        providers: set[str] = set()
        for n in dag.all_nodes.values():
            if n.tool:
                tools.add(n.tool)
            if n.provider:
                providers.add(n.provider)
        dag.unique_tools = sorted(tools)
        dag.unique_providers = sorted(providers)

        # Duration from root node
        if dag.root and dag.root.duration_seconds:
            dag.total_duration_seconds = dag.root.duration_seconds
        elif dag.timeline:
            dag.total_duration_seconds = dag.timeline[-1].timestamp - dag.timeline[0].timestamp

    def _attach_knowledge(self, dag: ReplayDAG) -> None:
        """Attach experience summaries and knowledge items for this activity."""
        if not self._knowledge_store:
            return
        try:
            store = self._knowledge_store
            exp = None
            if hasattr(store, "get_experience"):
                exp = store.get_experience(dag.activity_id)
            elif hasattr(store, "get_experience_summary"):
                exp = store.get_experience_summary(dag.activity_id)
            if exp:
                dag.experience = exp if isinstance(exp, dict) else exp.__dict__ if hasattr(exp, "__dict__") else {}

            knowledge = []
            if hasattr(store, "search_knowledge"):
                knowledge = store.search_knowledge(
                    min_confidence=0.0, min_evidence=0, limit=10
                )
            elif hasattr(store, "get_knowledge_items"):
                knowledge = store.get_knowledge_items(limit=10)
            dag.knowledge = [
                k if isinstance(k, dict) else (k.__dict__ if hasattr(k, "__dict__") else {"claim": str(k)})
                for k in (knowledge or [])
            ]
        except Exception as e:
            logger.debug("attach_knowledge: %s", e)

    # ── Data access ─────────────────────────────────────────

    def _get_activity_tree(self, activity_id: str) -> list[dict]:
        """Fetch activity tree from the store, handling multiple return formats."""
        if not self._activity_store:
            return []
        try:
            raw = self._activity_store.get_activity_tree(activity_id)
            # Handle list[ActivityNode] vs list[dict] vs tuple
            if raw is None:
                return []
            if isinstance(raw, tuple):
                raw = list(raw)
            result = []
            for item in raw:
                if hasattr(item, "__dict__"):
                    result.append(item.__dict__)
                elif isinstance(item, dict):
                    result.append(item)
                else:
                    result.append({})
            return result
        except Exception as e:
            logger.debug("get_activity_tree %s: %s", activity_id, e)
            return []

    def _get_activity_edges(self, activity_id: str) -> list[dict]:
        """Fetch edges for the activity."""
        if not self._activity_store:
            return []
        try:
            edges = []
            # Try get_edges with activity_id filter
            if hasattr(self._activity_store, "get_edges"):
                raw_edges = self._activity_store.get_edges(activity_id=activity_id)
                for e in (raw_edges or []):
                    if hasattr(e, "__dict__"):
                        edges.append(e.__dict__)
                    elif isinstance(e, dict):
                        edges.append(e)
            return edges
        except Exception as e:
            logger.debug("get_activity_edges %s: %s", activity_id, e)
            return []


# ── Utility functions ────────────────────────────────────────────────────────

def _parse_ts(ts: str) -> datetime:
    """Parse an ISO 8601 timestamp string."""
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _try_parse_json(s: str) -> dict | None:
    """Try to parse a JSON string, return None on failure."""
    import json
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return None


def _preview(data: Any, max_len: int = 200) -> str:
    """Convert data to a short string preview."""
    if not data:
        return ""
    if isinstance(data, str):
        return data[:max_len]
    import json
    try:
        s = json.dumps(data, default=str)[:max_len]
        return s
    except Exception:
        return str(data)[:max_len]


def _extract_error(output: Any) -> str | None:
    """Extract error message from node output."""
    if not output:
        return None
    if isinstance(output, dict):
        err = output.get("error") or output.get("exception") or output.get("message", "")
        return str(err)[:200] if err else None
    return None
