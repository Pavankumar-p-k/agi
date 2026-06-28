from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock

from jarvis_tui.app.services.activity_updates import ActivityUpdateService


SAMPLE_CACHE = {
    "activities": [{"id": "act_1", "status": "RUNNING"}],
    "counts": {"total": 1, "running": 1},
}


class _MockClient:
    def __init__(self):
        self.get_activities = AsyncMock(return_value=SAMPLE_CACHE["activities"])
        self.get_activity_counts = AsyncMock(return_value=SAMPLE_CACHE["counts"])


@pytest.fixture
def mock_client():
    return _MockClient()


@pytest.mark.asyncio
async def test_empty_cache_on_create(mock_client):
    svc = ActivityUpdateService(mock_client, poll_interval=999)
    assert svc.cache == {"activities": [], "counts": {}}
    assert svc.is_running is False


@pytest.mark.asyncio
async def test_start_stops_polling(mock_client):
    svc = ActivityUpdateService(mock_client, poll_interval=0.05)
    svc.start()
    assert svc.is_running is True
    await asyncio.sleep(0.12)
    assert mock_client.get_activities.await_count >= 1
    assert mock_client.get_activity_counts.await_count >= 1
    await svc.stop()
    assert svc.is_running is False


@pytest.mark.asyncio
async def test_subscribe_receives_initial_cache(mock_client):
    svc = ActivityUpdateService(mock_client, poll_interval=999)
    received = []

    async def cb(cache):
        received.append(cache)

    svc.subscribe(cb)
    await asyncio.sleep(0.01)
    assert len(received) >= 1
    assert received[0] == {"activities": [], "counts": {}}


@pytest.mark.asyncio
async def test_subscribe_receives_updates(mock_client):
    svc = ActivityUpdateService(mock_client, poll_interval=0.05)
    received = []

    async def cb(cache):
        received.append(cache)

    svc.subscribe(cb)
    svc.start()
    await asyncio.sleep(0.12)
    await svc.stop()
    # Should have received initial + at least one update
    assert len(received) >= 2
    # Last received should have the real data
    assert received[-1]["activities"] == SAMPLE_CACHE["activities"]


@pytest.mark.asyncio
async def test_unsubscribe_stops_updates(mock_client):
    svc = ActivityUpdateService(mock_client, poll_interval=0.05)
    received = []

    async def cb(cache):
        received.append(cache)

    svc.subscribe(cb)
    svc.start()
    await asyncio.sleep(0.12)
    svc.unsubscribe(cb)
    count_before = len(received)
    await asyncio.sleep(0.12)
    # Should not have received new updates after unsubscribe
    assert len(received) == count_before
    await svc.stop()


@pytest.mark.asyncio
async def test_poll_error_does_not_crash_service(mock_client):
    mock_client.get_activities = AsyncMock(side_effect=Exception("API down"))
    svc = ActivityUpdateService(mock_client, poll_interval=0.05)
    received = []

    async def cb(cache):
        received.append(cache)

    svc.subscribe(cb)
    svc.start()
    await asyncio.sleep(0.12)
    # Service should still be running after errors
    assert svc.is_running is True
    await svc.stop()


@pytest.mark.asyncio
async def test_callback_error_does_not_crash_service(mock_client):
    svc = ActivityUpdateService(mock_client, poll_interval=0.05)
    fail_count = 0

    async def failing_cb(cache):
        nonlocal fail_count
        fail_count += 1
        if fail_count == 1:
            pass  # Let the initial one pass
        else:
            raise ValueError("callback error")

    svc.subscribe(failing_cb)
    svc.start()
    await asyncio.sleep(0.12)
    # Service should still be running after callback errors
    assert svc.is_running is True
    await svc.stop()


@pytest.mark.asyncio
async def test_cache_updates_after_poll(mock_client):
    svc = ActivityUpdateService(mock_client, poll_interval=0.05)
    svc.start()
    await asyncio.sleep(0.12)
    await svc.stop()
    cache = svc.cache
    assert cache["activities"] == SAMPLE_CACHE["activities"]
    assert cache["counts"] == SAMPLE_CACHE["counts"]


@pytest.mark.asyncio
async def test_multiple_subscribers(mock_client):
    svc = ActivityUpdateService(mock_client, poll_interval=0.05)
    received_a = []
    received_b = []

    async def cb_a(cache):
        received_a.append(cache)

    async def cb_b(cache):
        received_b.append(cache)

    svc.subscribe(cb_a)
    svc.subscribe(cb_b)
    svc.start()
    await asyncio.sleep(0.12)
    await svc.stop()
    assert len(received_a) >= 2
    assert len(received_b) >= 2
