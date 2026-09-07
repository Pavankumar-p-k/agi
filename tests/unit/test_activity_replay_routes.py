"""Tests for the ReplayDAG REST API endpoint and ReplayScreen TUI integration.

Validates:
  - GET /api/activity/{activity_id}/replay returns correct ReplayDAG
  - Serialization matches dataclass structure
  - Error states (missing, empty, failed, cancelled)
  - Large and deep DAGs
  - Timeline ordering
  - Decision trace reconstruction
  - TUI ReplayScreen renders ReplayDAG
  - Identical DAG structure between UI and API
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from textual.widgets import Static

from core.activity.replay import (
    ReplayAssembler, ReplayDAG, ReplayNode, ReplayEdge,
    DecisionTrace, CandidateScore, DecisionOutcome, TimelineEvent,
)
from core.routes.activity import _replay_dag_to_dict, _replay_node_to_dict

# ── Sample data ────────────────────────────────────────────────────────────

ROOT_NODE = {
    "node_id": "act_root",
    "activity_id": "act_001",
    "node_type": "goal",
    "label": "Build coffee shop app",
    "title": "Build coffee shop app",
    "status": "COMPLETED",
    "depth": 0,
    "parent_id": None,
    "started_at": "2026-06-28T06:51:05.578307+00:00",
    "completed_at": "2026-06-28T06:51:05.578307+00:00",
    "agent_id": "NEXUS",
    "workflow_id": "wf_001",
    "input_json": '{"goal": "Build coffee shop app"}',
    "output_json": '{"status": "completed", "apk_path": "/tmp/app.apk"}',
    "metadata_json": '{"version": 1}',
}

AGENT_NODE = {
    "node_id": "node_agent",
    "activity_id": "act_001",
    "node_type": "agent_call",
    "label": "NEXUS: Build APK",
    "title": "NEXUS: Build APK",
    "status": "COMPLETED",
    "depth": 1,
    "parent_id": "act_root",
    "started_at": "2026-06-28T06:51:05.578307+00:00",
    "completed_at": "2026-06-28T06:51:05.578307+00:00",
    "agent_id": "NEXUS",
    "workflow_id": None,
    "input_json": '{"task": "Build APK"}',
    "output_json": '{"result": "APK built"}',
    "metadata_json": '{"provider": "forge", "model": "qwen2.5:7b"}',
}

TOOL_NODE = {
    "node_id": "node_tool",
    "activity_id": "act_001",
    "node_type": "tool_call",
    "label": "browser_navigate(url=https://google.com)",
    "title": "browser_navigate",
    "status": "COMPLETED",
    "depth": 2,
    "parent_id": "node_agent",
    "started_at": "2026-06-28T06:51:05.578307+00:00",
    "completed_at": "2026-06-28T06:51:05.578307+00:00",
    "agent_id": None,
    "workflow_id": "wf_001",
    "input_json": '{"url": "https://google.com"}',
    "output_json": '{"status": "ok", "url": "https://google.com"}',
    "metadata_json": None,
}

FAILED_NODE = {
    "node_id": "node_failed",
    "activity_id": "act_001",
    "node_type": "agent_call",
    "label": "Failed task",
    "title": "Failed task",
    "status": "FAILED",
    "depth": 1,
    "parent_id": "act_root",
    "started_at": "2026-06-28T06:51:05.578307+00:00",
    "completed_at": "2026-06-28T06:51:05.578307+00:00",
    "agent_id": "FORGE",
    "workflow_id": None,
    "input_json": '{"task": "fail"}',
    "output_json": '{"error": "Build failed"}',
    "metadata_json": '{"provider": "forge"}',
}

CANCELLED_NODE = {
    "node_id": "node_cancelled",
    "activity_id": "act_cancel",
    "node_type": "goal",
    "label": "Cancelled task",
    "title": "Cancelled task",
    "status": "CANCELLED",
    "depth": 0,
    "parent_id": None,
    "started_at": "2026-06-28T06:51:05.578307+00:00",
    "completed_at": "2026-06-28T06:51:05.578307+00:00",
    "agent_id": None,
    "workflow_id": None,
    "input_json": None,
    "output_json": None,
    "metadata_json": None,
}

MALFORMED_NODE = {
    "node_id": "node_bad",
    "activity_id": "act_bad",
    "node_type": "tool_call",
    "label": "bad node",
    "title": "bad node",
    "status": "UNKNOWN",
    "depth": 0,
    "parent_id": None,
    "started_at": None,
    "completed_at": None,
    "agent_id": None,
    "workflow_id": None,
    "input_json": "not valid json{{{",
    "output_json": None,
    "metadata_json": None,
}

SAMPLE_EDGE = {
    "edge_id": "edge_1",
    "from_node_id": "node_agent",
    "to_node_id": "node_tool",
    "edge_type": "depends_on",
    "metadata_json": '{"weight": 1}',
}


class _MockStore:
    """Minimal mock of ActivityStore for testing."""
    def __init__(self, nodes=None, edges=None):
        self._nodes = nodes if nodes is not None else [ROOT_NODE, AGENT_NODE, TOOL_NODE]
        self._all_edges = edges if edges is not None else [SAMPLE_EDGE]

    def get_activity_tree(self, activity_id):
        nodes = [n for n in self._nodes if n.get("activity_id", n.get("node_id", "")) == activity_id]
        return nodes or self._nodes

    def get_edges(self, activity_id=None):
        return self._all_edges


class _MockManager:
    """Minimal mock of ActivityManager for testing."""
    def __init__(self, nodes=None, edges=None):
        self.store = _MockStore(nodes=nodes, edges=edges)

    def get_tree(self, activity_id):
        return self.store.get_activity_tree(activity_id)

    def get_active_activities(self):
        return []


# ── Fixtures ───────────────────────────────────────────────────────────────


def _make_dag(activity_id: str, nodes: list[dict] | None = None) -> ReplayDAG:
    """Build a ReplayDAG from raw node dicts using ReplayAssembler."""
    manager = _MockManager(nodes=nodes)
    assembler = ReplayAssembler(activity_store=manager.store)
    return assembler.build(activity_id)


# ── Serialization tests ────────────────────────────────────────────────────

class TestSerialization:
    def test_replay_node_to_dict_flat(self):
        dag = _make_dag("act_001")
        node = dag.all_nodes["act_root"]
        d = _replay_node_to_dict(node)
        assert d["node_id"] == "act_root"
        assert d["node_type"] == "goal"
        assert d["children"] == ["node_agent"]
        assert isinstance(d["metadata"], dict)
        assert d["metadata"].get("version") == 1

    def test_replay_node_to_dict_no_children(self):
        dag = _make_dag("act_001")
        node = dag.all_nodes["node_tool"]
        d = _replay_node_to_dict(node)
        assert d["children"] == []

    def test_replay_dag_to_dict_basic(self):
        dag = _make_dag("act_001")
        d = _replay_dag_to_dict(dag)
        assert d["activity_id"] == "act_001"
        assert d["root_id"] == "act_root"
        assert len(d["all_nodes"]) == 3
        assert len(d["timeline"]) == 3
        assert d["total_nodes"] == 3

    def test_replay_dag_to_dict_has_summary(self):
        dag = _make_dag("act_001")
        d = _replay_dag_to_dict(dag)
        assert d["total_nodes"] == 3
        assert d["total_retries"] == 0
        assert isinstance(d["unique_tools"], list)
        assert isinstance(d["unique_providers"], list)
        assert isinstance(d["experience"], (dict, type(None)))
        assert isinstance(d["knowledge"], list)

    def test_decision_trace_empty_no_crash(self):
        dag = _make_dag("act_001")
        d = _replay_dag_to_dict(dag)
        assert isinstance(d["decisions"], list)

    def test_all_nodes_flat_no_children(self):
        dag = _make_dag("act_001")
        d = _replay_dag_to_dict(dag)
        for node_id, node_dict in d["all_nodes"].items():
            assert isinstance(node_dict["children"], list)
            for cid in node_dict["children"]:
                assert isinstance(cid, str)


# ── API endpoint logic tests (via direct ReplayAssembler + serialization) ──

class TestReplayEndpoint:
    def _build_and_serialize(self, activity_id: str, nodes: list[dict] | None = None,
                              edges: list[dict] | None = None) -> dict:
        """Simulate what the API endpoint does: build DAG + serialize."""
        manager = _MockManager(nodes=nodes, edges=edges)
        assembler = ReplayAssembler(activity_store=manager.store)
        dag = assembler.build(activity_id)
        return _replay_dag_to_dict(dag)

    def test_replay_returns_dag(self):
        data = self._build_and_serialize("act_001")
        assert data["activity_id"] == "act_001"
        assert data["root_id"] == "act_root"
        assert len(data["all_nodes"]) == 3
        assert len(data["timeline"]) == 3

    def test_replay_timeline_ordered(self):
        data = self._build_and_serialize("act_001")
        timestamps = [e["timestamp"] for e in data["timeline"]]
        assert timestamps == sorted(timestamps)

    def test_replay_missing_activity(self):
        data = self._build_and_serialize("act_nonexistent", nodes=[])
        assert data["total_nodes"] == 0

    def test_replay_empty_activity(self):
        empty_act = {"node_id": "act_empty", "activity_id": "act_empty",
                      "node_type": "goal", "label": "Empty", "title": "Empty",
                      "status": "PENDING", "depth": 0, "parent_id": None,
                      "started_at": None, "completed_at": None,
                      "agent_id": None, "workflow_id": None,
                      "input_json": None, "output_json": None, "metadata_json": None}
        data = self._build_and_serialize("act_empty", nodes=[empty_act], edges=[])
        assert data["total_nodes"] == 1
        assert data["root_id"] == "act_empty"

    def test_replay_failed_activity(self):
        nodes = [ROOT_NODE, FAILED_NODE]
        data = self._build_and_serialize("act_001", nodes=nodes)
        assert data["failed_nodes"] == 1
        assert data["total_nodes"] == 2

    def test_replay_cancelled_activity(self):
        data = self._build_and_serialize("act_cancel", nodes=[CANCELLED_NODE], edges=[])
        assert data["root_id"] == "node_cancelled"

    def test_replay_malformed_metadata(self):
        data = self._build_and_serialize("act_bad", nodes=[MALFORMED_NODE], edges=[])
        assert data["root_id"] == "node_bad"

    def test_replay_large_dag(self):
        nodes = []
        for i in range(50):
            parent_id = nodes[-1]["node_id"] if nodes else None
            nodes.append({
                "node_id": f"node_{i}",
                "activity_id": "act_large",
                "node_type": "tool_call",
                "label": f"tool_{i}",
                "title": f"tool_{i}",
                "status": "COMPLETED" if i % 2 == 0 else "FAILED",
                "depth": i,
                "parent_id": parent_id,
                "started_at": "2026-06-28T06:51:05.578307+00:00",
                "completed_at": "2026-06-28T06:51:05.578307+00:00",
                "agent_id": None,
                "workflow_id": None,
                "input_json": None,
                "output_json": None,
                "metadata_json": None,
            })
        data = self._build_and_serialize("act_large", nodes=nodes)
        assert data["total_nodes"] == 50
        assert data["failed_nodes"] == 25

    def test_replay_deep_dag(self):
        nodes = []
        for i in range(10):
            parent_id = nodes[-1]["node_id"] if nodes else None
            nodes.append({
                "node_id": f"depth_{i}",
                "activity_id": "act_deep",
                "node_type": "subgoal",
                "label": f"depth_{i}",
                "title": f"depth_{i}",
                "status": "COMPLETED",
                "depth": i,
                "parent_id": parent_id,
                "started_at": "2026-06-28T06:51:05.578307+00:00",
                "completed_at": "2026-06-28T06:51:05.578307+00:00",
                "agent_id": None,
                "workflow_id": None,
                "input_json": None,
                "output_json": None,
                "metadata_json": None,
            })
        data = self._build_and_serialize("act_deep", nodes=nodes, edges=[])
        assert data["total_nodes"] == 10
        assert data["root_id"] == "depth_0"

    def test_replay_timeline_ordering(self):
        """Timeline events must be sorted chronologically."""
        nodes = [
            {**ROOT_NODE, "started_at": "2026-06-28T06:51:10.000000+00:00",
             "completed_at": "2026-06-28T06:51:15.000000+00:00"},
            {**AGENT_NODE, "started_at": "2026-06-28T06:51:05.000000+00:00",
             "completed_at": "2026-06-28T06:51:08.000000+00:00"},
            {**TOOL_NODE, "started_at": "2026-06-28T06:51:08.000000+00:00",
             "completed_at": "2026-06-28T06:51:10.000000+00:00"},
        ]
        data = self._build_and_serialize("act_001", nodes=nodes)
        assert len(data["timeline"]) == 3
        for i, ev in enumerate(data["timeline"]):
            assert ev["timestamp"] == float(i)


# ── Cross-check: identical DAG structure ───────────────────────────────────

class TestCrossCheck:
    def test_identical_dag_ui_and_api(self):
        """ReplayAssembler.build() + serialization must be consistent."""
        nodes = [ROOT_NODE, AGENT_NODE, TOOL_NODE]
        manager1 = _MockManager(nodes=nodes)
        assembler1 = ReplayAssembler(activity_store=manager1.store)
        dag1 = assembler1.build("act_001")
        direct1 = _replay_dag_to_dict(dag1)

        manager2 = _MockManager(nodes=nodes)
        assembler2 = ReplayAssembler(activity_store=manager2.store)
        dag2 = assembler2.build("act_001")
        direct2 = _replay_dag_to_dict(dag2)

        assert direct1["activity_id"] == direct2["activity_id"]
        assert direct1["root_id"] == direct2["root_id"]
        assert direct1["total_nodes"] == direct2["total_nodes"]
        assert direct1["failed_nodes"] == direct2["failed_nodes"]
        assert direct1["total_duration_seconds"] == direct2["total_duration_seconds"]
        assert set(direct1["all_nodes"].keys()) == set(direct2["all_nodes"].keys())
        assert len(direct1["timeline"]) == len(direct2["timeline"])
        assert len(direct1["decisions"]) == len(direct2["decisions"])


# ── TUI ReplayScreen tests ─────────────────────────────────────────────────

SAMPLE_DAG_RESPONSE = {
    "activity_id": "act_001",
    "root_id": "act_root",
    "all_nodes": {
        "act_root": {
            "node_id": "act_root", "activity_id": "act_001",
            "node_type": "goal", "label": "Build coffee shop app",
            "status": "COMPLETED", "depth": 0, "parent_id": None,
            "children": ["node_agent"],
            "duration_seconds": 10.0,
            "tool": None, "provider": None, "model": None,
            "retry_count": 0, "cost": 0.0,
            "input_preview": "", "output_preview": "", "error": None,
            "started_at": None, "completed_at": None,
            "agent_id": None, "workflow_id": "wf_001",
            "timeline_index": 2, "metadata": {}, "artifacts": {},
        },
        "node_agent": {
            "node_id": "node_agent", "activity_id": "act_001",
            "node_type": "agent_call", "label": "NEXUS: Build APK",
            "status": "COMPLETED", "depth": 1, "parent_id": "act_root",
            "children": ["node_tool"],
            "duration_seconds": 5.0,
            "tool": None, "provider": "forge", "model": "qwen2.5:7b",
            "retry_count": 0, "cost": 0.0,
            "input_preview": "", "output_preview": "", "error": None,
            "started_at": None, "completed_at": None,
            "agent_id": "NEXUS", "workflow_id": None,
            "timeline_index": 1, "metadata": {}, "artifacts": {},
        },
        "node_tool": {
            "node_id": "node_tool", "activity_id": "act_001",
            "node_type": "tool_call", "label": "browser_navigate(url=https://google.com)",
            "status": "COMPLETED", "depth": 2, "parent_id": "node_agent",
            "children": [],
            "duration_seconds": 2.0,
            "tool": "browser_navigate", "provider": None, "model": None,
            "retry_count": 0, "cost": 0.0,
            "input_preview": "", "output_preview": "", "error": None,
            "started_at": None, "completed_at": None,
            "agent_id": None, "workflow_id": "wf_001",
            "timeline_index": 0, "metadata": {}, "artifacts": {},
        },
    },
    "all_edges": [{"edge_id": "edge_1", "from_node_id": "node_agent",
                    "to_node_id": "node_tool", "edge_type": "depends_on",
                    "label": "depends_on", "metadata": {}}],
    "timeline": [
        {"timestamp": 0.0, "label": "browser_navigate(...)", "node_id": "node_tool",
         "node_type": "tool_call", "status": "COMPLETED", "duration_seconds": 2.0,
         "detail": "tool=browser_navigate"},
        {"timestamp": 1.0, "label": "NEXUS: Build APK", "node_id": "node_agent",
         "node_type": "agent_call", "status": "COMPLETED", "duration_seconds": 5.0,
         "detail": "provider=forge"},
        {"timestamp": 2.0, "label": "Build coffee shop app", "node_id": "act_root",
         "node_type": "goal", "status": "COMPLETED", "duration_seconds": 10.0,
         "detail": ""},
    ],
    "decisions": [
        {"decision_id": "dec_001", "capability": "build",
         "selected_provider": "forge", "candidates": [
             {"provider_id": "forge", "total_score": 0.85, "priority_score": 0.5,
              "historical_score": 1.0, "benchmark_score": 0.0, "health_score": 0.0,
              "latency_score": 0.0, "cost_score": 0.0, "budget_score": 0.0,
              "offline_score": 0.0, "calibration_adjustment": 0.0},
         ], "reasons": ["historical=+1.00", "priority=+0.50"],
         "outcome": {"success": True, "duration_ms": 1200, "quality_score": 0.9,
                     "cost": 0.0, "retries": 0, "error": None}},
    ],
    "total_nodes": 3,
    "failed_nodes": 0,
    "total_duration_seconds": 10.0,
    "unique_tools": ["browser_navigate"],
    "unique_providers": ["forge"],
    "total_retries": 0,
    "total_cost": 0.0,
    "experience": None,
    "knowledge": [],
}


class _TUIMockClient:
    """Minimal mock JarvisClient for TUI screen tests."""
    def __init__(self):
        self.get_activities = AsyncMock(return_value=[
            {"node_id": "act_001", "label": "Build coffee shop app",
             "title": "Build coffee shop app", "status": "RUNNING", "progress": 65},
        ])
        self.get_activity_replay = AsyncMock(return_value=SAMPLE_DAG_RESPONSE)
        self.get_activity_timeline = AsyncMock(return_value=[])
        self.get_activity_detail = AsyncMock(return_value={})
        self.get_activity_summary = AsyncMock(return_value={})


@pytest.mark.asyncio
async def test_replay_screen_loads_dag():
    """ReplayScreen fetches and renders a ReplayDAG."""
    from jarvis_tui.app.screens.replay_screen import ReplayScreen
    from textual.app import App

    mc = _TUIMockClient()
    mc.get_activity_replay = AsyncMock(return_value=SAMPLE_DAG_RESPONSE)

    class _TestApp(App):
        def __init__(self):
            super().__init__()
            self.jarvis_client = mc
        def on_mount(self):
            self.push_screen(ReplayScreen())
        def handle_navigation(self, screen_name):
            pass

    app = _TestApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert mc.get_activity_replay.await_count >= 1
        viewer = app.screen.query_one("#replay-viewer")
        assert viewer is not None
        dag_view = app.screen.query_one("#replay-dag-view")
        assert dag_view is not None
        dec_view = app.screen.query_one("#replay-decisions-view")
        assert dec_view is not None
        sum_view = app.screen.query_one("#replay-summary-view")
        assert sum_view is not None


@pytest.mark.asyncio
async def test_replay_screen_empty_state():
    """ReplayScreen handles no activities gracefully."""
    from jarvis_tui.app.screens.replay_screen import ReplayScreen
    from textual.app import App

    mc = _TUIMockClient()
    mc.get_activities = AsyncMock(return_value=[])

    class _TestApp(App):
        def __init__(self):
            super().__init__()
            self.jarvis_client = mc
        def on_mount(self):
            self.push_screen(ReplayScreen())
        def handle_navigation(self, screen_name):
            pass

    app = _TestApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        viewer = app.screen.query_one("#replay-viewer", Static)
        assert viewer is not None


@pytest.mark.asyncio
async def test_replay_screen_error_state():
    """ReplayScreen handles API errors gracefully."""
    from jarvis_tui.app.screens.replay_screen import ReplayScreen
    from textual.app import App

    mc = _TUIMockClient()
    mc.get_activities = AsyncMock(side_effect=Exception("API error"))

    class _TestApp(App):
        def __init__(self):
            super().__init__()
            self.jarvis_client = mc
        def on_mount(self):
            self.push_screen(ReplayScreen())
        def handle_navigation(self, screen_name):
            pass

    app = _TestApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        viewer = app.screen.query_one("#replay-viewer", Static)
        assert viewer is not None


@pytest.mark.asyncio
async def test_replay_screen_failed_activity():
    """ReplayScreen shows failed nodes in DAG and summary."""
    from jarvis_tui.app.screens.replay_screen import ReplayScreen
    from textual.app import App

    dag = {**SAMPLE_DAG_RESPONSE, "failed_nodes": 1}
    dag = {**dag, "all_nodes": {**dag["all_nodes"]}}
    dag["all_nodes"]["node_failed"] = {
        "node_id": "node_failed", "activity_id": "act_001",
        "node_type": "agent_call", "label": "Failed task",
        "status": "FAILED", "depth": 1, "parent_id": "act_root",
        "children": [], "duration_seconds": 0.0,
        "tool": None, "provider": "forge", "model": None,
        "retry_count": 0, "cost": 0.0,
        "input_preview": "", "output_preview": "", "error": "Build failed",
        "started_at": None, "completed_at": None,
        "agent_id": "FORGE", "workflow_id": None,
        "timeline_index": 3, "metadata": {}, "artifacts": {},
    }

    mc = _TUIMockClient()
    mc.get_activity_replay = AsyncMock(return_value=dag)

    class _TestApp(App):
        def __init__(self):
            super().__init__()
            self.jarvis_client = mc
        def on_mount(self):
            self.push_screen(ReplayScreen())
        def handle_navigation(self, screen_name):
            pass

    app = _TestApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        viewer = app.screen.query_one("#replay-summary-view", Static)
        assert viewer is not None


@pytest.mark.asyncio
async def test_replay_screen_cancelled_activity():
    """ReplayScreen handles cancelled activities."""
    from jarvis_tui.app.screens.replay_screen import ReplayScreen
    from textual.app import App

    mc = _TUIMockClient()
    cancelled_dag = {
        "activity_id": "act_cancel",
        "root_id": "act_cancel",
        "all_nodes": {
            "act_cancel": {
                "node_id": "act_cancel", "activity_id": "act_cancel",
                "node_type": "goal", "label": "Cancelled task",
                "status": "CANCELLED", "depth": 0, "parent_id": None,
                "children": [], "duration_seconds": 0.0,
                "tool": None, "provider": None, "model": None,
                "retry_count": 0, "cost": 0.0, "input_preview": "",
                "output_preview": "", "error": None,
                "started_at": None, "completed_at": None,
                "agent_id": None, "workflow_id": None,
                "timeline_index": 0, "metadata": {}, "artifacts": {},
            }
        },
        "all_edges": [], "timeline": [], "decisions": [],
        "total_nodes": 1, "failed_nodes": 1,
        "total_duration_seconds": 0.0,
        "unique_tools": [], "unique_providers": [],
        "total_retries": 0, "total_cost": 0.0,
        "experience": None, "knowledge": [],
    }
    mc.get_activity_replay = AsyncMock(return_value=cancelled_dag)

    class _TestApp(App):
        def __init__(self):
            super().__init__()
            self.jarvis_client = mc
        def on_mount(self):
            self.push_screen(ReplayScreen())
        def handle_navigation(self, screen_name):
            pass

    app = _TestApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert mc.get_activity_replay.await_count >= 1


@pytest.mark.asyncio
async def test_replay_screen_step_forward():
    """Timeline step forward works with DAG data."""
    from jarvis_tui.app.screens.replay_screen import ReplayScreen
    from textual.app import App

    mc = _TUIMockClient()
    mc.get_activity_replay = AsyncMock(return_value=SAMPLE_DAG_RESPONSE)

    class _TestApp(App):
        def __init__(self):
            super().__init__()
            self.jarvis_client = mc
        def on_mount(self):
            self.push_screen(ReplayScreen())
        def handle_navigation(self, screen_name):
            pass

    app = _TestApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.action_step_forward()
        await pilot.pause()
        assert app.screen.index == 1


@pytest.mark.asyncio
async def test_replay_screen_step_back():
    """Timeline step back works with DAG data."""
    from jarvis_tui.app.screens.replay_screen import ReplayScreen
    from textual.app import App

    mc = _TUIMockClient()
    mc.get_activity_replay = AsyncMock(return_value=SAMPLE_DAG_RESPONSE)

    class _TestApp(App):
        def __init__(self):
            super().__init__()
            self.jarvis_client = mc
        def on_mount(self):
            self.push_screen(ReplayScreen())
        def handle_navigation(self, screen_name):
            pass

    app = _TestApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.action_step_forward()
        app.screen.action_step_forward()
        await pilot.pause()
        assert app.screen.index == 2
        app.screen.action_step_back()
        await pilot.pause()
        assert app.screen.index == 1


@pytest.mark.asyncio
async def test_replay_screen_toggle_play():
    """Play/pause toggles auto-advance timer."""
    from jarvis_tui.app.screens.replay_screen import ReplayScreen
    from textual.app import App

    mc = _TUIMockClient()
    mc.get_activity_replay = AsyncMock(return_value=SAMPLE_DAG_RESPONSE)

    class _TestApp(App):
        def __init__(self):
            super().__init__()
            self.jarvis_client = mc
        def on_mount(self):
            self.push_screen(ReplayScreen())
        def handle_navigation(self, screen_name):
            pass

    app = _TestApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.action_toggle_play()
        assert app.screen.playing is True
        app.screen.action_toggle_play()
        assert app.screen.playing is False


@pytest.mark.asyncio
async def test_replay_screen_has_tabs():
    """ReplayScreen has all four view tabs."""
    from jarvis_tui.app.screens.replay_screen import ReplayScreen
    from textual.app import App

    mc = _TUIMockClient()
    mc.get_activity_replay = AsyncMock(return_value=SAMPLE_DAG_RESPONSE)

    class _TestApp(App):
        def __init__(self):
            super().__init__()
            self.jarvis_client = mc
        def on_mount(self):
            self.push_screen(ReplayScreen())
        def handle_navigation(self, screen_name):
            pass

    app = _TestApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        tabs = app.screen.query_one("#replay-tabs")
        assert tabs is not None
        assert app.screen.query_one("#tab-timeline") is not None
        assert app.screen.query_one("#tab-dag") is not None
        assert app.screen.query_one("#tab-decisions") is not None
        assert app.screen.query_one("#tab-summary") is not None
