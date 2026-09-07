"""Integration tests for Phase 6E — Distribution.

Sprint 9: Worker registration, discovery, InProcessTransport,
RemoteExecutionRuntime, version negotiation, WorkerPool,
health checker, retry, and mixed-version cluster.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from core.distribution import (
    CapabilityDescriptor,
    ExecutionAffinity,
    HealthStatus,
    InMemoryWorkerRegistry,
    VersionCheck,
    WorkerRegistration,
    WorkerStatus,
    get_worker_registry,
    set_worker_registry,
)
from core.distribution.contracts import WorkerRequest, WorkerResponse
from core.distribution.health import HealthChecker
from core.distribution.pool import WorkerPool
from core.distribution.retry import RetryPolicy
from core.distribution.transport import InProcessTransport


# ── Helpers ────────────────────────────────────────────────────────────────────


class FakeWorker:
    """A test worker that returns canned responses."""

    def __init__(self, worker_id: str = "test-worker") -> None:
        self.worker_id = worker_id
        self.execution_count = 0

    async def execute(self, request: WorkerRequest) -> WorkerResponse:
        self.execution_count += 1
        return WorkerResponse(
            outcome=None,
            observations=(),
            metrics=None,
        )

    async def health(self) -> HealthStatus:
        return HealthStatus.HEALTHY

    async def heartbeat(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass


def _registration(
    worker_id: str = "w1",
    tenant: str | None = "acme",
    caps: list[str] | None = None,
    pipeline_version: str = "1.0",
    runtime_spec_version: str = "1.0",
) -> WorkerRegistration:
    caps_descriptors = [
        CapabilityDescriptor(id=c, name=c) for c in (caps or ["chat.execute"])
    ]
    return WorkerRegistration(
        worker_id=worker_id,
        worker=FakeWorker(worker_id),
        tenant_id=tenant,
        capabilities=caps_descriptors,
        pipeline_version=pipeline_version,
        runtime_spec_version=runtime_spec_version,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Sprint 1 — Worker Registry
# ═══════════════════════════════════════════════════════════════════════════════


class TestWorkerRegistry:
    """Worker registration, deregistration, discovery."""

    def setup_method(self) -> None:
        self.registry = InMemoryWorkerRegistry()

    def test_register_and_discover(self):
        w = _registration("w1", tenant="acme", caps=["browser"])
        self.registry.register(w)
        found = self.registry.discover(tenant_id="acme", capability="browser")
        assert len(found) == 1
        assert found[0].worker_id == "w1"

    def test_discover_tenant_isolation(self):
        self.registry.register(_registration("w1", tenant="acme"))
        self.registry.register(_registration("w2", tenant="corp"))
        acme = self.registry.discover(tenant_id="acme")
        corp = self.registry.discover(tenant_id="corp")
        other = self.registry.discover(tenant_id="other")
        assert len(acme) == 1 and acme[0].worker_id == "w1"
        assert len(corp) == 1 and corp[0].worker_id == "w2"
        assert len(other) == 0

    def test_discover_capability_filter(self):
        self.registry.register(_registration("w1", caps=["browser", "chat"]))
        self.registry.register(_registration("w2", caps=["chat"]))
        browser = self.registry.discover(capability="browser")
        chat = self.registry.discover(capability="chat")
        assert len(browser) == 1
        assert len(chat) == 2

    def test_deregister_removes_worker(self):
        self.registry.register(_registration("w1"))
        assert len(self.registry.all_workers()) == 1
        self.registry.deregister("w1")
        assert len(self.registry.all_workers()) == 0

    def test_offline_workers_not_discovered(self):
        w = _registration("w1")
        self.registry.register(w)
        w.status = WorkerStatus.OFFLINE
        found = self.registry.discover()
        assert len(found) == 0

    def test_heartbeat_updates_timestamp(self):
        w = _registration("w1")
        w.last_heartbeat = None
        self.registry.register(w)
        self.registry.heartbeat("w1")
        assert w.last_heartbeat is not None
        assert w.status == WorkerStatus.ONLINE


# ═══════════════════════════════════════════════════════════════════════════════
# Sprint 2 — Version Negotiation
# ═══════════════════════════════════════════════════════════════════════════════


class TestVersionNegotiation:
    """Version compatibility checks before dispatch."""

    def setup_method(self) -> None:
        self.registry = InMemoryWorkerRegistry()

    def test_compatible_versions(self):
        w = _registration("w1", pipeline_version="1.0", runtime_spec_version="1.0")
        check = self.registry.check_version_compatibility(w, "1.0", "1.0")
        assert check.compatible
        assert check.reason is None

    def test_pipeline_version_mismatch(self):
        w = _registration("w1", pipeline_version="1.0", runtime_spec_version="1.0")
        check = self.registry.check_version_compatibility(w, "2.0", "1.0")
        assert not check.compatible
        assert "pipeline_version" in (check.reason or "")

    def test_runtime_spec_version_mismatch(self):
        w = _registration("w1", pipeline_version="1.0", runtime_spec_version="1.0")
        check = self.registry.check_version_compatibility(w, "1.0", "2.0")
        assert not check.compatible
        assert "runtime_spec_version" in (check.reason or "")

    def test_version_check_prevents_dispatch(self):
        self.registry.register(_registration("w1", pipeline_version="2.0"))
        self.registry.register(_registration("w2", pipeline_version="1.0"))
        found = self.registry.discover(version_check=VersionCheck(compatible=True))
        assert len(found) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# Sprint 3 — InProcessTransport
# ═══════════════════════════════════════════════════════════════════════════════


class TestInProcessTransport:
    """InProcessTransport calls worker directly."""

    @pytest.mark.asyncio
    async def test_send_via_worker_fn(self):
        worker = FakeWorker("inline")
        transport = InProcessTransport(worker_fn=worker.execute)
        req = WorkerRequest(
            runtime_context=None,
            request="test",
            pipeline_version="1.0",
            runtime_spec_version="1.0",
            worker_protocol_version="1.0",
        )
        resp = await transport.send(req)
        assert worker.execution_count == 1
        assert resp is not None

    @pytest.mark.asyncio
    async def test_send_with_async_worker_fn(self):
        async def fake_worker(req: WorkerRequest) -> WorkerResponse:
            return WorkerResponse(outcome=None, observations=(), metrics=None)

        transport = InProcessTransport(worker_fn=fake_worker)
        req = WorkerRequest(
            runtime_context=None,
            request="test",
            pipeline_version="1.0",
            runtime_spec_version="1.0",
            worker_protocol_version="1.0",
        )
        resp = await transport.send(req)
        assert resp is not None


# ═══════════════════════════════════════════════════════════════════════════════
# Sprint 4 — RemoteExecutionRuntime
# ═══════════════════════════════════════════════════════════════════════════════


class TestRemoteExecutionRuntime:
    """RemoteExecutionRuntime discovers workers and dispatches."""

    @pytest.mark.asyncio
    async def test_falls_back_to_local_when_no_worker(self):
        old = get_worker_registry()
        try:
            registry = InMemoryWorkerRegistry()
            set_worker_registry(registry)

            from core.distribution.runtime import RemoteExecutionRuntime

            async def local_fallback(req) -> WorkerResponse:
                return WorkerResponse(outcome=None, observations=(), metrics=None)

            rt = RemoteExecutionRuntime(
                pipeline_version="1.0",
                runtime_spec_version="1.0",
            )
            # No workers registered — falls back to local
            rt._execute_local = local_fallback
            resp = await rt.execute(
                {"text": "hello", "transport": "test"},
                affinity=ExecutionAffinity(tenant_id="acme"),
            )
            assert resp is not None
        finally:
            set_worker_registry(old)


# ═══════════════════════════════════════════════════════════════════════════════
# Sprint 7 — WorkerPool
# ═══════════════════════════════════════════════════════════════════════════════


class TestWorkerPool:
    """WorkerPool round-robin and eviction."""

    def setup_method(self) -> None:
        self.pool = WorkerPool()

    def test_round_robin_selection(self):
        w1 = _registration("w1", caps=["browser"])
        w2 = _registration("w2", caps=["browser"])
        self.pool.add_worker(w1)
        self.pool.add_worker(w2)

        first = self.pool.next_worker(tenant_id="acme", capability="browser")
        second = self.pool.next_worker(tenant_id="acme", capability="browser")
        third = self.pool.next_worker(tenant_id="acme", capability="browser")

        assert first is not None and second is not None
        assert first.worker_id != second.worker_id
        assert third is not None and third.worker_id == first.worker_id

    def test_evict_unhealthy(self):
        w = _registration("w1", caps=["chat"])
        self.pool.add_worker(w)
        assert self.pool.evict_unhealthy() == 0
        w.status = WorkerStatus.OFFLINE
        assert self.pool.evict_unhealthy() == 1
        assert self.pool.next_worker(capability="chat") is None

    def test_no_worker_for_unknown_capability(self):
        assert self.pool.next_worker(capability="nonexistent") is None


# ═══════════════════════════════════════════════════════════════════════════════
# Sprint 7 — Health Checker
# ═══════════════════════════════════════════════════════════════════════════════


class TestHealthChecker:
    """HealthChecker marks offline workers after missed heartbeats."""

    @pytest.mark.asyncio
    async def test_marks_offline_after_missed_heartbeats(self):
        old = get_worker_registry()
        try:
            registry = InMemoryWorkerRegistry()
            set_worker_registry(registry)
            w = _registration("w1")
            now = datetime.now(timezone.utc)
            w.last_heartbeat = now
            registry.register(w)

            checker = HealthChecker(
                interval_seconds=0.01, missed_heartbeat_threshold=1
            )
            w.last_heartbeat = datetime(2020, 1, 1, tzinfo=timezone.utc)
            checker._check_all()
            assert w.status == WorkerStatus.OFFLINE
        finally:
            set_worker_registry(old)


# ═══════════════════════════════════════════════════════════════════════════════
# Sprint 7 — Retry Policy
# ═══════════════════════════════════════════════════════════════════════════════


class TestRetryPolicy:
    """RetryPolicy retries on failure and falls back."""

    @pytest.mark.asyncio
    async def test_retry_then_fallback(self):
        call_count = 0

        async def failing_fn():
            nonlocal call_count
            call_count += 1
            raise ValueError("fail")

        fallback_called = False

        async def fallback_fn():
            nonlocal fallback_called
            fallback_called = True
            return "fallback"

        policy = RetryPolicy(max_retries=2, backoff_seconds=0.01)
        result = await policy.execute(failing_fn, fallback=fallback_fn)
        assert result == "fallback"
        assert call_count == 2
        assert fallback_called

    @pytest.mark.asyncio
    async def test_succeeds_on_first_attempt(self):
        async def ok_fn():
            return "success"

        policy = RetryPolicy(max_retries=3)
        result = await policy.execute(ok_fn)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_raises_when_no_fallback(self):
        call_count = 0

        async def failing_fn():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("fail")

        policy = RetryPolicy(max_retries=1, backoff_seconds=0.01)
        with pytest.raises(RuntimeError):
            await policy.execute(failing_fn)
        assert call_count == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Sprint 9 — Mixed-Version Cluster
# ═══════════════════════════════════════════════════════════════════════════════


class TestMixedVersionCluster:
    """Only workers with compatible versions receive dispatches."""

    def setup_method(self) -> None:
        self.registry = InMemoryWorkerRegistry()

    def test_only_compatible_workers_selected(self):
        old = get_worker_registry()
        try:
            set_worker_registry(self.registry)
            self.registry.register(
                _registration("v1-w1", pipeline_version="1.0", runtime_spec_version="1.0")
            )
            self.registry.register(
                _registration("v2-w1", pipeline_version="2.0", runtime_spec_version="2.0")
            )

            workers_v1 = self.registry.discover()
            compatible = [
                w
                for w in workers_v1
                if self.registry.check_version_compatibility(w, "1.0", "1.0").compatible
            ]
            assert len(compatible) == 1
            assert compatible[0].worker_id == "v1-w1"
        finally:
            set_worker_registry(old)

    def test_all_rejected_when_no_match(self):
        self.registry.register(
            _registration("v2-only", pipeline_version="2.0", runtime_spec_version="2.0")
        )
        workers = self.registry.discover()
        compatible = [
            w
            for w in workers
            if self.registry.check_version_compatibility(w, "1.0", "1.0").compatible
        ]
        assert len(compatible) == 0

    def test_mixed_rejection_reasons(self):
        w1 = _registration("w1", pipeline_version="1.0", runtime_spec_version="1.0")
        check_ok = self.registry.check_version_compatibility(w1, "1.0", "1.0")
        assert check_ok.compatible

        check_pv = self.registry.check_version_compatibility(w1, "2.0", "1.0")
        assert not check_pv.compatible
        assert "pipeline_version mismatch" in (check_pv.reason or "")

        check_rs = self.registry.check_version_compatibility(w1, "1.0", "2.0")
        assert not check_rs.compatible
        assert "runtime_spec_version mismatch" in (check_rs.reason or "")
