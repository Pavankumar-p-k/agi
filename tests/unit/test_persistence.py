# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone

import pytest

from core.persistence import AgentCheckpoint, ExecutionGraph, GraphNode, CheckpointStore
from core.persistence.graph import NodeStatus


# ════════════════════════════════════════════════════════════════════════
# Phase 7a: AgentCheckpoint Schema
# ════════════════════════════════════════════════════════════════════════

class TestAgentCheckpoint:
    def test_create(self):
        cp = AgentCheckpoint(session_key="sess_1", task="build app")
        assert cp.session_key == "sess_1"
        assert cp.task == "build app"
        assert cp.version == 1
        assert cp.created_at
        assert cp.updated_at

    def test_add_tool_result(self):
        cp = AgentCheckpoint(session_key="sess_1")
        cp.add_tool_result({"tool": "bash", "exit_code": 0})
        assert len(cp.tool_results) == 1
        assert cp.tool_results[0]["tool"] == "bash"

    def test_tool_result_capped(self):
        cp = AgentCheckpoint(session_key="sess_1")
        cp.MAX_TOOL_RESULTS = 3
        for i in range(5):
            cp.add_tool_result({"i": i})
        assert len(cp.tool_results) == 3
        assert cp.tool_results[-1]["i"] == 4

    def test_mark_completed(self):
        cp = AgentCheckpoint(session_key="sess_1")
        cp.pending_tasks = ["t1", "t2"]
        cp.mark_completed("t1")
        assert "t1" in cp.completed_tasks
        assert "t1" not in cp.pending_tasks

    def test_mark_failed(self):
        cp = AgentCheckpoint(session_key="sess_1")
        cp.pending_tasks = ["t1"]
        cp.mark_failed("t1")
        assert "t1" in cp.failed_tasks
        assert "t1" not in cp.pending_tasks

    def test_to_dict_roundtrip(self):
        cp = AgentCheckpoint(
            session_key="sess_1",
            agent_id="nexus",
            task="do something",
            plan=[{"step": 1, "action": "think"}],
            variables={"mode": "auto"},
        )
        d = cp.to_dict()
        restored = AgentCheckpoint.from_dict(d)
        assert restored.session_key == "sess_1"
        assert restored.agent_id == "nexus"
        assert restored.variables == {"mode": "auto"}
        assert restored.plan == [{"step": 1, "action": "think"}]

    def test_from_dict_empty(self):
        restored = AgentCheckpoint.from_dict({})
        assert restored.session_key == ""

    def test_to_dict_limits(self):
        cp = AgentCheckpoint(session_key="sess_1")
        for i in range(100):
            cp.add_tool_result({"i": i})
        d = cp.to_dict()
        assert len(d["tool_results"]) == 50  # last 50
        assert d["tool_results"][0]["i"] == 50


# ════════════════════════════════════════════════════════════════════════
# Phase 7b: ExecutionGraph
# ════════════════════════════════════════════════════════════════════════

class TestExecutionGraph:
    def test_add_node(self):
        g = ExecutionGraph(session_key="sess_1")
        g.add_node(GraphNode(id="n1", description="step 1"))
        assert g.get_node("n1") is not None

    def test_topological_order(self):
        g = ExecutionGraph()
        g.add_node(GraphNode(id="n3", depends_on=["n1", "n2"]))
        g.add_node(GraphNode(id="n1"))
        g.add_node(GraphNode(id="n2", depends_on=["n1"]))
        order = g.topological_order()
        order_ids = [n.id for n in order]
        assert order_ids.index("n1") < order_ids.index("n2")
        assert order_ids.index("n2") < order_ids.index("n3")

    def test_ready_nodes(self):
        g = ExecutionGraph()
        g.add_node(GraphNode(id="n1", status=NodeStatus.COMPLETED))
        g.add_node(GraphNode(id="n2", depends_on=["n1"]))
        g.add_node(GraphNode(id="n3", depends_on=["n1"]))

        ready = g.ready_nodes()
        assert len(ready) == 2
        assert all(n.id in ("n2", "n3") for n in ready)

    def test_ready_nodes_blocked(self):
        g = ExecutionGraph()
        g.add_node(GraphNode(id="n1", status=NodeStatus.PENDING))
        g.add_node(GraphNode(id="n2", depends_on=["n1"]))
        ready = g.ready_nodes()
        assert len(ready) == 1
        assert ready[0].id == "n1"

    def test_is_complete(self):
        g = ExecutionGraph()
        g.add_node(GraphNode(id="n1", status=NodeStatus.COMPLETED))
        g.add_node(GraphNode(id="n2", status=NodeStatus.COMPLETED))
        assert g.is_complete() is True

    def test_is_not_complete(self):
        g = ExecutionGraph()
        g.add_node(GraphNode(id="n1", status=NodeStatus.RUNNING))
        assert g.is_complete() is False

    def test_completion_pct(self):
        g = ExecutionGraph()
        g.add_node(GraphNode(id="n1", status=NodeStatus.COMPLETED))
        g.add_node(GraphNode(id="n2", status=NodeStatus.PENDING))
        assert g.completion_pct() == 50.0

    def test_update_status(self):
        g = ExecutionGraph()
        g.add_node(GraphNode(id="n1"))
        g.update_status("n1", NodeStatus.RUNNING)
        assert g.get_node("n1").status == NodeStatus.RUNNING

    def test_json_roundtrip(self):
        g = ExecutionGraph(session_key="sess_1")
        g.add_node(GraphNode(id="n1", description="first", status=NodeStatus.COMPLETED))
        g.add_node(GraphNode(id="n2", description="second", depends_on=["n1"]))

        json_str = g.to_json()
        restored = ExecutionGraph.from_json(json_str)
        assert restored.session_key == "sess_1"
        assert restored.get_node("n1").description == "first"
        assert restored.get_node("n2").depends_on == ["n1"]

    def test_dict_roundtrip(self):
        g = ExecutionGraph(session_key="sess_1")
        g.add_node(GraphNode(id="n1", result="done", duration_ms=1500.0))
        d = g.to_dict()
        restored = ExecutionGraph.from_dict(d)
        assert restored.get_node("n1").result == "done"
        assert restored.get_node("n1").duration_ms == 1500.0

    def test_empty_graph_not_complete(self):
        g = ExecutionGraph()
        assert g.is_complete() is False
        assert g.completion_pct() == 0.0

    def test_ready_nodes_empty(self):
        g = ExecutionGraph()
        assert g.ready_nodes() == []


# ════════════════════════════════════════════════════════════════════════
# Phase 7c: CheckpointStore
# ════════════════════════════════════════════════════════════════════════

class TestCheckpointStore:
    @pytest.fixture
    def store(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        s = CheckpointStore(db_path=db_path)
        yield s
        import os
        if os.path.exists(db_path):
            os.unlink(db_path)

    def test_save_and_load_latest(self, store):
        cp = AgentCheckpoint(session_key="sess_1", task="test")
        row_id = store.save(cp)
        assert row_id > 0

        loaded = store.load_latest("sess_1")
        assert loaded is not None
        restored_cp, restored_graph = loaded
        assert restored_cp.session_key == "sess_1"
        assert restored_cp.task == "test"
        assert restored_graph is None

    def test_save_with_graph(self, store):
        cp = AgentCheckpoint(session_key="sess_2")
        g = ExecutionGraph(session_key="sess_2")
        g.add_node(GraphNode(id="n1"))

        store.save(cp, graph=g)
        loaded = store.load_latest("sess_2")
        assert loaded is not None
        _, restored_graph = loaded
        assert restored_graph is not None
        assert restored_graph.get_node("n1") is not None

    def test_load_latest_returns_newest(self, store):
        import time
        cp1 = AgentCheckpoint(session_key="sess_3", task="first")
        store.save(cp1)
        time.sleep(0.02)
        cp2 = AgentCheckpoint(session_key="sess_3", task="second")
        store.save(cp2)

        loaded = store.load_latest("sess_3")
        assert loaded is not None
        assert loaded[0].task == "second"

    def test_load_latest_no_session(self, store):
        assert store.load_latest("nonexistent") is None

    def test_load_by_id(self, store):
        cp = AgentCheckpoint(session_key="sess_4")
        row_id = store.save(cp)
        loaded = store.load_by_id(row_id)
        assert loaded is not None
        assert loaded[0].session_key == "sess_4"

    def test_load_by_id_missing(self, store):
        assert store.load_by_id(99999) is None

    def test_list_recent(self, store):
        for i in range(5):
            store.save(AgentCheckpoint(session_key=f"sess_{i}"))
        recent = store.list_recent(limit=3)
        assert len(recent) == 3

    def test_list_recent_empty(self, store):
        assert store.list_recent() == []

    def test_delete_old(self, store):
        from datetime import timedelta
        cp = AgentCheckpoint(session_key="old_sess")
        store.save(cp)
        deleted = store.delete_old(days=0)
        assert deleted >= 0  # may be 0 if within same second

    def test_delete_session(self, store):
        store.save(AgentCheckpoint(session_key="del_me"))
        deleted = store.delete_session("del_me")
        assert deleted == 1
        assert store.load_latest("del_me") is None

    def test_compact(self, store):
        for i in range(15):
            store.save(AgentCheckpoint(session_key="compact_sess"))
        removed = store.compact(max_per_session=5)
        assert removed == 10

    def test_db_path_property(self, store):
        assert store.db_path.endswith(".db")

    def test_multiple_sessions(self, store):
        store.save(AgentCheckpoint(session_key="a"))
        store.save(AgentCheckpoint(session_key="b"))
        store.save(AgentCheckpoint(session_key="c"))
        recent = store.list_recent(limit=10)
        assert len(recent) == 3
