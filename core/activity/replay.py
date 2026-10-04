"""Activity Replay DAG — reconstructs execution traces for audit/replay.

Contract: tests/unit/test_activity_replay.py (3A structure, 3B metadata,
3C decision traces, 3D timeline, summary, edge cases) and the serialization
consumed by tests/unit/test_activity_replay_routes.py.

Input stores may hand back plain dicts (test stores) or dataclass objects
(core.activity.storage ActivityNode/ActivityEdge, feedback store
RoutingDecision/RoutingOutcome); every read goes through _get().
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

_INF = float("inf")


# ── input helpers ───────────────────────────────────────────────────────────

def _get(raw: Any, key: str, default: Any = None) -> Any:
    if isinstance(raw, dict):
        return raw.get(key, default)
    return getattr(raw, key, default)


def _parse_ts(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _ts_float(value: Any) -> Optional[float]:
    ts = _parse_ts(value)
    if ts is None:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.timestamp()


def _iso(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        return value.isoformat()
    return value if isinstance(value, str) else None


def _duration_seconds(raw: Any) -> Optional[float]:
    start = _ts_float(_get(raw, "started_at"))
    end = _ts_float(_get(raw, "completed_at"))
    if start is None or end is None:
        return None
    return max(0.0, end - start)


def _json_object(*candidates: Any) -> dict:
    for candidate in candidates:
        if isinstance(candidate, dict):
            return dict(candidate)
        if isinstance(candidate, str) and candidate.strip():
            try:
                parsed = json.loads(candidate)
            except ValueError:
                return {}
            if isinstance(parsed, dict):
                return parsed
            return {}
    return {}


def _preview(raw_json: Any, limit: int = 2000) -> str:
    if not isinstance(raw_json, str) or not raw_json.strip():
        return ""
    try:
        parsed = json.loads(raw_json)
    except ValueError:
        return ""
    if parsed is None:
        return ""
    if isinstance(parsed, (dict, list)):
        text = json.dumps(parsed, ensure_ascii=False, default=str)
    else:
        text = str(parsed)
    return text[:limit]


def _error_from_output(raw: Any) -> Optional[str]:
    output = _get(raw, "output_json")
    if isinstance(output, str) and output.strip():
        try:
            parsed = json.loads(output)
        except ValueError:
            return None
        if isinstance(parsed, dict):
            err = parsed.get("error")
            if err:
                return err if isinstance(err, str) else json.dumps(err, default=str)
    return None


def _status_str(raw: Any) -> str:
    status = _get(raw, "status")
    if status is None:
        return ""
    return str(getattr(status, "value", status))


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# ── dataclasses ─────────────────────────────────────────────────────────────

@dataclass
class CandidateScore:
    provider_id: str = ""
    total_score: float = 0.0
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
    success: bool = False
    duration_ms: float = 0.0
    quality_score: float = 0.0
    cost: float = 0.0
    retries: int = 0
    error: Optional[str] = None


@dataclass
class DecisionTrace:
    decision_id: str = ""
    capability: str = ""
    selected_provider: str = ""
    candidates: list[CandidateScore] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    outcome: Optional[DecisionOutcome] = None


@dataclass
class ReplayNode:
    node_id: str = ""
    activity_id: str = ""
    node_type: str = ""
    label: str = ""
    status: str = ""
    depth: Optional[int] = None
    parent_id: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    input_preview: str = ""
    output_preview: str = ""
    error: Optional[str] = None
    tool: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    retry_count: int = 0
    cost: float = 0.0
    agent_id: Optional[str] = None
    workflow_id: Optional[str] = None
    timeline_index: Optional[int] = None
    metadata: dict = field(default_factory=dict)
    artifacts: dict = field(default_factory=dict)
    children: list["ReplayNode"] = field(default_factory=list)


@dataclass
class ReplayEdge:
    edge_id: str = ""
    from_node_id: str = ""
    to_node_id: str = ""
    edge_type: str = ""
    label: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class TimelineEvent:
    timestamp: float = 0.0
    label: str = ""
    node_id: str = ""
    node_type: str = ""
    status: str = ""
    duration_seconds: Optional[float] = None
    detail: str = ""


@dataclass
class ReplayDAG:
    activity_id: str = ""
    root: Optional[ReplayNode] = None
    all_nodes: dict[str, ReplayNode] = field(default_factory=dict)
    all_edges: list[ReplayEdge] = field(default_factory=list)
    timeline: list[TimelineEvent] = field(default_factory=list)
    decisions: list[DecisionTrace] = field(default_factory=list)
    total_nodes: int = 0
    failed_nodes: int = 0
    unique_tools: list[str] = field(default_factory=list)
    unique_providers: list[str] = field(default_factory=list)
    total_retries: int = 0
    total_cost: float = 0.0
    total_duration_seconds: float = 0.0
    experience: Optional[dict] = None
    knowledge: list = field(default_factory=list)


# ── assembler ───────────────────────────────────────────────────────────────

class ReplayAssembler:
    """Builds a ReplayDAG from an activity store (plus optional feedback and
    knowledge stores for decision traces and attached experience)."""

    def __init__(
        self,
        activity_store: Any = None,
        feedback_store: Any = None,
        knowledge_store: Any = None,
        workflow_store: Any = None,
        **_ignored: Any,
    ) -> None:
        self._activity_store = activity_store
        self._feedback_store = feedback_store
        self._knowledge_store = knowledge_store
        self._workflow_store = workflow_store

    def build(self, activity_id: str) -> ReplayDAG:
        all_nodes = self._load_nodes(activity_id)
        self._assemble_children(all_nodes)
        root = self._select_root(all_nodes)
        edges = self._load_edges(activity_id, all_nodes)
        timeline = self._build_timeline(all_nodes)
        decisions = self._build_decisions()
        experience, knowledge = self._load_knowledge(activity_id)
        nodes = list(all_nodes.values())
        failed = sum(1 for n in nodes if n.status.upper() == "FAILED")
        durations = [n.duration_seconds for n in nodes if n.duration_seconds is not None]
        if root is not None and root.duration_seconds is not None:
            total_duration = root.duration_seconds
        elif durations:
            total_duration = max(durations)
        else:
            total_duration = 0.0
        return ReplayDAG(
            activity_id=activity_id,
            root=root,
            all_nodes=all_nodes,
            all_edges=edges,
            timeline=timeline,
            decisions=decisions,
            total_nodes=len(nodes),
            failed_nodes=failed,
            unique_tools=sorted({n.tool for n in nodes if n.tool}),
            unique_providers=sorted({n.provider for n in nodes if n.provider}),
            total_retries=sum(n.retry_count for n in nodes),
            total_cost=sum(n.cost for n in nodes),
            total_duration_seconds=total_duration,
            experience=experience,
            knowledge=knowledge,
        )

    # ── nodes ───────────────────────────────────────────────────────────────

    def _load_nodes(self, activity_id: str) -> dict[str, ReplayNode]:
        store = self._activity_store
        if store is None:
            return {}
        try:
            raw_nodes = store.get_activity_tree(activity_id)
        except Exception:
            logger.warning("activity tree load failed for %s", activity_id, exc_info=True)
            return {}
        all_nodes: dict[str, ReplayNode] = {}
        for raw in raw_nodes or []:
            node = self._convert_node(raw)
            if node.node_id:
                all_nodes[node.node_id] = node
        return all_nodes

    def _convert_node(self, raw: Any) -> ReplayNode:
        node_id = str(_get(raw, "node_id") or "")
        metadata = _json_object(_get(raw, "metadata"), _get(raw, "metadata_json"))
        node_type = str(_get(raw, "node_type") or "")
        label = str(_get(raw, "label") or "")
        tool = metadata.get("tool")
        if not tool and node_type == "tool_call" and label:
            tool = label.split("(", 1)[0].strip() or None
        raw_depth = _get(raw, "depth")
        return ReplayNode(
            node_id=node_id,
            activity_id=str(_get(raw, "activity_id") or ""),
            node_type=node_type,
            label=label,
            status=_status_str(raw),
            depth=_as_int(raw_depth) if raw_depth is not None else None,
            parent_id=_get(raw, "parent_id"),
            started_at=_iso(_get(raw, "started_at")),
            completed_at=_iso(_get(raw, "completed_at")),
            duration_seconds=_duration_seconds(raw),
            input_preview=_preview(_get(raw, "input_json")),
            output_preview=_preview(_get(raw, "output_json")),
            error=_error_from_output(raw),
            tool=str(tool) if tool else None,
            provider=str(metadata["provider"]) if metadata.get("provider") else None,
            model=str(metadata["model"]) if metadata.get("model") else None,
            retry_count=_as_int(metadata.get("retry_count", metadata.get("retries"))),
            cost=_as_float(metadata.get("cost")),
            agent_id=_get(raw, "agent_id"),
            workflow_id=_get(raw, "workflow_id"),
            metadata=metadata,
            artifacts=_json_object(_get(raw, "artifacts_json")),
        )

    def _assemble_children(self, all_nodes: dict[str, ReplayNode]) -> None:
        for node in all_nodes.values():
            parent_id = node.parent_id
            if not parent_id or parent_id == node.node_id:
                continue
            parent = all_nodes.get(parent_id)
            if parent is not None:
                parent.children.append(node)

    def _select_root(self, all_nodes: dict[str, ReplayNode]) -> Optional[ReplayNode]:
        nodes = list(all_nodes.values())
        for node in nodes:
            if node.depth == 0 and node.parent_id is None:
                return node
        for node in nodes:
            if node.depth == 0:
                return node
        for node in nodes:
            if node.parent_id is None:
                return node
        return nodes[0] if nodes else None

    # ── edges ───────────────────────────────────────────────────────────────

    def _load_edges(
        self, activity_id: str, all_nodes: dict[str, ReplayNode]
    ) -> list[ReplayEdge]:
        store = self._activity_store
        if store is None:
            return []
        collected: dict[tuple, ReplayEdge] = {}
        for query in [activity_id, *all_nodes.keys()]:
            try:
                raw_edges = store.get_edges(query)
            except Exception:
                continue
            for i, raw in enumerate(raw_edges or []):
                edge = self._convert_edge(raw, len(collected))
                key = (edge.edge_id or "", edge.from_node_id, edge.to_node_id, edge.edge_type)
                if key not in collected:
                    collected[key] = edge
        return list(collected.values())

    def _convert_edge(self, raw: Any, index: int) -> ReplayEdge:
        edge_id = str(_get(raw, "edge_id") or f"edge_{index}")
        from_node = str(_get(raw, "from_node_id", _get(raw, "src")) or "")
        to_node = str(_get(raw, "to_node_id", _get(raw, "dst")) or "")
        edge_type = str(_get(raw, "edge_type", _get(raw, "relation")) or "depends_on")
        metadata = _json_object(_get(raw, "metadata"), _get(raw, "metadata_json"))
        return ReplayEdge(
            edge_id=edge_id,
            from_node_id=from_node,
            to_node_id=to_node,
            edge_type=edge_type,
            label=edge_type,
            metadata=metadata,
        )

    # ── timeline ────────────────────────────────────────────────────────────

    @staticmethod
    def _timeline_sort_key(node: ReplayNode) -> float:
        start = _ts_float(node.started_at)
        if start is not None:
            return start
        completed = _ts_float(node.completed_at)
        return completed if completed is not None else _INF

    @staticmethod
    def _timeline_detail(node: ReplayNode) -> str:
        if node.node_type == "tool_call" and node.tool:
            return f"tool={node.tool}"
        if node.node_type == "agent_call" and node.provider:
            return f"provider={node.provider}"
        return ""

    def _build_timeline(self, all_nodes: dict[str, ReplayNode]) -> list[TimelineEvent]:
        ordered = sorted(all_nodes.values(), key=self._timeline_sort_key)
        events: list[TimelineEvent] = []
        for index, node in enumerate(ordered):
            node.timeline_index = index
            events.append(
                TimelineEvent(
                    timestamp=float(index),
                    label=node.label,
                    node_id=node.node_id,
                    node_type=node.node_type,
                    status=node.status,
                    duration_seconds=node.duration_seconds,
                    detail=self._timeline_detail(node),
                )
            )
        return events

    # ── decision traces ─────────────────────────────────────────────────────

    def _fetch_decisions(self, store: Any) -> list[Any]:
        if hasattr(store, "get_decisions"):
            try:
                return list(store.get_decisions() or [])
            except TypeError:
                try:
                    return list(store.get_decisions(limit=10) or [])
                except Exception:
                    return []
            except Exception:
                return []
        if hasattr(store, "get_recent_decisions"):
            try:
                return list(store.get_recent_decisions() or [])
            except TypeError:
                try:
                    return list(store.get_recent_decisions(limit=10) or [])
                except Exception:
                    return []
            except Exception:
                return []
        return []

    def _build_decisions(self) -> list[DecisionTrace]:
        store = self._feedback_store
        if store is None:
            return []
        traces: list[DecisionTrace] = []
        for raw in self._fetch_decisions(store):
            try:
                traces.append(self._convert_decision(raw))
            except Exception:
                logger.warning("decision trace conversion failed", exc_info=True)
        return traces

    def _convert_decision(self, raw: Any) -> DecisionTrace:
        decision_id = str(_get(raw, "decision_id") or "")
        capability = str(_get(raw, "capability") or "")
        selected = str(_get(raw, "selected_provider") or "")
        raw_candidates = _get(raw, "candidate_scores") or []
        candidates = [self._convert_candidate(c) for c in raw_candidates]
        explicit_reasons = _get(raw, "reasons")
        if isinstance(explicit_reasons, (list, tuple)) and explicit_reasons:
            reasons = [str(r) for r in explicit_reasons]
        else:
            reasons = self._derive_reasons(selected, raw_candidates)
        return DecisionTrace(
            decision_id=decision_id,
            capability=capability,
            selected_provider=selected,
            candidates=candidates,
            reasons=reasons,
            outcome=self._resolve_outcome(decision_id),
        )

    def _convert_candidate(self, raw: Any) -> CandidateScore:
        return CandidateScore(
            provider_id=str(_get(raw, "provider_id") or ""),
            total_score=_as_float(_get(raw, "total_score")),
            priority_score=_as_float(_get(raw, "priority_score")),
            historical_score=_as_float(_get(raw, "historical_score")),
            benchmark_score=_as_float(_get(raw, "benchmark_score")),
            health_score=_as_float(_get(raw, "health_score")),
            latency_score=_as_float(_get(raw, "latency_score")),
            cost_score=_as_float(_get(raw, "cost_score")),
            budget_score=_as_float(_get(raw, "budget_score")),
            offline_score=_as_float(_get(raw, "offline_score")),
            calibration_adjustment=_as_float(_get(raw, "calibration_adjustment")),
        )

    @staticmethod
    def _score_items(raw: Any) -> list[tuple[str, float]]:
        if isinstance(raw, dict):
            items = raw.items()
        elif hasattr(raw, "to_dict"):
            items = raw.to_dict().items()
        else:
            items = []
        scores: list[tuple[str, float]] = []
        for key, value in items:
            if key == "provider_id" or isinstance(value, bool):
                continue
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            scores.append((str(key), numeric))
        return scores

    def _derive_reasons(self, selected: str, raw_candidates: Any) -> list[str]:
        chosen = None
        for candidate in raw_candidates or []:
            if str(_get(candidate, "provider_id") or "") == selected:
                chosen = candidate
                break
        if chosen is None:
            return []
        reasons = [
            (key[:-6] if key.endswith("_score") else key, value)
            for key, value in self._score_items(chosen)
            if value != 0.0
        ]
        reasons.sort(key=lambda item: item[1], reverse=True)
        return [f"{name}={value:+.2f}" for name, value in reasons]

    def _resolve_outcome(self, decision_id: str) -> Optional[DecisionOutcome]:
        store = self._feedback_store
        if store is None or not decision_id:
            return None
        try:
            outcomes = store.get_outcomes_for_decision(decision_id)
        except Exception:
            return None
        if not outcomes:
            return None
        raw = outcomes[-1]
        return DecisionOutcome(
            success=bool(_get(raw, "success", False)),
            duration_ms=_as_float(_get(raw, "duration_ms")),
            quality_score=_as_float(_get(raw, "quality_score")),
            cost=_as_float(_get(raw, "cost")),
            retries=_as_int(_get(raw, "retries")),
            error=_get(raw, "error"),
        )

    # ── knowledge ───────────────────────────────────────────────────────────

    def _load_knowledge(self, activity_id: str) -> tuple[Optional[dict], list]:
        store = self._knowledge_store
        if store is None:
            return None, []
        experience: Optional[dict] = None
        try:
            experience = store.get_experience(activity_id)
        except Exception:
            logger.warning("experience load failed", exc_info=True)
        knowledge: list = []
        try:
            knowledge = list(store.search_knowledge() or [])
        except TypeError:
            try:
                knowledge = list(store.search_knowledge(limit=10) or [])
            except Exception:
                knowledge = []
        except Exception:
            logger.warning("knowledge load failed", exc_info=True)
        return experience, knowledge


__all__ = [
    "CandidateScore",
    "DecisionOutcome",
    "DecisionTrace",
    "ReplayAssembler",
    "ReplayDAG",
    "ReplayEdge",
    "ReplayNode",
    "TimelineEvent",
]
