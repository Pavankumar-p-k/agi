"""Tests for the Activity Replay DAG (core/activity/replay.py).

Covers:
  3A — DAG structure, tree assembly, node conversion
  3B — Execution metadata enrichment (tool, provider, workflow)
  3C — Decision trace (candidates, scores, reasons, outcome)
  3D — Timeline (flattening, sorting, index cross-reference)
  Summary — aggregation, experience/knowledge attachment
  Edge cases — empty trees, missing stores, malformed data
"""

import json
import tempfile
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

import pytest

from core.activity.replay import (
    ReplayAssembler,
    ReplayDAG,
    ReplayNode,
    ReplayEdge,
    DecisionTrace,
    CandidateScore,
    DecisionOutcome,
    TimelineEvent,
)


# ── Sample data ──────────────────────────────────────────────────────────────

TS_NOW = datetime.now(timezone.utc).isoformat()
TS_START = datetime.now(timezone.utc).isoformat()

ROOT_NODE = {
    "node_id": "act_root",
    "activity_id": "act_123",
    "node_type": "goal",
    "label": "Build coffee shop app",
    "status": "COMPLETED",
    "depth": 0,
    "parent_id": None,
    "agent_id": None,
    "workflow_id": "wf_001",
    "started_at": TS_START,
    "completed_at": TS_NOW,
    "input_json": '{"goal": "Build coffee shop app"}',
    "output_json": '{"status": "completed", "apk_path": "/tmp/app.apk"}',
    "artifacts_json": '{"apk": "art_001"}',
    "metadata_json": '{"version": 1}',
}

AGENT_NODE = {
    "node_id": "node_agent",
    "activity_id": "act_123",
    "node_type": "agent_call",
    "label": "NEXUS: Build APK",
    "status": "COMPLETED",
    "depth": 1,
    "parent_id": "act_root",
    "agent_id": "NEXUS",
    "workflow_id": None,
    "started_at": TS_START,
    "completed_at": TS_NOW,
    "input_json": '{"task": "Build APK"}',
    "output_json": '{"result": "APK built"}',
    "metadata_json": '{"provider": "forge", "model": "qwen2.5:7b"}',
}

TOOL_NODE = {
    "node_id": "node_tool",
    "activity_id": "act_123",
    "node_type": "tool_call",
    "label": "browser_navigate(url=https://google.com)",
    "status": "COMPLETED",
    "depth": 2,
    "parent_id": "node_agent",
    "agent_id": None,
    "workflow_id": "wf_001",
    "started_at": TS_START,
    "completed_at": TS_NOW,
    "input_json": '{"url": "https://google.com"}',
    "output_json": '{"status": "ok", "url": "https://google.com"}',
    "metadata_json": '{}',
}

FAILED_NODE = {
    "node_id": "node_fail",
    "activity_id": "act_123",
    "node_type": "tool_call",
    "label": "build_project",
    "status": "FAILED",
    "depth": 2,
    "parent_id": "node_agent",
    "agent_id": None,
    "workflow_id": None,
    "started_at": TS_START,
    "completed_at": TS_NOW,
    "input_json": '{"project": "app"}',
    "output_json": '{"error": "Build failed: syntax error in MainActivity.kt:42"}',
    "metadata_json": '{}',
}

SAMPLE_EDGE = {
    "edge_id": "edge_1",
    "from_node_id": "node_agent",
    "to_node_id": "node_tool",
    "edge_type": "depends_on",
    "metadata_json": '{"weight": 1}',
}


# ── Mock stores ──────────────────────────────────────────────────────────────

class MockActivityStore:
    """Returns test data as list of dicts (what ActivityStore.get_activity_tree returns after conversion)."""
    def __init__(self, nodes=None, edges=None):
        self._nodes = nodes if nodes is not None else [ROOT_NODE, AGENT_NODE, TOOL_NODE]
        self._edges = edges if edges is not None else [SAMPLE_EDGE]

    def get_activity_tree(self, activity_id):
        return list(self._nodes)

    def get_edges(self, activity_id=None):
        return list(self._edges)


class MockFeedbackStore:
    def __init__(self):
        self._decisions = []
        self._outcomes = {}

    def add_decision(self, decision: dict):
        self._decisions.append(decision)

    def add_outcome(self, decision_id: str, outcome: dict):
        self._outcomes.setdefault(decision_id, []).append(outcome)

    def get_decisions(self, limit=10):
        return list(self._decisions[-limit:])

    def get_outcomes_for_decision(self, decision_id: str):
        return list(self._outcomes.get(decision_id, []))


class MockKnowledgeStore:
    def __init__(self):
        self._experience = None
        self._knowledge = []

    def set_experience(self, exp: dict):
        self._experience = exp

    def set_knowledge(self, items: list):
        self._knowledge = items

    def get_experience(self, activity_id: str):
        return self._experience

    def search_knowledge(self, min_confidence=0.0, min_evidence=0, limit=10):
        return list(self._knowledge[:limit])


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def store():
    return MockActivityStore()


@pytest.fixture
def feedback_store():
    return MockFeedbackStore()


@pytest.fixture
def knowledge_store():
    return MockKnowledgeStore()


@pytest.fixture
def assembler(store):
    return ReplayAssembler(activity_store=store)


@pytest.fixture
def full_assembler(store, feedback_store, knowledge_store):
    return ReplayAssembler(
        activity_store=store,
        feedback_store=feedback_store,
        knowledge_store=knowledge_store,
    )


# ══════════════════════════════════════════════════════════════════
# Phase 3A — DAG Visualization
# ══════════════════════════════════════════════════════════════════

class TestPhase3A_DAGStructure:

    def test_build_returns_dag(self, assembler):
        dag = assembler.build("act_123")
        assert isinstance(dag, ReplayDAG)
        assert dag.activity_id == "act_123"

    def test_all_nodes_loaded(self, assembler):
        dag = assembler.build("act_123")
        assert len(dag.all_nodes) == 3
        assert "act_root" in dag.all_nodes
        assert "node_agent" in dag.all_nodes
        assert "node_tool" in dag.all_nodes

    def test_root_identified_by_depth(self, assembler):
        dag = assembler.build("act_123")
        assert dag.root is not None
        assert dag.root.node_id == "act_root"
        assert dag.root.depth == 0

    def test_tree_children_assembled(self, assembler):
        dag = assembler.build("act_123")
        assert dag.root is not None
        assert len(dag.root.children) == 1
        assert dag.root.children[0].node_id == "node_agent"
        assert len(dag.root.children[0].children) == 1
        assert dag.root.children[0].children[0].node_id == "node_tool"

    def test_all_edges_loaded(self, assembler):
        dag = assembler.build("act_123")
        assert len(dag.all_edges) == 1
        assert dag.all_edges[0].edge_id == "edge_1"

    def test_node_conversion(self, assembler):
        dag = assembler.build("act_123")
        node = dag.all_nodes["node_tool"]
        assert node.node_type == "tool_call"
        assert node.status == "COMPLETED"
        assert node.depth == 2
        assert node.parent_id == "node_agent"
        assert node.duration_seconds is not None
        assert node.input_preview != ""
        assert node.output_preview != ""

    def test_node_error_extracted(self, assembler):
        store = MockActivityStore(nodes=[ROOT_NODE, AGENT_NODE, FAILED_NODE])
        a = ReplayAssembler(activity_store=store)
        dag = a.build("act_123")
        node = dag.all_nodes["node_fail"]
        assert node.error is not None
        assert "Build failed" in node.error

    def test_artifact_refs_loaded(self, assembler):
        dag = assembler.build("act_123")
        node = dag.all_nodes["act_root"]
        assert "apk" in node.artifacts
        assert node.artifacts["apk"] == "art_001"

    def test_empty_tree(self):
        store = MockActivityStore(nodes=[])
        a = ReplayAssembler(activity_store=store)
        dag = a.build("act_empty")
        assert len(dag.all_nodes) == 0
        assert dag.root is None

    def test_single_node(self):
        store = MockActivityStore(nodes=[ROOT_NODE], edges=[])
        a = ReplayAssembler(activity_store=store)
        dag = a.build("act_123")
        assert len(dag.all_nodes) == 1
        assert dag.root is not None
        assert dag.root.node_id == "act_root"

    def test_no_store(self):
        a = ReplayAssembler()
        dag = a.build("act_123")
        assert len(dag.all_nodes) == 0
        assert dag.root is None


# ══════════════════════════════════════════════════════════════════
# Phase 3B — Execution Metadata
# ══════════════════════════════════════════════════════════════════

class TestPhase3B_ExecutionMetadata:

    def test_tool_call_has_tool_name(self, assembler):
        dag = assembler.build("act_123")
        tool_node = dag.all_nodes["node_tool"]
        assert tool_node.tool == "browser_navigate"

    def test_agent_call_has_provider(self, assembler):
        dag = assembler.build("act_123")
        agent_node = dag.all_nodes["node_agent"]
        assert agent_node.provider == "forge"
        assert agent_node.model == "qwen2.5:7b"

    def test_failed_node_has_error(self, assembler):
        store = MockActivityStore(nodes=[ROOT_NODE, AGENT_NODE, FAILED_NODE])
        a = ReplayAssembler(activity_store=store)
        dag = a.build("act_123")
        node = dag.all_nodes["node_fail"]
        assert node.error is not None
        assert "syntax error" in node.error

    def test_missing_workflow_store_does_not_crash(self, assembler):
        dag = assembler.build("act_123")
        # Enrich should not crash even without workflow store
        assert dag.root is not None


# ══════════════════════════════════════════════════════════════════
# Phase 3C — Decision Trace
# ══════════════════════════════════════════════════════════════════

class TestPhase3C_DecisionTrace:

    def test_decision_attached(self, assembler, feedback_store):
        feedback_store.add_decision({
            "decision_id": "dec_1",
            "capability": "code_generation",
            "selected_provider": "forge",
            "candidate_scores": [
                {"provider_id": "forge", "total_score": 0.94, "priority_score": 0.8,
                 "historical_score": 0.9, "calibration_adjustment": 0.05},
                {"provider_id": "codex", "total_score": 0.73, "priority_score": 0.5,
                 "historical_score": 0.7, "calibration_adjustment": 0.0},
            ],
        })
        a = ReplayAssembler(
            activity_store=assembler._activity_store,
            feedback_store=feedback_store,
        )
        dag = a.build("act_123")
        assert len(dag.decisions) > 0
        trace = dag.decisions[0]
        assert trace.capability == "code_generation"
        assert trace.selected_provider == "forge"

    def test_decision_candidates(self, assembler, feedback_store):
        feedback_store.add_decision({
            "decision_id": "dec_1",
            "capability": "code_generation",
            "selected_provider": "forge",
            "candidate_scores": [
                {"provider_id": "forge", "total_score": 0.94, "priority_score": 0.8,
                 "historical_score": 0.9, "health_score": 0.85,
                 "latency_score": 0.7, "benchmark_score": 0.88,
                 "cost_score": 0.6, "offline_score": 0.0,
                 "calibration_adjustment": 0.05},
                {"provider_id": "codex", "total_score": 0.73, "priority_score": 0.5,
                 "historical_score": 0.7},
            ],
        })
        a = ReplayAssembler(
            activity_store=assembler._activity_store,
            feedback_store=feedback_store,
        )
        dag = a.build("act_123")
        trace = dag.decisions[0]
        assert len(trace.candidates) == 2
        assert trace.candidates[0].provider_id == "forge"
        assert trace.candidates[0].total_score == 0.94
        assert trace.candidates[0].health_score == 0.85

    def test_decision_reasons(self, assembler, feedback_store):
        feedback_store.add_decision({
            "decision_id": "dec_2",
            "capability": "code_generation",
            "selected_provider": "codex",
            "candidate_scores": [
                {"provider_id": "forge", "total_score": 0.5, "health_score": 0.3, "historical_score": 0.6, "benchmark_score": 0.4},
                {"provider_id": "codex", "total_score": 0.9, "health_score": 0.95, "historical_score": 0.8, "benchmark_score": 0.85},
            ],
        })
        a = ReplayAssembler(
            activity_store=assembler._activity_store,
            feedback_store=feedback_store,
        )
        dag = a.build("act_123")
        trace = dag.decisions[0]
        assert len(trace.reasons) > 0
        # Top reasons should reflect the selected provider's strengths
        assert "health" in trace.reasons[0].lower() or any("health" in r.lower() for r in trace.reasons)

    def test_decision_outcome(self, assembler, feedback_store):
        feedback_store.add_decision({
            "decision_id": "dec_1",
            "capability": "code_generation",
            "selected_provider": "forge",
            "candidate_scores": [],
        })
        feedback_store.add_outcome("dec_1", {
            "success": True,
            "duration_ms": 15000,
            "quality_score": 0.85,
            "cost": 0.02,
            "retries": 1,
        })
        a = ReplayAssembler(
            activity_store=assembler._activity_store,
            feedback_store=feedback_store,
        )
        dag = a.build("act_123")
        trace = dag.decisions[0]
        assert trace.outcome is not None
        assert trace.outcome.success is True
        assert trace.outcome.duration_ms == 15000
        assert trace.outcome.retries == 1

    def test_no_decisions_when_no_feedback_store(self, assembler):
        dag = assembler.build("act_123")
        assert len(dag.decisions) == 0

    def test_no_decisions_for_non_agent_nodes(self, assembler):
        store = MockActivityStore(nodes=[ROOT_NODE, TOOL_NODE])
        a = ReplayAssembler(activity_store=store)
        dag = a.build("act_123")
        assert len(dag.decisions) == 0


# ══════════════════════════════════════════════════════════════════
# Phase 3D — Timeline
# ══════════════════════════════════════════════════════════════════

class TestPhase3D_Timeline:

    def test_timeline_has_all_events(self, assembler):
        dag = assembler.build("act_123")
        assert len(dag.timeline) == 3

    def test_timeline_sorted(self, assembler):
        dag = assembler.build("act_123")
        timestamps = [e.timestamp for e in dag.timeline]
        assert timestamps == sorted(timestamps)

    def test_timeline_events_have_node_refs(self, assembler):
        dag = assembler.build("act_123")
        for event in dag.timeline:
            assert event.node_id in dag.all_nodes
            assert event.node_type in ("goal", "agent_call", "tool_call")

    def test_timeline_index_on_nodes(self, assembler):
        dag = assembler.build("act_123")
        for node in dag.all_nodes.values():
            assert node.timeline_index is not None
            assert 0 <= node.timeline_index < len(dag.timeline)

    def test_timeline_detail_includes_tool(self, assembler):
        dag = assembler.build("act_123")
        tool_events = [e for e in dag.timeline if e.node_type == "tool_call"]
        for ev in tool_events:
            node = dag.all_nodes[ev.node_id]
            if node.tool:
                assert node.tool in ev.detail or "tool=browser_navigate" in ev.detail


# ══════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════

class TestSummary:

    def test_total_nodes_counted(self, assembler):
        dag = assembler.build("act_123")
        assert dag.total_nodes == 3

    def test_failed_nodes_counted(self, assembler):
        store = MockActivityStore(nodes=[ROOT_NODE, AGENT_NODE, FAILED_NODE])
        a = ReplayAssembler(activity_store=store)
        dag = a.build("act_123")
        assert dag.failed_nodes == 1

    def test_unique_tools(self, assembler):
        dag = assembler.build("act_123")
        assert "browser_navigate" in dag.unique_tools

    def test_unique_providers(self, assembler):
        dag = assembler.build("act_123")
        assert "forge" in dag.unique_providers

    def test_experience_attached(self, full_assembler, knowledge_store):
        knowledge_store.set_experience({"activity_id": "act_123", "goal": "Build app", "success": True})
        dag = full_assembler.build("act_123")
        assert dag.experience is not None
        assert dag.experience.get("goal") == "Build app"

    def test_knowledge_attached(self, full_assembler, knowledge_store):
        knowledge_store.set_knowledge([
            {"claim": "Forge is best for Java", "confidence": 0.9},
        ])
        dag = full_assembler.build("act_123")
        assert len(dag.knowledge) == 1
        assert dag.knowledge[0]["claim"] == "Forge is best for Java"

    def test_empty_knowledge_no_crash(self, full_assembler):
        dag = full_assembler.build("act_123")
        assert dag.knowledge == []


# ══════════════════════════════════════════════════════════════════
# Edge Cases
# ══════════════════════════════════════════════════════════════════

class TestEdgeCases:

    def test_null_node_durations_no_crash(self):
        node_no_time = {**ROOT_NODE, "started_at": None, "completed_at": None}
        store = MockActivityStore(nodes=[node_no_time], edges=[])
        a = ReplayAssembler(activity_store=store)
        dag = a.build("act_123")
        assert dag.all_nodes["act_root"].duration_seconds is None

    def test_malformed_json_input_no_crash(self):
        node = {**ROOT_NODE, "input_json": "not valid json{{{", "output_json": None}
        store = MockActivityStore(nodes=[node], edges=[])
        a = ReplayAssembler(activity_store=store)
        dag = a.build("act_123")
        assert dag.root is not None
        # Should have empty string preview, not crash
        assert isinstance(dag.root.input_preview, str)

    def test_tool_node_without_metadata_still_works(self):
        node = {**TOOL_NODE, "metadata_json": None}
        store = MockActivityStore(nodes=[ROOT_NODE, AGENT_NODE, node], edges=[])
        a = ReplayAssembler(activity_store=store)
        dag = a.build("act_123")
        tool_node = dag.all_nodes["node_tool"]
        # Tool should be extracted from label
        assert tool_node.tool is not None

    def test_orphan_nodes_loaded_no_crash(self):
        """Nodes with parent_id pointing to non-existent node should still load."""
        orphan = {**TOOL_NODE, "parent_id": "nonexistent"}
        store = MockActivityStore(nodes=[ROOT_NODE, orphan], edges=[])
        a = ReplayAssembler(activity_store=store)
        dag = a.build("act_123")
        assert len(dag.all_nodes) == 2

    def test_no_store_provided_graceful_degradation(self):
        a = ReplayAssembler()
        dag = a.build("act_123")
        assert len(dag.all_nodes) == 0
        assert dag.root is None
        assert dag.timeline == []
        assert dag.decisions == []

    def test_activity_id_preserved(self, assembler):
        dag = assembler.build("custom_id_42")
        assert dag.activity_id == "custom_id_42"
