from __future__ import annotations

import asyncio

import pytest

from core.event_bus import Event, EventBus
from core.observation import (
    OBSERVATION_CREATED,
    OBSERVATION_OBSERVED,
    ObservationHub,
    get_hub,
    reset_hub,
)
from core.observation.hub import _observation_hub
from core.pipeline.observation import Observation


@pytest.fixture
def fresh_bus():
    return EventBus()


@pytest.fixture
def hub(fresh_bus):
    return ObservationHub(bus=fresh_bus)


@pytest.fixture
def sample_obs():
    return Observation.new(
        activity_id="act-1",
        source="test",
        type_="text",
        payload={"content": "hello"},
    )


class TestPublishObservation:
    async def test_publishes_event_with_correct_type(self, hub, fresh_bus, sample_obs):
        events: list[Event] = []

        async def capture(e: Event):
            events.append(e)

        fresh_bus.subscribe(OBSERVATION_OBSERVED, capture)
        await hub.publish_observation_async(sample_obs)

        assert len(events) == 1
        assert events[0].type == OBSERVATION_OBSERVED
        assert events[0].source == "observation.hub"

    async def test_payload_contains_observation_dict(self, hub, fresh_bus, sample_obs):
        events: list[Event] = []

        async def capture(e: Event):
            events.append(e)

        fresh_bus.subscribe(OBSERVATION_OBSERVED, capture)
        await hub.publish_observation_async(sample_obs)

        payload = events[0].payload
        assert payload["id"] == sample_obs.id
        assert payload["fingerprint"] == sample_obs.fingerprint
        assert payload["activity_id"] == "act-1"
        assert payload["source"] == "test"
        assert payload["type"] == "text"
        assert payload["payload"] == {"content": "hello"}

    async def test_publishes_batch(self, hub, fresh_bus):
        events: list[Event] = []

        async def capture(e: Event):
            events.append(e)

        fresh_bus.subscribe(OBSERVATION_OBSERVED, capture)
        obs_list = [
            Observation.new(activity_id="a", source="test", type_="text", payload={"i": 1}),
            Observation.new(activity_id="a", source="test", type_="text", payload={"i": 2}),
        ]
        await hub.publish_observations_async(obs_list)
        assert len(events) == 2

    async def test_sync_publish_fires_with_sleep(self, hub, fresh_bus, sample_obs):
        events: list[Event] = []

        async def capture(e: Event):
            events.append(e)

        fresh_bus.subscribe(OBSERVATION_OBSERVED, capture)
        hub.publish_observation(sample_obs)
        await asyncio.sleep(0)

        assert len(events) == 1


class TestPublishObservationAsync:
    async def test_publishes_async(self, hub, fresh_bus, sample_obs):
        events: list[Event] = []

        async def capture(e: Event):
            events.append(e)

        fresh_bus.subscribe(OBSERVATION_OBSERVED, capture)
        await hub.publish_observation_async(sample_obs)

        assert len(events) == 1
        assert events[0].type == OBSERVATION_OBSERVED

    async def test_publishes_async_batch(self, hub, fresh_bus):
        events: list[Event] = []

        async def capture(e: Event):
            events.append(e)

        fresh_bus.subscribe(OBSERVATION_OBSERVED, capture)
        obs_list = [
            Observation.new(activity_id="a", source="test", type_="text", payload={"i": 1}),
            Observation.new(activity_id="a", source="test", type_="text", payload={"i": 2}),
        ]
        await hub.publish_observations_async(obs_list)
        assert len(events) == 2


class TestSubscribe:
    async def test_subscribe_default_pattern(self, hub, fresh_bus, sample_obs):
        events: list[Event] = []

        def handler(e: Event):
            events.append(e)

        hub.subscribe(handler)
        await fresh_bus.publish(Event(
            type=OBSERVATION_OBSERVED, source="test", payload={},
        ))

        assert len(events) == 1

    async def test_subscribe_custom_pattern(self, hub, fresh_bus, sample_obs):
        events: list[Event] = []

        def handler(e: Event):
            events.append(e)

        hub.subscribe(handler, pattern=OBSERVATION_CREATED)

        await fresh_bus.publish(Event(
            type=OBSERVATION_CREATED, source="test", payload={},
        ))
        await fresh_bus.publish(Event(
            type=OBSERVATION_OBSERVED, source="test", payload={},
        ))

        assert len(events) == 1
        assert events[0].type == OBSERVATION_CREATED


class TestSubscribeStream:
    async def test_stream_queue(self, hub, fresh_bus, sample_obs):
        queue = hub.subscribe_stream()
        await hub.publish_observation_async(sample_obs)

        item = await queue.get()
        assert item["channel"] == OBSERVATION_OBSERVED
        assert item["payload"]["id"] == sample_obs.id


class TestSingleton:
    def test_get_hub_returns_singleton(self):
        reset_hub()
        a = get_hub()
        b = get_hub()
        assert a is b

    def test_reset_hub_clears_singleton(self):
        reset_hub()
        a = get_hub()
        reset_hub()
        b = get_hub()
        assert a is not b

    def test_singleton_uses_global_event_bus(self):
        reset_hub()
        hub = get_hub()
        assert hub._bus is not None
