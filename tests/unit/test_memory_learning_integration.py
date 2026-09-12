"""Unit tests for Memory + Learning integration.

Covers:
- memory/experience.py  (record/recall/best_procedure over EpisodicStore)
- memory/memory_facade  (record_experience / recall_experience / best_procedure)
- core/event_bus.py     (publish_sync, error isolation, async compatibility)
- learning/habit_tracker.py (real habit tracking)
- learning/listeners.py (LearningHub wiring)
- core/browser/browser_ai emit funnel (verified outcomes reach the EventBus)

No planner/, agents/, or pipeline/ modules are touched or imported.
"""
from __future__ import annotations

import asyncio

import pytest

from core.event_bus import EventBus
from memory.episodic_store import EpisodicStore
from memory.experience import ExperienceRecorder


# ---------------------------------------------------------------------------
# Experience layer
# ---------------------------------------------------------------------------

@pytest.fixture()
def store(tmp_path):
    return EpisodicStore(db_path=str(tmp_path / "mem.db"))


@pytest.fixture()
def recorder(store):
    return ExperienceRecorder(store)


class TestExperienceRecorder:
    def test_record_returns_episode_id(self, recorder):
        ep_id = recorder.record_outcome(
            "check github notifications",
            [{"action": "browser.navigate", "url": "https://github.com/notifications"}],
            verified=True,
            specialist="Browser AI",
        )
        assert ep_id

    def test_recall_finds_similar_goal_with_expiry_fields(self, recorder):
        recorder.record_outcome(
            "check github notifications",
            [{"action": "browser.navigate", "url": "https://github.com/notifications"}],
            verified=True,
            specialist="Browser AI",
        )
        hits = recorder.recall_outcomes("check github notifications")
        assert len(hits) == 1
        hit = hits[0]
        assert hit["verified"] is True
        assert hit["success"] is True
        assert hit["fresh"] is True
        assert hit["days_since_verified"] is not None
        assert hit["similarity"] >= 0.35
        assert hit["context"].get("specialist") == "Browser AI"

    def test_recall_filters_dissimilar_goals(self, recorder):
        recorder.record_outcome("check github notifications", [], verified=True)
        assert recorder.recall_outcomes("utterly unrelated quantum banana harvest") == []

    def test_best_procedure_aggregates_verified_success(self, recorder):
        recorder.record_outcome(
            "create a github repository",
            [{"action": "browser.click", "target": "New"}],
            verified=True,
            specialist="Browser AI",
        )
        recorder.record_outcome(
            "create a github repository",
            [{"action": "browser.click", "target": "New"}],
            verified=True,
        )
        recorder.record_outcome(
            "create a github repository",
            [],
            verified=False,
            error="selector not found",
        )
        proc = recorder.best_procedure("create a github repository")
        assert proc is not None
        assert proc["matches"] == 3
        assert proc["verified_matches"] == 2
        assert proc["success_rate"] == pytest.approx(2 / 3, abs=0.01)
        assert proc["workflow"], "workflow must come from the verified success"
        assert proc["workflow"][0]["action"] == "browser.click"
        assert proc["fresh"] is True
        assert proc["known_failures"], "failure episodes must be reported"

    def test_best_procedure_none_when_nothing_similar(self, recorder):
        recorder.record_outcome("deploy to production", [], verified=True)
        assert recorder.best_procedure("bake a cake") is None

    def test_unverified_outcome_marked_honestly(self, recorder):
        recorder.record_outcome("open chrome", [], verified=False, error="timeout")
        hits = recorder.recall_outcomes("open chrome")
        assert hits[0]["verified"] is False
        assert hits[0]["success"] is False
        assert hits[0]["error"] == "timeout"


class TestFacadeExperience:
    def test_facade_record_and_recall(self, store, monkeypatch):
        from memory.memory_facade import MemoryFacade
        facade = MemoryFacade()
        monkeypatch.setattr(facade, "_experience", ExperienceRecorder(store))
        ep_id = facade.record_experience(
            "check github notifications",
            [{"action": "browser.navigate"}],
            verified=True,
            specialist="Browser AI",
        )
        assert ep_id
        assert len(facade.recall_experience("check github notifications")) == 1
        proc = facade.best_procedure("check github notifications")
        assert proc is not None and proc["verified_matches"] == 1

    def test_facade_degrades_gracefully_when_unavailable(self):
        from memory.memory_facade import MemoryFacade
        facade = MemoryFacade()
        facade._experience = False
        assert facade.record_experience("g", [], verified=True) == ""
        assert facade.recall_experience("g") == []
        assert facade.best_procedure("g") is None


# ---------------------------------------------------------------------------
# EventBus
# ---------------------------------------------------------------------------

class TestEventBus:
    def test_async_publish_awaits_async_handler(self):
        bus = EventBus()
        seen = []
        bus.subscribe("e", lambda data: seen.append(asyncio.ensure_future.__self__ if False else data))
        asyncio.run(bus.publish("e", {"x": 1}))
        assert seen == [{"x": 1}]

    def test_async_publish_awaits_coroutine_handler(self):
        bus = EventBus()
        seen = []

        async def handler(data):
            seen.append(data)

        bus.subscribe("e", handler)
        asyncio.run(bus.publish("e", {"x": 2}))
        assert seen == [{"x": 2}]

    def test_publish_sync_runs_sync_handler_inline(self):
        bus = EventBus()
        seen = []
        bus.subscribe("e", lambda data: seen.append(data))
        bus.publish_sync("e", {"x": 3})
        assert seen == [{"x": 3}]

    def test_publish_sync_runs_async_handler_without_loop(self):
        bus = EventBus()
        seen = []

        async def handler(data):
            seen.append(data)

        bus.subscribe("e", handler)
        bus.publish_sync("e", {"x": 4})
        assert seen == [{"x": 4}]

    def test_broken_handler_does_not_raise_and_is_counted(self):
        bus = EventBus()
        seen = []

        def broken(_):
            raise RuntimeError("consumer exploded")

        bus.subscribe("e", broken)
        bus.subscribe("e", lambda data: seen.append(data))
        bus.publish_sync("e", {"x": 5})
        assert seen == [{"x": 5}], "other listeners must still run"
        assert bus.failed_deliveries() == 1


# ---------------------------------------------------------------------------
# Habit tracker
# ---------------------------------------------------------------------------

class TestHabitTracker:
    def test_repeated_goal_becomes_established_habit(self):
        from learning.habit_tracker import HabitTracker
        tracker = HabitTracker()
        for _ in range(3):
            tracker.record_outcome("check github notifications", success=True, verified=True)
        strength = tracker.habit_strength("check github notifications")
        assert strength is not None
        assert strength["count"] == 3
        assert strength["success_rate"] == 1.0
        assert strength["established"] is True

    def test_success_rate_reflects_failures(self):
        from learning.habit_tracker import HabitTracker
        tracker = HabitTracker()
        tracker.record_outcome("deploy", success=True, verified=True)
        tracker.record_outcome("deploy", success=False)
        strength = tracker.habit_strength("deploy")
        assert strength["success_rate"] == 0.5
        assert strength["established"] is False

    def test_action_events_use_kind_prefix(self):
        from learning.habit_tracker import HabitTracker
        tracker = HabitTracker()
        tracker.record_event("browser.navigate", success=True)
        strength = tracker.habit_strength("action:browser.navigate")
        assert strength is not None and strength["count"] == 1

    def test_top_habits_orders_by_strength(self):
        from learning.habit_tracker import HabitTracker
        tracker = HabitTracker()
        for _ in range(5):
            tracker.record_outcome("big habit", success=True)
        tracker.record_outcome("small habit", success=True)
        tops = tracker.top_habits()
        assert tops[0]["key"] == "big habit"

    def test_legacy_api_preserved(self):
        from learning.habit_tracker import HabitTracker
        tracker = HabitTracker(memory=None)
        state = type("S", (), {"current_goal": "check mail"})()
        asyncio.run(tracker.update(state))
        stats = tracker.get_stats()
        assert stats["updates"] == 1
        assert stats["goals_observed"] == 1
        assert stats["tracked_habits"] == 1


# ---------------------------------------------------------------------------
# Learning hub wiring
# ---------------------------------------------------------------------------

class TestLearningHub:
    def _hub(self, bus, memory_stub):
        from learning.habit_tracker import HabitTracker
        from learning.listeners import LearningHub
        from learning.pattern_engine import PatternEngine
        from learning.listeners import _PatternPersistenceAdapter
        return LearningHub(
            bus=bus,
            memory=memory_stub,
            pattern_engine=PatternEngine(_PatternPersistenceAdapter(tmp := __import__("pathlib").Path(__import__("tempfile").gettempdir()) / "tpt.json")),
            habit_tracker=HabitTracker(),
        )

    def test_goal_completed_records_experience_and_habit(self):
        bus = EventBus()

        class MemoryStub:
            def __init__(self):
                self.recorded = []

            def record_experience(self, goal, actions, **kw):
                self.recorded.append((goal, actions, kw))
                return "ep1"

        stub = MemoryStub()
        hub = self._hub(bus, stub).attach()
        bus.publish_sync("goal.completed", {
            "goal": "check github notifications",
            "success": True,
            "verified": True,
            "actions": [{"action": "browser.navigate"}],
            "specialist": "Browser AI",
        })
        assert stub.recorded, "experience must be recorded via facade"
        assert stub.recorded[0][2]["verified"] is True
        strength = hub.habit_tracker.habit_strength("check github notifications")
        assert strength is not None and strength["count"] == 1

    def test_goal_completed_survives_memory_failure(self):
        bus = EventBus()

        class ExplodingMemory:
            def record_experience(self, *a, **kw):
                raise RuntimeError("db gone")

        hub = self._hub(bus, ExplodingMemory()).attach()
        bus.publish_sync("goal.completed", {"goal": "g", "success": True})
        assert hub.habit_tracker.habit_strength("g") is not None

    def test_user_message_feeds_pattern_engine(self):
        bus = EventBus()
        hub = self._hub(bus, None).attach()
        for _ in range(2):
            asyncio.run(bus.publish("user.message", {"intent": "code", "emotion": "neutral"}))
        summary = hub.pattern_engine.get_all_patterns()
        assert summary["total_patterns"] >= 1

    def test_unknown_event_ignored(self):
        bus = EventBus()
        hub = self._hub(bus, None).attach()
        bus.publish_sync("unrelated.event", {"anything": True})
        assert hub.habit_tracker.get_stats()["goals_observed"] == 0


# ---------------------------------------------------------------------------
# Browser AI emit funnel
# ---------------------------------------------------------------------------

class _FakeCaller:
    def __init__(self, script):
        self.script = script

    async def __call__(self, tool, params):
        return dict(self.script.get(tool, {"status": "error", "error": "not scripted"}))


class _FakeMemory:
    def record(self, *a, **kw):
        return "p1"

    def get(self, *a, **kw):
        return None

    def summary(self):
        return {}


class TestBrowserEmitFunnel:
    def _specialist(self, script):
        from core.browser.browser_ai import BrowserAI
        return BrowserAI(tool_caller=_FakeCaller(script), procedural_memory=_FakeMemory())

    def test_verified_navigation_emits_action_event(self, monkeypatch):
        fresh_bus = EventBus()
        import core.event_bus as eb
        monkeypatch.setattr(eb, "global_event_bus", fresh_bus)
        seen = []
        fresh_bus.subscribe("action.verified", lambda d: seen.append(d))

        specialist = self._specialist({
            "browser_navigate": {"status": "ok", "result": {"url": "https://example.com"}},
        })
        result = specialist.execute_capability("browser.navigate", {"url": "https://example.com"})
        assert result.verified is True
        assert len(seen) == 1
        event = seen[0]
        assert event["specialist"] == "Browser AI"
        assert event["verified"] is True
        assert event["success"] is True

    def test_failed_action_still_emits_honest_event(self, monkeypatch):
        fresh_bus = EventBus()
        import core.event_bus as eb
        monkeypatch.setattr(eb, "global_event_bus", fresh_bus)
        seen = []
        fresh_bus.subscribe("action.verified", lambda d: seen.append(d))

        specialist = self._specialist({})
        result = specialist.execute_capability("browser.navigate", {"url": "https://example.com"})
        assert result.verified is False
        assert len(seen) == 1
        assert seen[0]["verified"] is False
        assert seen[0]["success"] is False

    def test_goal_level_capability_emits_goal_completed(self, monkeypatch):
        fresh_bus = EventBus()
        import core.event_bus as eb
        monkeypatch.setattr(eb, "global_event_bus", fresh_bus)
        seen = []
        fresh_bus.subscribe("goal.completed", lambda d: seen.append(d))

        specialist = self._specialist({})
        from core.specialist import SpecialistResult
        specialist._emit_outcome_event(
            "browser.execute_workflow",
            {"goal": "research playwright install"},
            SpecialistResult(success=True, verified=True,
                             output={"status": "SUCCESS", "goal": "research playwright install"}),
        )
        assert len(seen) == 1
        assert seen[0]["goal"] == "research playwright install"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
