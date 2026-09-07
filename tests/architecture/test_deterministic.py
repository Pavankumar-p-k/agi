from __future__ import annotations

from datetime import datetime, timezone

from core.pipeline.deterministic import DeterministicServices


class TestRealServices:
    def test_defaults_produce_real_values(self):
        svc = DeterministicServices.real()
        id1 = svc.uuid4()
        id2 = svc.uuid4()
        assert isinstance(id1, str) and len(id1) == 32
        assert id1 != id2  # real UUIDs differ
        now = svc.now()
        assert isinstance(now, datetime)


class TestFakeServices:
    def test_sequential_ids(self):
        svc = DeterministicServices.fake()
        id1 = svc.uuid4()
        id2 = svc.uuid4()
        assert id1 != id2
        assert len(id1) == 32

    def test_fixed_timestamp(self):
        svc = DeterministicServices.fake()
        t1 = svc.now()
        t2 = svc.now()
        assert t1 == t2  # always the same

    def test_fake_with_custom_timestamp(self):
        ts = datetime(2026, 6, 15, tzinfo=timezone.utc)
        svc = DeterministicServices.fake(fixed_now=ts)
        assert svc.now() == ts

    def test_seed_is_42(self):
        svc = DeterministicServices.fake()
        assert svc.seed == 42

    def test_fixed_alias(self):
        svc = DeterministicServices.fixed("2026-07-04T12:00:00Z")
        assert svc.now() == datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc)


class TestInPipelineContext:
    async def test_services_propagate_through_process_message(self):
        from core.pipeline.context import PipelineContext
        ctx = PipelineContext(
            request_id="test-1",
            transport="test",
            services=DeterministicServices.fake(),
        )
        assert ctx.services.uuid4() is not None
        assert ctx.services.now() is not None

    async def test_observation_uses_services(self):
        from core.pipeline.deterministic import DeterministicServices
        from core.pipeline.observation import Observation

        svc = DeterministicServices.fake()
        obs1 = Observation.new(
            activity_id="act-1",
            source="test",
            type_="text",
            payload={"msg": "hello"},
            services=svc,
        )
        obs2 = Observation.new(
            activity_id="act-1",
            source="test",
            type_="text",
            payload={"msg": "hello"},
            services=svc,
        )
        # Same payload produces same fingerprint
        assert obs1.fingerprint == obs2.fingerprint
        # But different IDs (sequential counter)
        assert obs1.id != obs2.id
        # Same timestamp
        assert obs1.timestamp == obs2.timestamp
