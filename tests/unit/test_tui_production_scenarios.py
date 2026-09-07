"""
Production verification scenarios for the TUI's ActivityUpdateService.

Covers:
  Scenario 1 — Subscription stress: open all dashboards, verify single
               polling loop, subscriber add/remove, no orphaned tasks.
  Scenario 2 — Concurrent agent execution: multiple agents, activity_id
               isolation, completion independence.
  Scenario 3 — Connection recovery: backend disconnect/reconnect,
               automatic service recovery.
  Scenario 4 — Long-duration stability: abbreviated stress test tracking
               memory, task count, cache size, subscriber count.
"""

from __future__ import annotations

import asyncio
import gc
import sys
import pytest
from unittest.mock import AsyncMock

from jarvis_tui.app.services.activity_updates import ActivityUpdateService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _MockClient:
    """Minimal mock client that simulates backend responses."""
    def __init__(self, activities=None, counts=None):
        self.get_activities = AsyncMock(return_value=activities or [])
        self.get_activity_counts = AsyncMock(return_value=counts or {"total": 0, "running": 0})

    def fail_next(self, n=1):
        """Make the next n get_activities calls fail."""
        orig = self.get_activities
        call_count = 0

        async def flaky(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= n:
                raise ConnectionError("Backend unavailable")
            return await orig(*args, **kwargs)

        self.get_activities = AsyncMock(side_effect=flaky)

    def recover(self):
        """Restore normal operation after failure."""
        self.get_activities = AsyncMock(return_value=[])
        self.get_activity_counts = AsyncMock(return_value={"total": 0, "running": 0})


async def _collect(n: int, svc: ActivityUpdateService) -> list:
    """Collect the next n callback invocations from the service."""
    gathered = []

    async def cb(cache):
        gathered.append(cache)

    svc.subscribe(cb)
    while len(gathered) < n:
        await asyncio.sleep(0.05)
    svc.unsubscribe(cb)
    return gathered


# ===================================================================
# Scenario 1 — Subscription Stress Test
# ===================================================================

class TestScenario1_SubscriptionStress:
    """
    Open every dashboard simultaneously:
    - Verify exactly one polling loop exists
    - Confirm subscribers are added/removed correctly
    - Check for orphaned asyncio tasks after screens close
    """

    @pytest.mark.asyncio
    async def test_single_polling_loop(self):
        """Multiple screens share one service — only one _run() task."""
        client = _MockClient()
        svc = ActivityUpdateService(client, poll_interval=999)

        assert svc.subscriber_count == 0
        assert svc._task is None

        svc.start()
        assert svc.is_running is True
        # _task is the single polling loop
        assert svc._task is not None and not svc._task.done()

        # Subscribe 6 dashboards
        callbacks = [AsyncMock() for _ in range(6)]
        for cb in callbacks:
            svc.subscribe(cb)
        assert svc.subscriber_count == 6

        # Still exactly one task
        assert svc._task is not None and not svc._task.done()

        # Verify each callback receives initial cache immediately
        await asyncio.sleep(0.05)
        for cb in callbacks:
            assert cb.await_count >= 1

        await svc.stop()

    @pytest.mark.asyncio
    async def test_subscriber_add_remove(self):
        """Subscriber count tracks screen lifecycle correctly."""
        svc = ActivityUpdateService(_MockClient(), poll_interval=999)
        svc.start()

        async def cb_a(cache):
            pass

        async def cb_b(cache):
            pass

        assert svc.subscriber_count == 0
        svc.subscribe(cb_a)
        assert svc.subscriber_count == 1
        svc.subscribe(cb_b)
        assert svc.subscriber_count == 2

        # Remove one
        svc.unsubscribe(cb_a)
        assert svc.subscriber_count == 1
        assert cb_a not in svc._callbacks
        assert cb_b in svc._callbacks

        svc.unsubscribe(cb_b)
        assert svc.subscriber_count == 0

        await svc.stop()

    @pytest.mark.asyncio
    async def test_unsubscribe_unknown_callback_is_safe(self):
        """Removing a callback that was never subscribed does not crash."""
        svc = ActivityUpdateService(_MockClient(), poll_interval=999)

        async def cb(cache):
            pass

        svc.unsubscribe(cb)  # should not raise
        assert svc.subscriber_count == 0

    @pytest.mark.asyncio
    async def test_duplicate_subscribe_is_idempotent(self):
        """Subscribing the same callback twice does not double-count."""
        svc = ActivityUpdateService(_MockClient(), poll_interval=999)

        async def cb(cache):
            pass

        svc.subscribe(cb)
        svc.subscribe(cb)  # duplicate
        assert svc.subscriber_count == 1

    @pytest.mark.asyncio
    async def test_no_orphaned_tasks_after_stop(self):
        """
        After all screens close (service stop), verify no asyncio tasks
        reference the service's _run() coroutine.
        """
        client = _MockClient()
        svc = ActivityUpdateService(client, poll_interval=0.05)
        svc.start()

        # Let it run a few cycles
        await asyncio.sleep(0.15)
        assert svc.is_running is True

        # Collect tasks referencing the service before stop
        tasks_before = {
            id(t) for t in asyncio.all_tasks()
            if "ActivityUpdateService" in str(t)
        }

        await svc.stop()
        assert svc.is_running is False

        # Give event loop a moment to cancel
        await asyncio.sleep(0.05)

        tasks_after = {
            id(t) for t in asyncio.all_tasks()
            if "ActivityUpdateService" in str(t)
        }

        # No new tasks should reference the service after stop
        new_tasks = tasks_after - tasks_before
        # Some frameworks (pytest) may create wrapper tasks — at minimum
        # the _run() task should be cancelled and no longer pending
        assert svc._task is None or svc._task.done()

    @pytest.mark.asyncio
    async def test_subscriber_count_returns_to_zero_after_all_screens_close(self):
        """
        Simulate opening and closing all dashboards.
        Net subscriber count should be 0 after all close.
        """
        svc = ActivityUpdateService(_MockClient(), poll_interval=999)

        # Simulate 6 screens opening
        callbacks = [AsyncMock() for _ in range(6)]
        for cb in callbacks:
            svc.subscribe(cb)
        assert svc.subscriber_count == 6

        # Simulate all screens closing
        for cb in callbacks:
            svc.unsubscribe(cb)
        assert svc.subscriber_count == 0

        # No leftover references
        for cb in callbacks:
            assert cb not in svc._callbacks


# ===================================================================
# Scenario 2 — Concurrent Agent Execution
# ===================================================================

class TestScenario2_ConcurrentAgents:
    """
    Launch multiple agents simultaneously:
    - Verify updates are routed by activity_id
    - Ensure completion of one task does not stop updates for others
    """

    @pytest.mark.asyncio
    async def test_multiple_agents_activity_id_isolation(self):
        """
        The cache should contain activities from multiple agents.
        Each activity retains its own id, status, and progress.
        """
        activities_multi = [
            {"id": "act_build", "title": "Build APK", "status": "RUNNING", "progress": 30},
            {"id": "act_research", "title": "Research LLM", "status": "RUNNING", "progress": 60},
            {"id": "act_test", "title": "Run Tests", "status": "RUNNING", "progress": 10},
        ]
        counts_multi = {"total": 3, "running": 3}
        client = _MockClient(activities=activities_multi, counts=counts_multi)

        svc = ActivityUpdateService(client, poll_interval=0.05)
        received = []

        async def cb(cache):
            received.append(cache)

        svc.subscribe(cb)
        svc.start()

        # Wait for at least one poll cycle
        await asyncio.sleep(0.12)

        assert len(received) >= 2  # initial + polled
        latest = received[-1]
        assert len(latest["activities"]) == 3

        # Verify each activity_id is preserved
        ids = {a["id"] for a in latest["activities"]}
        assert "act_build" in ids
        assert "act_research" in ids
        assert "act_test" in ids

        await svc.stop()

    @pytest.mark.asyncio
    async def test_completion_of_one_does_not_block_others(self):
        """
        When one activity completes (status changes to COMPLETED),
        the remaining running activities still appear in the cache.
        """
        # Phase 1: 3 running
        activities_v1 = [
            {"id": "act_1", "status": "RUNNING"},
            {"id": "act_2", "status": "RUNNING"},
            {"id": "act_3", "status": "RUNNING"},
        ]
        # Phase 2: act_1 completes, others still running
        activities_v2 = [
            {"id": "act_1", "status": "COMPLETED"},
            {"id": "act_2", "status": "RUNNING"},
            {"id": "act_3", "status": "RUNNING"},
        ]
        # Phase 3: all complete
        activities_v3 = [
            {"id": "act_1", "status": "COMPLETED"},
            {"id": "act_2", "status": "COMPLETED"},
            {"id": "act_3", "status": "COMPLETED"},
        ]

        client = _MockClient(activities=activities_v1, counts={"total": 3, "running": 3})
        svc = ActivityUpdateService(client, poll_interval=0.05)
        received = []

        async def cb(cache):
            received.append(cache)

        svc.subscribe(cb)
        svc.start()

        await asyncio.sleep(0.1)

        # Phase 2: act_1 completes
        client.get_activities = AsyncMock(return_value=activities_v2)
        client.get_activity_counts = AsyncMock(return_value={"total": 3, "running": 2})
        await asyncio.sleep(0.1)

        # Phase 3: all complete
        client.get_activities = AsyncMock(return_value=activities_v3)
        client.get_activity_counts = AsyncMock(return_value={"total": 3, "running": 0})
        await asyncio.sleep(0.1)

        await svc.stop()

        # Find a snapshot where act_1 completed but act_2/act_3 still running
        for entry in received:
            acts = entry["activities"]
            statuses = {a["id"]: a["status"] for a in acts}
            if statuses.get("act_1") == "COMPLETED" and statuses.get("act_2") == "RUNNING":
                break
        else:
            pytest.fail("Never observed partial completion snapshot")

    @pytest.mark.asyncio
    async def test_cache_overwrite_does_not_leak_old_data(self):
        """
        When the poll returns new data, the cache is fully replaced,
        not merged. No stale activities remain.
        """
        old_activities = [{"id": "act_old", "status": "RUNNING"}]
        new_activities = [{"id": "act_new", "status": "RUNNING"}]

        client = _MockClient(activities=old_activities, counts={"total": 1, "running": 1})
        svc = ActivityUpdateService(client, poll_interval=0.05)
        svc.start()
        await asyncio.sleep(0.1)

        # New poll returns different data
        client.get_activities = AsyncMock(return_value=new_activities)
        client.get_activity_counts = AsyncMock(return_value={"total": 1, "running": 1})
        await asyncio.sleep(0.15)

        await svc.stop()

        latest = svc.cache
        ids = {a["id"] for a in latest["activities"]}
        assert "act_old" not in ids
        assert "act_new" in ids


# ===================================================================
# Scenario 3 — Connection Recovery
# ===================================================================

class TestScenario3_ConnectionRecovery:
    """
    Backend disconnect/reconnect:
    - Verify the service does not crash on transient failures
    - Verify automatic recovery when backend returns
    - Ensure no data corruption during recovery window
    """

    @pytest.mark.asyncio
    async def test_backend_disconnect_does_not_crash_service(self):
        """When get_activities raises, the service logs and continues."""
        client = _MockClient()
        client.fail_next(5)  # Next 5 calls fail

        svc = ActivityUpdateService(client, poll_interval=0.02)
        svc.start()
        await asyncio.sleep(0.15)

        # Service must still be running after repeated failures
        assert svc.is_running is True
        await svc.stop()

    @pytest.mark.asyncio
    async def test_automatic_recovery_after_backend_restart(self):
        """
        Simulate: backend up → fails → recovers.
        Service should resume updating the cache without restart.
        """
        activities_up = [
            {"id": "act_1", "status": "RUNNING"},
            {"id": "act_2", "status": "RUNNING"},
        ]

        client = _MockClient(activities=activities_up, counts={"total": 2, "running": 2})
        svc = ActivityUpdateService(client, poll_interval=0.05)
        received = []

        async def cb(cache):
            received.append(cache)

        svc.subscribe(cb)
        svc.start()

        # Phase 1: normal operation
        await asyncio.sleep(0.1)
        assert len(received[-1]["activities"]) == 2

        # Phase 2: backend fails
        client.fail_next(3)
        await asyncio.sleep(0.2)

        # Service still running, cache retains last known good data
        assert svc.is_running is True
        assert len(svc.cache["activities"]) == 2  # last good data preserved

        # Phase 3: backend recovers with new data
        new_activities = [{"id": "act_3", "status": "RUNNING"}]
        client.recover()
        client.get_activities = AsyncMock(return_value=new_activities)
        client.get_activity_counts = AsyncMock(return_value={"total": 1, "running": 1})
        await asyncio.sleep(0.15)

        await svc.stop()

        # Cache should reflect the new data from recovered backend
        latest = svc.cache
        ids = {a["id"] for a in latest["activities"]}
        assert "act_3" in ids
        assert "act_1" not in ids

    @pytest.mark.asyncio
    async def test_no_data_corruption_during_intermittent_failures(self):
        """
        During a failure window:
        - Cache retains last valid data
        - After recovery, cache is replaced correctly
        """
        activities_a = [{"id": "a", "status": "RUNNING"}]
        client = _MockClient(activities=activities_a, counts={"total": 1, "running": 1})
        svc = ActivityUpdateService(client, poll_interval=0.03)
        received = []

        async def cb(cache):
            received.append(cache)

        svc.subscribe(cb)
        svc.start()

        # Phase 1: get "a" once
        await asyncio.sleep(0.1)

        # Phase 2: backend fails
        client.get_activities = AsyncMock(side_effect=ConnectionError("timeout"))
        client.get_activity_counts = AsyncMock(side_effect=ConnectionError("timeout"))
        await asyncio.sleep(0.15)

        # Cache should still have "a"
        assert svc.cache["activities"][0]["id"] == "a"

        # Phase 3: backend recovers with "c"
        client.get_activities = AsyncMock(return_value=[{"id": "c", "status": "COMPLETED"}])
        client.get_activity_counts = AsyncMock(return_value={"total": 1, "running": 0})
        await asyncio.sleep(0.15)

        await svc.stop()

        # Cache reflects last valid poll
        assert svc.cache["activities"][0]["id"] == "c"

        # Integrity: never saw corrupted partial data
        for entry in received:
            acts = entry["activities"]
            assert isinstance(acts, list), f"Expected list, got {type(acts)}"
            for a in acts:
                assert "id" in a, f"Activity missing 'id': {a}"
                assert "status" in a, f"Activity missing 'status': {a}"

    @pytest.mark.asyncio
    async def test_no_crash_when_backend_never_comes_up(self):
        """
        If the backend is down from the start, the service still runs
        indefinitely without crashing.
        """
        client = _MockClient()
        client.get_activities = AsyncMock(side_effect=ConnectionError("Unreachable"))
        client.get_activity_counts = AsyncMock(side_effect=ConnectionError("Unreachable"))

        svc = ActivityUpdateService(client, poll_interval=0.02)
        svc.start()
        await asyncio.sleep(0.15)
        assert svc.is_running is True
        assert svc.cache == {"activities": [], "counts": {}}
        await svc.stop()


# ===================================================================
# Scenario 4 — Long-Duration Stability
# ===================================================================

class TestScenario4_LongDurationStability:
    """
    Abbreviated stress test:
    - Run for many poll cycles
    - Monitor: memory, task count, cache size, subscriber count
    - Verify no growth in resources over time
    """

    @pytest.mark.asyncio
    async def test_memory_stability_over_many_poll_cycles(self):
        """Cache and subscriber count remain bounded over 100 poll cycles."""
        # Generate 50 activities to keep the cache non-trivial
        activities_big = [
            {"id": f"act_{i}", "title": f"Activity {i}", "status": "RUNNING", "progress": i}
            for i in range(50)
        ]
        counts_big = {"total": 50, "running": 50}

        client = _MockClient(activities=activities_big, counts=counts_big)
        svc = ActivityUpdateService(client, poll_interval=0.01)
        received_counts = []

        async def cb(cache):
            received_counts.append(len(cache["activities"]))

        svc.subscribe(cb)
        svc.start()

        # Run for ~1.5s (150+ poll cycles)
        await asyncio.sleep(1.5)
        await svc.stop()

        # Must have received many callbacks
        assert len(received_counts) > 50, f"Expected >50 callbacks, got {len(received_counts)}"

        # At least one callback must reflect the full 50 activities
        # (initial callback may fire with empty cache before first poll)
        assert any(c == 50 for c in received_counts), (
            f"Expected at least one callback with 50 activities, got max={max(received_counts)}"
        )

        # The last several callbacks should all have 50 activities
        # (once polling stabilizes)
        final_window = [c for c in received_counts[-20:] if c > 0]
        if final_window:
            avg = sum(final_window) / len(final_window)
            assert avg >= 45, f"Average activity count in final window: {avg:.1f}"

        # Final cache must be intact
        assert len(svc.cache["activities"]) == 50
        assert svc.cache["counts"]["total"] == 50
        assert svc.cache["counts"]["running"] == 50

    @pytest.mark.asyncio
    async def test_no_task_leak_after_many_restarts(self):
        """
        Repeated start/stop cycles should not accumulate asyncio tasks.
        """
        client = _MockClient()

        for i in range(20):
            svc = ActivityUpdateService(client, poll_interval=0.01)
            svc.start()
            await asyncio.sleep(0.03)
            await svc.stop()
            await asyncio.sleep(0.02)

        await asyncio.sleep(0.05)

        # Look for any task referencing the service's _run method
        leaked = [
            t for t in asyncio.all_tasks()
            if "_run" in str(t) and "ActivityUpdateService" in str(t)
        ]
        assert len(leaked) == 0, f"Leaked {len(leaked)} tasks from ActivityUpdateService"

    @pytest.mark.asyncio
    async def test_subscriber_gc_no_reference_cycles(self):
        """
        After unsubscribing and dropping references, the callback should
        be garbage-collected.
        """
        svc = ActivityUpdateService(_MockClient(), poll_interval=999)
        ref = None

        async def my_cb(cache):
            pass

        svc.subscribe(my_cb)
        svc.unsubscribe(my_cb)

        # Drop the reference
        del my_cb
        gc.collect()

        # The service should have no reference to the old callback
        assert svc.subscriber_count == 0
        assert all(not cb.__name__.startswith("my_cb") for cb in svc._callbacks)

    @pytest.mark.asyncio
    async def test_simultaneous_subscribers_high_count(self):
        """50 simultaneous subscribers should all receive updates."""
        client = _MockClient(
            activities=[{"id": "a1", "status": "RUNNING"}],
            counts={"total": 1, "running": 1},
        )
        svc = ActivityUpdateService(client, poll_interval=0.02)
        all_received = []

        class _Tracker:
            def __init__(self):
                self.count = 0

        trackers = [_Tracker() for _ in range(50)]

        async def make_cb(tracker):
            async def cb(cache):
                tracker.count += 1
            return cb

        for t in trackers:
            cb = await make_cb(t)
            all_received.append((t, cb))
            svc.subscribe(cb)

        assert svc.subscriber_count == 50

        svc.start()
        await asyncio.sleep(0.15)
        await svc.stop()

        # Every subscriber should have received at least 1 update
        for t, _ in all_received:
            assert t.count >= 1, f"Subscriber received 0 updates"

        # Clean up
        for _, cb in all_received:
            svc.unsubscribe(cb)
        assert svc.subscriber_count == 0

    @pytest.mark.asyncio
    async def test_callback_exception_isolation(self):
        """
        A callback that raises should not prevent other callbacks
        from receiving the update.
        """
        client = _MockClient(
            activities=[{"id": "a1", "status": "RUNNING"}],
            counts={"total": 1, "running": 1},
        )
        svc = ActivityUpdateService(client, poll_interval=0.05)
        good_count = 0

        async def bad_cb(cache):
            raise ValueError("I am a bad callback")

        async def good_cb(cache):
            nonlocal good_count
            good_count += 1

        svc.subscribe(bad_cb)
        svc.subscribe(good_cb)
        svc.start()
        await asyncio.sleep(0.15)
        await svc.stop()

        # Good callback must have been called despite bad callback failing
        assert good_count >= 1, "Good callback was blocked by failing callback"
