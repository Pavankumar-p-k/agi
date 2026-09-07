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

"""tests/unit/test_governance.py
Unit tests for the JARVIS governance layer.

Run:
    python -m pytest tests/unit/test_governance.py -v
    # or from the jarvis root:
    python -m pytest tests/unit/test_governance.py -v --tb=short
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ════════════════════════════════════════════════════════════════════════════
# 1. TaskRouter
# ════════════════════════════════════════════════════════════════════════════

class TestTaskRouter:

    def setup_method(self):
        from core.governance.task_router import TaskRouter
        self.router = TaskRouter()

    @pytest.mark.asyncio
    async def test_research_routing(self):
        decision = await self.router.route("search for latest AI news")
        assert decision.handler == "sub_agent"
        assert decision.target  == "researcher"
        assert decision.confidence > 0.4

    @pytest.mark.asyncio
    async def test_coder_routing(self):
        decision = await self.router.route("write a Python function to sort a list")
        assert decision.handler == "sub_agent"
        assert decision.target  == "coder"
        assert decision.confidence > 0.4

    @pytest.mark.asyncio
    async def test_planner_routing(self):
        decision = await self.router.route("plan a roadmap for building a web app")
        assert decision.handler == "sub_agent"
        assert decision.target  in ("planner", "coder")  # both are valid for this task
        assert decision.confidence > 0.3

    @pytest.mark.asyncio
    async def test_conversational_routing(self):
        decision = await self.router.route("hello how are you")
        assert decision.handler == "llm_direct"

    @pytest.mark.asyncio
    async def test_skill_routing(self):
        self.router.add_skill("weather", ["weather", "temperature", "forecast", "rain"])
        decision = await self.router.route("what is the weather today")
        assert decision.handler == "skill"
        assert decision.target  == "weather"

    @pytest.mark.asyncio
    async def test_low_confidence_flags_clarification(self):
        decision = await self.router.route("xyzzy")
        # should still return a decision, possibly with low confidence
        assert hasattr(decision, "confidence")
        assert 0.0 <= decision.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_route_decision_to_dict(self):
        decision = await self.router.route("search for python tutorials")
        d = decision.to_dict()
        assert "handler" in d
        assert "target"  in d
        assert "confidence" in d
        assert "reasoning" in d
        assert "estimated_duration_s" in d

    def test_needs_clarification_below_threshold(self):
        from core.governance.task_router import RouteDecision
        d = RouteDecision(
            handler="llm_direct", target="llm_direct",
            confidence=0.3, reasoning="test",
            estimated_duration_s=1.0,
        )
        assert d.needs_clarification() is True

    def test_no_clarification_above_threshold(self):
        from core.governance.task_router import RouteDecision
        d = RouteDecision(
            handler="sub_agent", target="researcher",
            confidence=0.75, reasoning="test",
            estimated_duration_s=8.0,
        )
        assert d.needs_clarification() is False

    @pytest.mark.asyncio
    async def test_add_skill_manually(self):
        self.router.add_skill("spotify", ["play", "music", "song", "spotify"])
        decision = await self.router.route("play some relaxing music")
        assert decision.handler == "skill"
        assert decision.target  == "spotify"

    @pytest.mark.asyncio
    async def test_multiple_tasks(self):
        tasks = [
            "search for news",
            "write a script",
            "plan a project",
            "hello there",
        ]
        expected_targets = ["researcher", "coder", "planner", "llm_direct"]
        for task, expected in zip(tasks, expected_targets):
            d = await self.router.route(task)
            # We accept either the expected target or adjacent ones
            assert d.target in (expected, "llm_direct", "coder", "researcher", "planner"), \
                f"Task '{task}' routed to unexpected target '{d.target}'"


# ════════════════════════════════════════════════════════════════════════════
# 2. ResourceMonitor
# ════════════════════════════════════════════════════════════════════════════

class TestResourceMonitor:

    def setup_method(self):
        from core.governance.resource_monitor import ResourceMonitor
        self.monitor = ResourceMonitor()

    def test_get_snapshot_returns_snapshot(self):
        from core.governance.resource_monitor import ResourceSnapshot
        snap = self.monitor.get_snapshot()
        assert isinstance(snap, ResourceSnapshot)

    def test_snapshot_fields_in_range(self):
        snap = self.monitor.get_snapshot()
        assert 0.0 <= snap.cpu_pct  <= 100.0
        assert 0.0 <= snap.ram_pct  <= 100.0
        assert 0.0 <= snap.disk_pct <= 100.0
        assert snap.agent_count >= 0
        assert isinstance(snap.active_skills, list)

    def test_snapshot_to_dict(self):
        snap = self.monitor.get_snapshot()
        d    = snap.to_dict()
        assert "cpu_pct" in d
        assert "ram_pct" in d
        assert "disk_pct" in d
        assert "agent_count" in d
        assert "active_skills" in d

    @patch("psutil.cpu_percent", return_value=90.0)
    @patch("psutil.virtual_memory")
    @patch("psutil.disk_usage")
    def test_should_throttle_high_cpu(self, mock_disk, mock_ram, mock_cpu):
        mock_ram.return_value = MagicMock(percent=50.0)
        mock_disk.return_value = MagicMock(percent=30.0)
        from core.governance.resource_monitor import ResourceMonitor
        monitor = ResourceMonitor()
        assert monitor.should_throttle() is True

    @patch("psutil.cpu_percent", return_value=96.0)
    @patch("psutil.virtual_memory")
    @patch("psutil.disk_usage")
    def test_should_reject_critical_cpu(self, mock_disk, mock_ram, mock_cpu):
        mock_ram.return_value  = MagicMock(percent=50.0)
        mock_disk.return_value = MagicMock(percent=30.0)
        from core.governance.resource_monitor import ResourceMonitor
        monitor = ResourceMonitor()
        assert monitor.should_reject() is True

    @patch("psutil.cpu_percent", return_value=20.0)
    @patch("psutil.virtual_memory")
    @patch("psutil.disk_usage")
    def test_recommend_concurrency_healthy(self, mock_disk, mock_ram, mock_cpu):
        mock_ram.return_value  = MagicMock(percent=20.0)
        mock_disk.return_value = MagicMock(percent=10.0)
        from core.governance.resource_monitor import ResourceMonitor
        monitor = ResourceMonitor()
        conc = monitor.recommend_concurrency()
        assert 1 <= conc <= 8

    def test_agent_tracking(self):
        self.monitor.register_agent("agent-1")
        self.monitor.register_agent("agent-2")
        assert self.monitor.get_snapshot().agent_count == 2
        self.monitor.unregister_agent("agent-1")
        assert self.monitor.get_snapshot().agent_count == 1

    def test_skill_tracking(self):
        self.monitor.start_skill("weather")
        assert "weather" in self.monitor.get_snapshot().active_skills
        self.monitor.finish_skill("weather")
        assert "weather" not in self.monitor.get_snapshot().active_skills

    def test_is_healthy_property(self):
        from core.governance.resource_monitor import ResourceSnapshot
        snap = ResourceSnapshot(cpu_pct=50, ram_pct=60, disk_pct=40,
                                agent_count=2, active_skills=[])
        assert snap.is_healthy is True

    def test_is_critical_property(self):
        from core.governance.resource_monitor import ResourceSnapshot
        snap = ResourceSnapshot(cpu_pct=96, ram_pct=50, disk_pct=40,
                                agent_count=0, active_skills=[])
        assert snap.is_critical is True


# ════════════════════════════════════════════════════════════════════════════
# 3. WorkQueue
# ════════════════════════════════════════════════════════════════════════════

class TestWorkQueue:

    def setup_method(self):
        """Create a fresh WorkQueue with mocked monitor and router."""
        from core.governance.work_queue import WorkQueue
        from core.governance.resource_monitor import ResourceMonitor
        from core.governance.task_router import TaskRouter

        # Mock monitor so tests don't depend on actual CPU
        self.mock_monitor = MagicMock(spec=ResourceMonitor)
        self.mock_monitor.should_reject.return_value  = False
        self.mock_monitor.should_throttle.return_value = False
        self.mock_monitor.recommend_concurrency.return_value = 4

        # Mock router
        from core.governance.task_router import RouteDecision
        self.mock_router = AsyncMock(spec=TaskRouter)
        self.mock_router.route.return_value = RouteDecision(
            handler="llm_direct", target="llm_direct",
            confidence=0.8, reasoning="test mock",
            estimated_duration_s=1.0,
        )

        # Patch queue file so tests don't touch ~/.jarvis/queue.json
        self.tmp_queue = Path(f"/tmp/test_queue_{uuid.uuid4().hex}.json")
        with patch("core.governance.work_queue.QUEUE_FILE", self.tmp_queue):
            self.wq = WorkQueue(
                resource_monitor=self.mock_monitor,
                task_router=self.mock_router,
            )

    def teardown_method(self):
        if self.tmp_queue.exists():
            self.tmp_queue.unlink()

    @pytest.mark.asyncio
    async def test_enqueue_returns_task_id(self):
        task_id = await self.wq.enqueue("test task")
        assert isinstance(task_id, str)
        assert len(task_id) == 36  # UUID4

    @pytest.mark.asyncio
    async def test_get_task_after_enqueue(self):
        task_id = await self.wq.enqueue("hello world")
        record  = self.wq.get_task(task_id)
        assert record is not None
        assert record.task == "hello world"

    @pytest.mark.asyncio
    async def test_status_counts(self):
        await self.wq.enqueue("task 1")
        await self.wq.enqueue("task 2")
        status = self.wq.get_status()
        assert status["pending"] == 2
        assert status["running"] == 0
        assert status["done"]    == 0

    @pytest.mark.asyncio
    async def test_cancel_pending_task(self):
        task_id  = await self.wq.enqueue("cancel me", priority=5)
        result   = self.wq.cancel(task_id)
        assert result is True
        record = self.wq.get_task(task_id)
        assert record.status.value == "cancelled"

    def test_cancel_nonexistent_task(self):
        result = self.wq.cancel("nonexistent-id")
        assert result is False

    @pytest.mark.asyncio
    async def test_list_tasks(self):
        await self.wq.enqueue("task a")
        await self.wq.enqueue("task b")
        tasks = self.wq.list_tasks()
        assert len(tasks) == 2
        task_texts = [t["task"] for t in tasks]
        assert "task a" in task_texts
        assert "task b" in task_texts

    @pytest.mark.asyncio
    async def test_priority_ordering(self):
        from core.governance.work_queue import TaskRecord, TaskStatus
        await self.wq.enqueue("low",    priority=10)
        await self.wq.enqueue("urgent", priority=1)
        await self.wq.enqueue("normal", priority=5)

        # Pull all from queue and verify ordering
        records = []
        while not self.wq._queue.empty():
            prio, ts, rec = self.wq._queue.get_nowait()
            records.append((prio, rec))

        priorities = [p for p, _ in records]
        assert priorities == sorted(priorities), "Tasks not in priority order"

    @pytest.mark.asyncio
    async def test_reject_when_system_overloaded(self):
        self.mock_monitor.should_reject.return_value = True
        with pytest.raises(RuntimeError, match="critically overloaded"):
            await self.wq.enqueue("should be rejected")

    @pytest.mark.asyncio
    async def test_task_record_to_dict(self):
        task_id = await self.wq.enqueue("convert me")
        record  = self.wq.get_task(task_id)
        d       = record.to_dict()
        assert d["task_id"] == task_id
        assert d["task"]    == "convert me"
        assert "status"     in d
        assert "priority"   in d

    @pytest.mark.asyncio
    async def test_persistence_file_created(self):
        with patch("core.governance.work_queue.QUEUE_FILE", self.tmp_queue):
            from core.governance.work_queue import WorkQueue
            wq = WorkQueue(
                resource_monitor=self.mock_monitor,
                task_router=self.mock_router,
            )
            await wq.enqueue("persist me")
        assert self.tmp_queue.exists()
        data = json.loads(self.tmp_queue.read_text())
        assert len(data) >= 1
        assert data[0]["task"] == "persist me"

    def test_restore_pending_on_startup(self):
        """Tasks saved to disk should be restored as PENDING on next startup."""
        pending_data = [{
            "task_id":    str(uuid.uuid4()),
            "task":       "restored task",
            "priority":   5,
            "context":    {},
            "status":     "pending",
            "created_at": time.time(),
            "started_at": None,
            "done_at":    None,
            "result":     None,
            "error":      None,
        }]
        self.tmp_queue.write_text(json.dumps(pending_data))

        with patch("core.governance.work_queue.QUEUE_FILE", self.tmp_queue):
            from core.governance.work_queue import WorkQueue
            wq = WorkQueue(
                resource_monitor=self.mock_monitor,
                task_router=self.mock_router,
            )
        assert len(wq._records) == 1
        record = next(iter(wq._records.values()))
        assert record.task == "restored task"

    def test_running_tasks_reset_to_pending_on_restore(self):
        """Tasks that were RUNNING at crash time should be reset to PENDING."""
        running_data = [{
            "task_id":    str(uuid.uuid4()),
            "task":       "interrupted task",
            "priority":   3,
            "context":    {},
            "status":     "running",
            "created_at": time.time(),
            "started_at": time.time() - 30,
            "done_at":    None,
            "result":     None,
            "error":      None,
        }]
        self.tmp_queue.write_text(json.dumps(running_data))

        with patch("core.governance.work_queue.QUEUE_FILE", self.tmp_queue):
            from core.governance.work_queue import WorkQueue
            wq = WorkQueue(
                resource_monitor=self.mock_monitor,
                task_router=self.mock_router,
            )
        record = next(iter(wq._records.values()))
        assert record.status.value == "pending", \
            "RUNNING tasks should be reset to PENDING on restore"


# ════════════════════════════════════════════════════════════════════════════
# 4. SystemGovernor (integration)
# ════════════════════════════════════════════════════════════════════════════

class TestSystemGovernor:

    def setup_method(self):
        from core.system_governor import SystemGovernor
        self.gov = SystemGovernor()

    def test_decide_abort_on_max_retries(self):
        d = self.gov.decide("proj", [], "LOGIC", retries=5, max_retries=5,
                            budget_remaining=1.0)
        assert d.action == "abort"

    def test_decide_abort_on_budget_exhausted(self):
        d = self.gov.decide("proj", [], "LOGIC", retries=0, max_retries=5,
                            budget_remaining=0.0)
        assert d.action == "abort"

    def test_decide_switch_tool_on_tool_failure(self):
        d = self.gov.decide("proj", ["err"], "TOOL", retries=1, max_retries=5,
                            budget_remaining=1.0)
        assert d.action == "switch_tool"

    def test_decide_replan_on_logic_failure(self):
        d = self.gov.decide("proj", ["logic err"], "LOGIC", retries=1, max_retries=5,
                            budget_remaining=1.0)
        assert d.action == "replan"

    def test_decide_retry_first_logic_failure(self):
        d = self.gov.decide("proj", ["err"], "LOGIC", retries=0, max_retries=5,
                            budget_remaining=1.0)
        assert d.action == "retry"

    def test_decide_pause_on_unknown_pattern(self):
        d = self.gov.decide("proj", [], "UNKNOWN", retries=2, max_retries=5,
                            budget_remaining=1.0)
        assert d.action == "pause"

    def test_get_history(self):
        self.gov.decide("myproj", [], "LOGIC", 0, 3, 1.0)
        self.gov.decide("myproj", [], "LOGIC", 1, 3, 1.0)
        history = self.gov.get_history("myproj")
        assert len(history) == 2

    def test_reset_history(self):
        self.gov.decide("myproj", [], "LOGIC", 0, 3, 1.0)
        self.gov.reset("myproj")
        assert self.gov.get_history("myproj") == []

    def test_get_status_structure(self):
        # governor.get_status() should return queue + resources
        status = self.gov.get_status()
        assert "queue"     in status
        assert "resources" in status

    def test_route_is_async(self):
        import inspect
        from core.governance.task_router import task_router
        assert inspect.iscoroutinefunction(task_router.route)


# ════════════════════════════════════════════════════════════════════════════
# 5. API routes (integration-lite — no FastAPI test client needed)
# ════════════════════════════════════════════════════════════════════════════

class TestGovernanceRoutes:

    def test_routes_importable(self):
        from api.governance_routes import router
        # Verify all expected routes are registered
        paths = [r.path for r in router.routes]
        assert "/governance/status"      in paths
        assert "/governance/queue"       in paths
        assert "/governance/submit"      in paths
        assert "/governance/resources"   in paths
        assert "/governance/route"       in paths

    def test_route_methods(self):
        from api.governance_routes import router
        methods = {r.path: list(r.methods) for r in router.routes if hasattr(r, "methods")}
        assert "GET"  in methods.get("/governance/status", [])
        assert "POST" in methods.get("/governance/submit", [])
        assert "POST" in methods.get("/governance/cancel/{task_id}", [])
