"""Comprehensive tests for the JARVIS v3 provider ecosystem.

Matches actual implementation APIs from core/providers/.
All tests properly isolated — no singleton pollution.
"""

import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
from typing import Any

import pytest


# ── Helpers ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def clean_provider_state():
    """Clean up any singleton state leaked between tests."""
    from core.providers.memory import provider_memory
    from core.providers.budget import provider_budget
    from core.providers.registry import provider_registry
    provider_memory._records.clear()
    provider_budget._records.clear()
    provider_budget._limits.clear()
    yield


@pytest.fixture
def temp_root():
    """Create a unique temp directory for provider test isolation."""
    root = tempfile.mkdtemp()
    yield root
    shutil.rmtree(root, ignore_errors=True)


@pytest.fixture
def clean_registry(temp_root):
    """Create a ProviderRegistry with isolated storage path."""
    from core.providers.registry import ProviderRegistry
    reg = ProviderRegistry()
    settings_dir = Path(temp_root) / "provider_settings"
    settings_dir.mkdir(parents=True, exist_ok=True)
    reg._PROVIDER_SETTINGS_DIR = settings_dir
    reg._PROVIDER_SETTINGS_FILE = settings_dir / "registry.json"
    reg._providers.clear()
    reg._priorities.clear()
    reg._capability_index.clear()
    reg._pending_settings.clear()
    return reg


@pytest.fixture
def clean_memory(temp_root):
    """Create a ProviderMemory with isolated storage path."""
    from core.providers.memory import ProviderMemory
    mem = ProviderMemory()
    mem_dir = Path(temp_root) / "provider_memory"
    mem_dir.mkdir(parents=True, exist_ok=True)
    mem._MEMORY_DIR = mem_dir
    mem._MEMORY_FILE = mem_dir / "memory.json"
    mem._records.clear()
    return mem


@pytest.fixture
def clean_budget(temp_root):
    """Create a ProviderBudgetManager with isolated storage path."""
    from core.providers.budget import ProviderBudgetManager
    budget = ProviderBudgetManager()
    budget_dir = Path(temp_root) / "provider_budgets"
    budget_dir.mkdir(parents=True, exist_ok=True)
    budget._BUDGET_DIR = budget_dir
    budget._BUDGET_FILE = budget_dir / "budgets.json"
    budget._records.clear()
    budget._limits.clear()
    return budget


@pytest.fixture
def clean_router(clean_registry, clean_memory, clean_budget):
    """Create a ProviderRouter with isolated dependencies."""
    from core.providers.router import ProviderRouter
    return ProviderRouter(
        registry=clean_registry,
        memory=clean_memory,
        budget=clean_budget,
    )


# ── Concrete helper for ABC tests ────────────────────────────────────────────


@pytest.fixture
def concrete_provider():
    """Return a concrete ExecutionProvider subclass for testing base logic."""
    from core.providers.base import (
        ExecutionProvider, ProviderCapabilities,
        ProviderHealth, ProviderHealthStatus, ExecutionResult,
    )

    class _Concrete(ExecutionProvider):
        provider_id = "concrete"
        name = "Concrete"
        version = "1.0"
        priority = 50
        installed = True
        _enabled = True

        def capabilities(self) -> ProviderCapabilities:
            return ProviderCapabilities(capability_names=["coding"])

        async def health(self) -> ProviderHealth:
            return ProviderHealth(status=ProviderHealthStatus.HEALTHY)

        async def execute(self, task: dict[str, Any], context=None) -> ExecutionResult:
            return ExecutionResult(success=True, output="ok")

    return _Concrete()


# ── Base Models ──────────────────────────────────────────────────────────────


class TestExecutionProviderBase:
    def test_provider_capabilities_defaults(self):
        from core.providers.base import ProviderCapabilities
        caps = ProviderCapabilities()
        assert caps.capability_names == []
        assert caps.languages == []
        assert caps.frameworks == []

    def test_provider_capabilities_with_values(self):
        from core.providers.base import ProviderCapabilities
        caps = ProviderCapabilities(
            capability_names=["coding", "debugging"],
            languages=["python", "javascript"],
            frameworks=["django", "react"],
        )
        assert "coding" in caps.capability_names
        assert "python" in caps.languages
        assert "django" in caps.frameworks

    def test_provider_health_status_enum(self):
        from core.providers.base import ProviderHealthStatus
        assert ProviderHealthStatus.HEALTHY.value == "healthy"
        assert ProviderHealthStatus.DEGRADED.value == "degraded"
        assert ProviderHealthStatus.DOWN.value == "down"

    def test_execution_result(self):
        from core.providers.base import ExecutionResult
        r = ExecutionResult(success=True, output="test output", duration_ms=100)
        assert r.success is True
        assert r.output == "test output"
        assert r.duration_ms == 100

    def test_execution_result_with_error(self):
        from core.providers.base import ExecutionResult
        r = ExecutionResult(success=False, output="", error="Something broke")
        assert r.success is False
        assert r.error == "Something broke"

    def test_provider_health_dataclass_defaults(self):
        from core.providers.base import ProviderHealth, ProviderHealthStatus
        h = ProviderHealth()
        assert h.status == ProviderHealthStatus.UNKNOWN
        assert h.latency_ms == 0.0
        assert h.error == ""


class TestExecutionProviderABC:
    def test_enable_disable_lifecycle(self, concrete_provider):
        p = concrete_provider
        assert p.enabled is True
        p.disable()
        assert p.enabled is False
        p.enable()
        assert p.enabled is True

    def test_enabled_property_false_when_not_installed(self, concrete_provider):
        p = concrete_provider
        p.installed = False
        assert p.enabled is False

    def test_supports_capability(self, concrete_provider):
        p = concrete_provider
        assert p.supports("coding") is True
        assert p.supports("debugging") is False

    def test_available_checks_health_cache(self, concrete_provider):
        from core.providers.base import ProviderHealth, ProviderHealthStatus
        p = concrete_provider
        p._health_cache = ProviderHealth(status=ProviderHealthStatus.HEALTHY)
        assert p.available() is True
        p._health_cache = ProviderHealth(status=ProviderHealthStatus.DOWN)
        assert p.available() is False

    def test_available_false_when_disabled(self, concrete_provider):
        p = concrete_provider
        p._health_cache.status = "healthy"
        p.disable()
        assert p.available() is False

    def test_stream_default(self, concrete_provider):
        """stream() yields empty string first, then raises NotImplementedError."""
        p = concrete_provider
        import asyncio
        stream = p.stream({"task": "test"})
        # First __anext__ returns the yield ""
        first = asyncio.run(stream.__anext__())
        assert first == ""
        # Second __anext__ raises NotImplementedError
        with pytest.raises(NotImplementedError):
            asyncio.run(stream.__anext__())

    def test_cancel_default(self, concrete_provider):
        p = concrete_provider
        import asyncio
        result = asyncio.run(p.cancel("exec_123"))
        assert result is False

    def test_estimate_cost_default(self, concrete_provider):
        p = concrete_provider
        import asyncio
        assert asyncio.run(p.estimate_cost({})) == 0.0

    def test_estimate_latency_default(self, concrete_provider):
        p = concrete_provider
        import asyncio
        assert asyncio.run(p.estimate_latency({})) == 0.0

    def test_diagnostics(self, concrete_provider):
        p = concrete_provider
        import asyncio
        diag = asyncio.run(p.diagnostics())
        assert diag["provider_id"] == "concrete"


# ── Provider Implementations ────────────────────────────────────────────────


class TestForgeProvider:
    def test_forge_provider_attributes(self):
        from core.providers.adapters.forge import ForgeProvider
        p = ForgeProvider()
        assert p.provider_id == "forge"
        assert p.name == "Forge"
        assert p.version == "1.0.0"
        assert p.priority == 10
        assert p.installed is True
        assert p.enabled is True

    def test_forge_provider_capabilities(self):
        from core.providers.adapters.forge import ForgeProvider
        p = ForgeProvider()
        caps = p.capabilities()
        assert "coding" in caps.capability_names
        assert "python" in caps.languages

    @pytest.mark.asyncio
    async def test_forge_provider_health(self):
        from core.providers.adapters.forge import ForgeProvider
        from core.providers.base import ProviderHealthStatus
        p = ForgeProvider()
        health = await p.health()
        assert health.status == ProviderHealthStatus.HEALTHY
        assert health.latency_ms == 0.0

    @pytest.mark.asyncio
    async def test_forge_provider_execute_handles_failure(self):
        from core.providers.adapters.forge import ForgeProvider
        p = ForgeProvider()
        # Mock the ForgeAgent to fail
        with patch("core.providers.adapters.forge.ForgeSubAgent") as mock_agent_cls:
            mock_instance = MagicMock()
            mock_instance.run = AsyncMock(side_effect=RuntimeError("forge failure"))
            mock_agent_cls.return_value = mock_instance
            result = await p.execute({"goal": "test", "mode": "generate"})
            assert result.success is False
            assert "forge failure" in result.error


class TestExternalProviders:
    def test_claude_code_attributes(self):
        from core.providers.adapters.claude_code import ClaudeCodeProvider
        p = ClaudeCodeProvider()
        assert p.provider_id == "claude_code"
        assert p.name == "Claude Code"

    def test_codex_attributes(self):
        from core.providers.adapters.codex import CodexProvider
        p = CodexProvider()
        assert p.provider_id == "codex"
        assert p.name == "Codex CLI"

    @pytest.mark.asyncio
    async def test_claude_code_execute_no_cli(self):
        from core.providers.adapters.claude_code import ClaudeCodeProvider
        p = ClaudeCodeProvider()
        result = await p.execute({"goal": "test"})
        assert result.success is False

    def test_claude_code_capabilities(self):
        from core.providers.adapters.claude_code import ClaudeCodeProvider
        p = ClaudeCodeProvider()
        caps = p.capabilities()
        assert "coding" in caps.capability_names
        assert "research" in caps.capability_names

    def test_codex_capabilities(self):
        from core.providers.adapters.codex import CodexProvider
        p = CodexProvider()
        caps = p.capabilities()
        assert "coding" in caps.capability_names
        assert "scaffold" in caps.capability_names


# ── ProviderRegistry ─────────────────────────────────────────────────────────


class TestProviderRegistry:
    def _make_provider(self, pid="mock", caps=None):
        from core.providers.base import (
            ExecutionProvider, ProviderCapabilities,
            ProviderHealth, ProviderHealthStatus, ExecutionResult,
        )
        caps_list = caps or ["coding"]

        class _P(ExecutionProvider):
            provider_id = pid
            name = pid.title()
            version = "1.0"
            priority = 50
            installed = True
            _enabled = True
            def capabilities(self): return ProviderCapabilities(capability_names=list(caps_list))
            async def health(self): return ProviderHealth(status=ProviderHealthStatus.HEALTHY)
            async def execute(self, task, ctx=None): return ExecutionResult(success=True, output="ok")

        return _P()

    def test_register_and_get(self, clean_registry):
        p = self._make_provider("mock")
        clean_registry.register(p, priority=50)
        assert clean_registry.get("mock") is p

    def test_register_duplicate_overwrites(self, clean_registry):
        p1 = self._make_provider("mock")
        p2 = self._make_provider("mock")
        clean_registry.register(p1, priority=50)
        clean_registry.register(p2, priority=50)
        assert clean_registry.get("mock") is p2

    def test_list_providers(self, clean_registry):
        clean_registry.register(self._make_provider("p1"), priority=50)
        clean_registry.register(self._make_provider("p2"), priority=50)
        assert len(clean_registry.list_providers()) == 2

    def test_unregister(self, clean_registry):
        p = self._make_provider("mock")
        clean_registry.register(p, priority=50)
        assert clean_registry.unregister("mock") is True
        assert clean_registry.get("mock") is None

    def test_unregister_unknown(self, clean_registry):
        assert clean_registry.unregister("nonexistent") is False

    def test_enable_disable(self, clean_registry):
        p = self._make_provider("mock")
        clean_registry.register(p, priority=50)
        assert clean_registry.is_enabled("mock") is True
        clean_registry.disable("mock")
        assert clean_registry.is_enabled("mock") is False
        clean_registry.enable("mock")
        assert clean_registry.is_enabled("mock") is True

    def test_enable_unknown_returns_false(self, clean_registry):
        assert clean_registry.enable("nonexistent") is False

    def test_disable_unknown_returns_false(self, clean_registry):
        assert clean_registry.disable("nonexistent") is False

    def test_priority(self, clean_registry):
        p = self._make_provider("mock")
        clean_registry.register(p, priority=10)
        assert clean_registry.get_priority("mock") == 10
        clean_registry.set_priority("mock", 90)
        assert clean_registry.get_priority("mock") == 90

    def test_set_priority_unknown(self, clean_registry):
        assert clean_registry.set_priority("nonexistent", 10) is False

    def test_get_priority_default(self, clean_registry):
        assert clean_registry.get_priority("nonexistent") == 100

    def test_capability_index(self, clean_registry):
        p = self._make_provider("mock", caps=["coding", "debugging"])
        clean_registry.register(p, priority=50)
        providers = clean_registry.get_providers_for_capability("coding")
        assert len(providers) == 1
        assert providers[0].provider_id == "mock"

    def test_capability_index_unknown(self, clean_registry):
        assert clean_registry.get_providers_for_capability("nonexistent") == []

    def test_has_capability(self, clean_registry):
        p = self._make_provider("mock", caps=["coding"])
        clean_registry.register(p, priority=50)
        assert clean_registry.has_capability("coding") is True
        assert clean_registry.has_capability("nonexistent") is False

    def test_all_capabilities(self, clean_registry):
        p = self._make_provider("mock", caps=["coding", "debugging"])
        clean_registry.register(p, priority=50)
        caps = clean_registry.all_capabilities()
        assert "coding" in caps
        assert "debugging" in caps

    def test_link_plugin_registry(self, clean_registry):
        from core.plugins.base import PluginRegistry
        pr = PluginRegistry()
        clean_registry.link_plugin_registry(pr)
        assert clean_registry.plugin_registry is pr

    def test_list_enabled(self, clean_registry):
        p1 = self._make_provider("p1", caps=["coding"])
        p2 = self._make_provider("p2", caps=["coding"])
        clean_registry.register(p1, priority=50)
        clean_registry.register(p2, priority=50)
        assert len(clean_registry.list_enabled()) == 2
        clean_registry.disable("p1")
        enabled = clean_registry.list_enabled()
        assert len(enabled) == 1
        assert enabled[0].provider_id == "p2"

    def test_singleton_exists(self):
        from core.providers.registry import provider_registry
        assert provider_registry is not None

    def test_sorted_providers(self, clean_registry):
        p1 = self._make_provider("low_prio")
        p2 = self._make_provider("high_prio")
        clean_registry.register(p1, priority=100)
        clean_registry.register(p2, priority=10)
        sorted_p = clean_registry._sorted_providers()
        # lower priority number = more important, sorted first
        assert sorted_p[0].provider_id == "high_prio"

    def test_persist_and_reload(self, clean_registry, temp_root):
        p = self._make_provider("mock")
        clean_registry.register(p, priority=10)
        clean_registry.disable("mock")
        # Create new registry, re-register provider, load from same path
        from core.providers.registry import ProviderRegistry
        reg2 = ProviderRegistry()
        settings_dir = Path(temp_root) / "provider_settings"
        reg2._PROVIDER_SETTINGS_DIR = settings_dir
        reg2._PROVIDER_SETTINGS_FILE = settings_dir / "registry.json"
        reg2.register(self._make_provider("mock"), priority=50)
        # Settings from previous registry should apply
        assert reg2.get_priority("mock") == 10
        assert reg2.is_enabled("mock") is False


# ── ProviderMemory ───────────────────────────────────────────────────────────


class TestProviderMemory:
    def test_record_execution_basic(self, clean_memory):
        mem = clean_memory
        mem.record_execution(provider_id="test_p", success=True, duration_ms=100, capability="coding")
        record = mem.get_record("test_p")
        assert record.total_executions == 1
        assert record.successful_executions == 1
        assert record.success_rate == 1.0

    def test_record_execution_failure(self, clean_memory):
        mem = clean_memory
        mem.record_execution(provider_id="test_p", success=False, duration_ms=50, capability="debugging")
        record = mem.get_record("test_p")
        assert record.success_rate == 0.0
        assert record.consecutive_failures == 1

    def test_record_execution_multiple(self, clean_memory):
        mem = clean_memory
        for i in range(5):
            mem.record_execution(provider_id="test_p", success=i < 4, duration_ms=100.0, capability="coding")
        record = mem.get_record("test_p")
        assert record.total_executions == 5
        assert record.successful_executions == 4
        assert record.success_rate == 0.8

    def test_get_score_below_min_samples(self, clean_memory):
        mem = clean_memory
        mem.record_execution(provider_id="test_p", success=True, duration_ms=100, capability="coding")
        assert mem.get_score("test_p") == 0.5

    def test_get_score_above_min_samples(self, clean_memory):
        mem = clean_memory
        for _ in range(3):
            mem.record_execution(provider_id="test_p", success=True, duration_ms=100, capability="coding")
        assert mem.get_score("test_p") == 1.0

    def test_get_score_no_data(self, clean_memory):
        assert clean_memory.get_score("nonexistent") == 0.5

    def test_should_skip_after_consecutive_failures(self, clean_memory):
        mem = clean_memory
        for _ in range(3):
            mem.record_execution(provider_id="test_p", success=False, duration_ms=100, capability="coding")
        assert mem.should_skip("test_p") is True

    def test_should_skip_low_success_rate(self, clean_memory):
        mem = clean_memory
        for _ in range(5):
            mem.record_execution(provider_id="test_p", success=False, duration_ms=100, capability="coding")
        assert mem.should_skip("test_p") is True

    def test_should_not_skip_good_performer(self, clean_memory):
        mem = clean_memory
        for _ in range(5):
            mem.record_execution(provider_id="test_p", success=True, duration_ms=100, capability="coding")
        assert mem.should_skip("test_p") is False

    def test_per_capability_counters(self, clean_memory):
        mem = clean_memory
        mem.record_execution(provider_id="test_p", success=True, duration_ms=100, capability="coding", language="python")
        mem.record_execution(provider_id="test_p", success=False, duration_ms=50, capability="debugging", language="java")
        record = mem.get_record("test_p")
        assert record.capabilities_used.get("coding", 0) == 1
        assert record.capabilities_used.get("debugging", 0) == 1
        assert record.languages.get("python", 0) == 1
        assert record.languages.get("java", 0) == 1

    def test_get_success_rate_no_data(self, clean_memory):
        assert clean_memory.get_success_rate("nonexistent") == 0.0

    def test_get_avg_duration_no_data(self, clean_memory):
        assert clean_memory.get_avg_duration("nonexistent") == 0.0

    def test_get_avg_cost_no_data(self, clean_memory):
        assert clean_memory.get_avg_cost("nonexistent") == 0.0

    def test_get_all_scores(self, clean_memory):
        mem = clean_memory
        mem.record_execution(provider_id="p1", success=True, duration_ms=100, capability="coding")
        mem.record_execution(provider_id="p2", success=True, duration_ms=100, capability="coding")
        scores = mem.get_all_scores()
        assert "p1" in scores
        assert "p2" in scores

    def test_singleton_exists(self):
        from core.providers.memory import provider_memory
        assert provider_memory is not None

    def test_persistence(self, clean_memory, temp_root):
        mem = clean_memory
        mem.record_execution(provider_id="test_p", success=True, duration_ms=100, capability="coding")
        mem._save()
        # Create new memory loading from same path
        from core.providers.memory import ProviderMemory
        mem2 = ProviderMemory()
        mem2._MEMORY_DIR = Path(temp_root) / "provider_memory"
        mem2._MEMORY_FILE = Path(temp_root) / "provider_memory" / "memory.json"
        mem2._load()
        record = mem2.get_record("test_p")
        assert record.total_executions == 1

    def test_record_execution_retry_and_repair(self, clean_memory):
        mem = clean_memory
        mem.record_execution(provider_id="test_p", success=True, duration_ms=100,
                             retries=2, repair_count=1, tokens_used=500, cost=0.05)
        record = mem.get_record("test_p")
        assert record.total_retries == 2
        assert record.total_repair_count == 1
        assert record.total_tokens_used == 500
        assert record.total_cost == 0.05

    def test_capabilities_used_counter(self, clean_memory):
        mem = clean_memory
        for cap in ["coding", "debugging", "coding", "testing", "coding"]:
            mem.record_execution(provider_id="test_p", success=True, duration_ms=100, capability=cap)
        record = mem.get_record("test_p")
        assert record.capabilities_used.get("coding", 0) == 3
        assert record.capabilities_used.get("debugging", 0) == 1
        assert record.capabilities_used.get("testing", 0) == 1

    def test_consecutive_failures_reset_on_success(self, clean_memory):
        mem = clean_memory
        for _ in range(2):
            mem.record_execution(provider_id="test_p", success=False, duration_ms=100)
        assert mem.get_record("test_p").consecutive_failures == 2
        mem.record_execution(provider_id="test_p", success=True, duration_ms=100)
        assert mem.get_record("test_p").consecutive_failures == 0


# ── ProviderBudgetManager ────────────────────────────────────────────────────


class TestProviderBudget:
    def test_record_spend(self, clean_budget):
        budget = clean_budget
        budget.record_spend(provider_id="test_p", cost=1.50, tokens=1000)
        record = budget.get_record("test_p")
        assert record.total_spent == 1.50
        assert record.total_tokens == 1000

    def test_record_spend_multiple(self, clean_budget):
        budget = clean_budget
        for cost in [1.0, 2.0, 0.5]:
            budget.record_spend(provider_id="test_p", cost=cost, tokens=500)
        record = budget.get_record("test_p")
        assert record.total_spent == 3.50
        assert record.total_tokens == 1500

    def test_set_limit(self, clean_budget):
        budget = clean_budget
        budget.set_limit(provider_id="test_p", daily=10.0, monthly=100.0, per_workflow=5.0)
        limits = budget.get_limits("test_p")
        assert limits["daily"] == 10.0
        assert limits["monthly"] == 100.0
        assert limits["per_workflow"] == 5.0

    def test_can_use_over_daily_limit(self, clean_budget):
        budget = clean_budget
        budget.set_limit(provider_id="test_p", daily=5.0)
        budget.record_spend(provider_id="test_p", cost=6.0, tokens=100)
        assert budget.can_use("test_p") is False

    def test_can_use_under_limit(self, clean_budget):
        budget = clean_budget
        budget.set_limit(provider_id="test_p", daily=10.0)
        budget.record_spend(provider_id="test_p", cost=5.0, tokens=100)
        assert budget.can_use("test_p") is True

    def test_can_use_with_no_record(self, clean_budget):
        assert clean_budget.can_use("unknown") is True

    def test_per_workflow_limit(self, clean_budget):
        budget = clean_budget
        budget.set_limit(provider_id="test_p", per_workflow=5.0)
        budget.record_spend(provider_id="test_p", cost=3.0, tokens=100, workflow_id="wf_001")
        assert budget.can_use("test_p", workflow_id="wf_001") is True
        budget.record_spend(provider_id="test_p", cost=3.0, tokens=100, workflow_id="wf_001")
        assert budget.can_use("test_p", workflow_id="wf_001") is False

    def test_set_limit_partial(self, clean_budget):
        budget = clean_budget
        budget.set_limit(provider_id="test_p", daily=10.0)
        limits = budget.get_limits("test_p")
        assert limits["daily"] == 10.0
        assert "monthly" not in limits
        assert "per_workflow" not in limits

    def test_singleton_exists(self):
        from core.providers.budget import provider_budget
        assert provider_budget is not None


# ── Router ───────────────────────────────────────────────────────────────────


class TestProviderRouter:
    def _make_provider(self, pid="provider", caps=None):
        from core.providers.base import (
            ExecutionProvider, ProviderCapabilities,
            ProviderHealth, ProviderHealthStatus, ExecutionResult,
        )

        class _P(ExecutionProvider):
            provider_id = pid
            name = pid.title()
            version = "1.0"
            priority = 50
            installed = True
            _enabled = True
            def capabilities(self): return ProviderCapabilities(capability_names=list(caps or ["coding"]))
            async def health(self): return ProviderHealth(status=ProviderHealthStatus.HEALTHY)
            async def execute(self, task, ctx=None): return ExecutionResult(success=True, output="ok")

        return _P()

    def test_select_by_capability(self, clean_router, clean_registry):
        p = self._make_provider("healthy")
        clean_registry.register(p, priority=50)
        import asyncio
        asyncio.run(p.health())
        selected = clean_router.select(capability="coding")
        assert selected is p

    def test_select_none_available(self, clean_router):
        assert clean_router.select(capability="nonexistent") is None

    def test_select_skips_disabled(self, clean_router, clean_registry):
        p = self._make_provider("healthy")
        clean_registry.register(p, priority=50)
        clean_registry.disable("healthy")
        assert clean_router.select(capability="coding") is None

    def test_select_skips_unhealthy(self, clean_router, clean_registry):
        from core.providers.base import ProviderHealth, ProviderHealthStatus
        p = self._make_provider("unhealthy")
        p.health = AsyncMock(return_value=ProviderHealth(status=ProviderHealthStatus.DOWN, error="unhealthy"))
        clean_registry.register(p, priority=50)
        import asyncio
        asyncio.run(p.health())
        assert clean_router.select(capability="coding") is None

    def test_select_skips_without_health_check(self, clean_router, clean_registry):
        """If health was never checked, cached_health status is UNKNOWN which is OK."""
        from core.providers.base import ProviderHealth, ProviderHealthStatus
        p = self._make_provider("never_checked")
        clean_registry.register(p, priority=50)
        # Don't call health() — cache stays at UNKNOWN
        selected = clean_router.select(capability="coding")
        assert selected is p  # UNKNOWN is OK for available()

    def test_select_with_fallback(self, clean_router, clean_registry):
        p = self._make_provider("healthy")
        clean_registry.register(p, priority=50)
        import asyncio
        asyncio.run(p.health())
        fallbacks = clean_router.select_with_fallback(capability="coding")
        assert isinstance(fallbacks, list)
        assert len(fallbacks) >= 1

    def test_select_with_fallback_excludes(self, clean_router, clean_registry):
        p = self._make_provider("healthy")
        clean_registry.register(p, priority=50)
        import asyncio
        asyncio.run(p.health())
        fallbacks = clean_router.select_with_fallback(capability="coding", exclude={"healthy"})
        assert len(fallbacks) == 0

    def test_select_skips_over_budget(self, clean_router, clean_registry, clean_budget):
        p = self._make_provider("budget_provider")
        clean_registry.register(p, priority=50)
        import asyncio
        asyncio.run(p.health())
        clean_budget.set_limit(provider_id="budget_provider", daily=5.0)
        clean_budget.record_spend(provider_id="budget_provider", cost=10.0, tokens=100)
        assert clean_router.select(capability="coding") is None

    def test_select_skips_poor_performance(self, clean_router, clean_registry, clean_memory):
        p = self._make_provider("poor_performer")
        clean_registry.register(p, priority=50)
        import asyncio
        asyncio.run(p.health())
        for _ in range(3):
            clean_memory.record_execution(provider_id="poor_performer", success=False, duration_ms=100)
        assert clean_router.select(capability="coding") is None

    def test_select_prefers_higher_priority(self, clean_router, clean_registry):
        from core.providers.base import (
            ExecutionProvider, ProviderCapabilities,
            ProviderHealth, ProviderHealthStatus, ExecutionResult,
        )

        class LowPrio(ExecutionProvider):
            provider_id = "low"
            name = "Low"
            version = "1.0"
            priority = 10
            installed = True
            _enabled = True
            def capabilities(self): return ProviderCapabilities(capability_names=["coding"])
            async def health(self): return ProviderHealth(status=ProviderHealthStatus.HEALTHY)
            async def execute(self, task, ctx=None): return ExecutionResult(success=True, output="ok")

        low = LowPrio()
        clean_registry.register(low, priority=10)
        high = self._make_provider("high")
        clean_registry.register(high, priority=90)
        import asyncio
        asyncio.run(high.health())
        asyncio.run(low.health())
        # 0.5 * (90/100) + 0.5 * 0.5 = 0.45 + 0.25 = 0.70 (high)
        # 0.5 * (10/100) + 0.5 * 0.5 = 0.05 + 0.25 = 0.30 (low)
        selected = clean_router.select(capability="coding")
        assert selected is high

    def test_singleton_exists(self):
        from core.providers.router import provider_router
        assert provider_router is not None


# ── CapabilityRegistry ───────────────────────────────────────────────────────


class TestCapabilityRegistry:
    def _make_provider(self, pid="mock", caps=None):
        from core.providers.base import (
            ExecutionProvider, ProviderCapabilities,
            ProviderHealth, ProviderHealthStatus, ExecutionResult,
        )

        class _P(ExecutionProvider):
            provider_id = pid
            name = pid.title()
            version = "1.0"
            priority = 50
            installed = True
            _enabled = True
            def capabilities(self): return ProviderCapabilities(capability_names=list(caps or ["coding"]))
            async def health(self): return ProviderHealth(status=ProviderHealthStatus.HEALTHY)
            async def execute(self, task, ctx=None): return ExecutionResult(success=True, output="ok")

        return _P()

    @pytest.fixture
    def cap_setup(self, clean_registry):
        from core.capability.registry import CapabilityRegistry
        cap = CapabilityRegistry(registry=clean_registry)
        return clean_registry, cap

    def test_get_providers(self, cap_setup):
        registry, cap = cap_setup
        p = self._make_provider("mock", caps=["coding"])
        registry.register(p, priority=50)
        providers = cap.get_providers("coding")
        assert len(providers) == 1

    def test_get_providers_unknown(self, cap_setup):
        _, cap = cap_setup
        assert cap.get_providers("nonexistent") == []

    def test_has_capability(self, cap_setup):
        registry, cap = cap_setup
        p = self._make_provider("mock", caps=["coding"])
        registry.register(p, priority=50)
        assert cap.has_capability("coding") is True

    def test_has_capability_unknown(self, cap_setup):
        _, cap = cap_setup
        assert cap.has_capability("nonexistent") is False

    def test_all_capabilities(self, cap_setup):
        registry, cap = cap_setup
        p = self._make_provider("mock", caps=["coding", "debugging"])
        registry.register(p, priority=50)
        caps = cap.all_capabilities()
        assert "coding" in caps
        assert "debugging" in caps

    def test_get_description(self, cap_setup):
        _, cap = cap_setup
        assert "code" in cap.get_description("coding").lower()
        assert cap.get_description("nonexistent") == ""

    def test_register_capability(self, cap_setup):
        _, cap = cap_setup
        cap.register_capability("new_cap", "A new capability")
        assert cap.get_description("new_cap") == "A new capability"

    def test_get_providers_for_task(self, cap_setup):
        registry, cap = cap_setup
        p = self._make_provider("mock", caps=["coding", "testing"])
        registry.register(p, priority=50)
        matches = cap.get_providers_for_task("need coding and testing help")
        assert "coding" in matches
        assert "testing" in matches

    def test_get_providers_for_task_no_match(self, cap_setup):
        _, cap = cap_setup
        matches = cap.get_providers_for_task("completely unknown task")
        assert matches == {}

    def test_singleton_exists(self):
        from core.capability.registry import capability_registry
        assert capability_registry is not None


# ── Bootstrap ────────────────────────────────────────────────────────────────


class TestProviderBootstrap:
    def test_bootstrap_registers_forge(self, clean_registry):
        from core.providers.bootstrap import register_internal_providers
        with patch("core.providers.bootstrap.provider_registry", clean_registry):
            register_internal_providers()
            p = clean_registry.get("forge")
            assert p is not None
            assert p.provider_id == "forge"

    def test_forge_priority_after_bootstrap(self, clean_registry):
        from core.providers.bootstrap import register_internal_providers
        with patch("core.providers.bootstrap.provider_registry", clean_registry):
            register_internal_providers()
            assert clean_registry.get_priority("forge") == 10

    def test_bootstrap_runs_idempotent(self, clean_registry):
        from core.capability.registry import CapabilityRegistry
        from core.providers.bootstrap import bootstrap_providers
        cap_reg = CapabilityRegistry(registry=clean_registry)
        with patch("core.providers.bootstrap.provider_registry", clean_registry), \
             patch("core.providers.bootstrap.capability_registry", cap_reg), \
             patch("core.providers.bootstrap.register_external_providers"):
            bootstrap_providers()
            count1 = len(clean_registry.list_providers())
            bootstrap_providers()
            count2 = len(clean_registry.list_providers())
            assert count1 == count2

    def test_external_providers_skip_when_not_installed(self, clean_registry):
        from core.providers.bootstrap import register_external_providers
        from core.providers.adapters.claude_code import ClaudeCodeProvider
        from core.providers.adapters.codex import CodexProvider
        with patch("core.providers.bootstrap.provider_registry", clean_registry), \
             patch.object(ClaudeCodeProvider, "installed", False), \
             patch.object(CodexProvider, "installed", False):
            register_external_providers()
            assert clean_registry.get("claude_code") is None
            assert clean_registry.get("codex") is None

    def test_external_providers_register_when_installed(self, clean_registry):
        from core.providers.bootstrap import register_external_providers
        with patch("core.providers.bootstrap.provider_registry", clean_registry), \
             patch("core.providers.adapters.claude_code.shutil.which", return_value="/usr/bin/claude"), \
             patch("core.providers.adapters.codex.shutil.which", return_value="/usr/bin/codex"):
            register_external_providers()
            assert clean_registry.get("claude_code") is not None
            assert clean_registry.get("codex") is not None

    def test_scan_provider_plugins_no_crash(self, clean_registry):
        from core.providers.bootstrap import scan_provider_plugins
        with patch("core.providers.bootstrap.provider_registry", clean_registry), \
             patch("core.providers.bootstrap.Path.home") as mock_home:
            mock_home.return_value = Path(tempfile.mkdtemp())
            scan_provider_plugins()

    def test_full_bootstrap_logs_count(self, clean_registry):
        from core.capability.registry import CapabilityRegistry
        from core.providers.bootstrap import bootstrap_providers
        cap_reg = CapabilityRegistry(registry=clean_registry)
        with patch("core.providers.bootstrap.provider_registry", clean_registry), \
             patch("core.providers.bootstrap.capability_registry", cap_reg), \
             patch("core.providers.bootstrap.register_external_providers"):
            bootstrap_providers()
            assert len(clean_registry.list_providers()) >= 1


# ── Provider Store ───────────────────────────────────────────────────────────


class TestProviderStore:
    def test_list_known_providers(self):
        from core.providers.store import list_known_providers
        providers = list_known_providers()
        assert "claude-code" in providers
        assert "codex" in providers
        assert len(providers) >= 9

    def test_get_known_provider(self):
        from core.providers.store import get_known_provider
        info = get_known_provider("claude-code")
        assert info is not None
        assert info["provider_id"] == "claude_code"

    def test_get_unknown_provider(self):
        from core.providers.store import get_known_provider
        assert get_known_provider("nonexistent") is None

    def test_known_providers_have_required_fields(self):
        from core.providers.store import list_known_providers
        for pid, info in list_known_providers().items():
            assert "provider_id" in info
            assert "name" in info
            assert "version" in info
            assert "capabilities" in info

    def test_generate_manifest(self):
        from core.providers.store import generate_manifest
        manifest = generate_manifest("codex")
        assert manifest is not None
        assert manifest["provider_id"] == "codex"
        assert manifest["name"] == "Codex CLI"

    def test_generate_manifest_unknown(self):
        from core.providers.store import generate_manifest
        assert generate_manifest("nonexistent") is None

    def test_write_manifest_creates_file(self):
        from core.providers.store import write_manifest
        manifest_dir = Path(tempfile.mkdtemp())
        try:
            with patch("core.providers.store._MANIFESTS_DIR", manifest_dir):
                result = write_manifest("codex")
                assert result is True
                manifest_file = manifest_dir / "codex.json"
                assert manifest_file.exists()
                data = json.loads(manifest_file.read_text(encoding="utf-8"))
                assert data["provider_id"] == "codex"
        finally:
            shutil.rmtree(manifest_dir, ignore_errors=True)

    def test_write_manifest_unknown(self):
        from core.providers.store import write_manifest
        manifest_dir = Path(tempfile.mkdtemp())
        try:
            with patch("core.providers.store._MANIFESTS_DIR", manifest_dir):
                assert write_manifest("nonexistent") is False
        finally:
            shutil.rmtree(manifest_dir, ignore_errors=True)

    def test_health_command_exists_unknown(self):
        from core.providers.store import health_command_exists
        assert health_command_exists("nonexistent") is False

    def test_health_command_exists_no_command(self):
        from core.providers.store import health_command_exists
        manifest_dir = Path(tempfile.mkdtemp())
        try:
            with patch("core.providers.store._MANIFESTS_DIR", manifest_dir):
                assert health_command_exists("telegram") is False  # empty health_command
        finally:
            shutil.rmtree(manifest_dir, ignore_errors=True)

    def test_health_command_exists_installed(self):
        from core.providers.store import health_command_exists
        assert health_command_exists("forge") is False  # not in known providers

    def test_is_installed_checks_registry(self):
        from core.providers.store import is_installed
        with patch("core.providers.registry.provider_registry.get") as mock_get:
            mock_get.return_value = MagicMock()
            assert is_installed("forge") is True

    def test_is_installed_checks_manifest(self):
        from core.providers.store import is_installed
        manifest_dir = Path(tempfile.mkdtemp())
        try:
            manifest_file = manifest_dir / "test_provider.json"
            manifest_file.write_text("{}", encoding="utf-8")
            with patch("core.providers.store._MANIFESTS_DIR", manifest_dir), \
                 patch("core.providers.store.provider_registry") as mock_reg:
                mock_reg.get.return_value = None
                result = is_installed("test_provider")
                assert result is True  # manifest exists
        finally:
            shutil.rmtree(manifest_dir, ignore_errors=True)


# ── Execution Tool Integration ───────────────────────────────────────────────


class TestProviderToolIntegration:
    def test_register_plugin_tool(self):
        from core.tools.execution import register_plugin_tool, unregister_plugin_tool, _PLUGIN_TOOL_HANDLERS

        async def handler(args):
            return {"success": True, "result": "handler called"}

        register_plugin_tool("test_tool", handler)
        try:
            assert "test_tool" in _PLUGIN_TOOL_HANDLERS
        finally:
            unregister_plugin_tool("test_tool")

    def test_unregister_plugin_tool(self):
        from core.tools.execution import register_plugin_tool, unregister_plugin_tool, _PLUGIN_TOOL_HANDLERS

        async def handler(args):
            return {"success": True}

        register_plugin_tool("test_tool", handler)
        unregister_plugin_tool("test_tool")
        assert "test_tool" not in _PLUGIN_TOOL_HANDLERS

    def test_register_twice_overwrites(self):
        from core.tools.execution import register_plugin_tool, unregister_plugin_tool, _PLUGIN_TOOL_HANDLERS

        async def handler1(args):
            return {"success": True}

        async def handler2(args):
            return {"success": False}

        register_plugin_tool("test_tool", handler1)
        register_plugin_tool("test_tool", handler2)
        try:
            assert "test_tool" in _PLUGIN_TOOL_HANDLERS
        finally:
            unregister_plugin_tool("test_tool")

    def test_unregister_unknown(self):
        from core.tools.execution import unregister_plugin_tool
        unregister_plugin_tool("nonexistent")


# ── End-to-End ───────────────────────────────────────────────────────────────


class TestProviderE2E:
    def _make_provider(self, pid="provider", caps=None):
        from core.providers.base import (
            ExecutionProvider, ProviderCapabilities,
            ProviderHealth, ProviderHealthStatus, ExecutionResult,
        )

        class _P(ExecutionProvider):
            provider_id = pid
            name = pid.title()
            version = "1.0"
            priority = 50
            installed = True
            _enabled = True
            def capabilities(self): return ProviderCapabilities(capability_names=list(caps or ["coding"]))
            async def health(self): return ProviderHealth(status=ProviderHealthStatus.HEALTHY)
            async def execute(self, task, ctx=None): return ExecutionResult(success=True, output="ok")

        return _P()

    def test_registry_to_router(self, clean_registry, clean_router):
        import asyncio
        p = self._make_provider("mock", caps=["coding"])
        clean_registry.register(p, priority=10)
        asyncio.run(p.health())
        selected = clean_router.select(capability="coding")
        assert selected is not None
        assert selected.provider_id == "mock"

    def test_registry_to_capability(self, clean_registry):
        from core.capability.registry import CapabilityRegistry
        cap = CapabilityRegistry(registry=clean_registry)
        p = self._make_provider("mock", caps=["coding", "debugging"])
        clean_registry.register(p, priority=10)
        assert cap.has_capability("coding") is True
        assert cap.has_capability("testing") is False
        caps = cap.all_capabilities()
        assert "coding" in caps
        assert "debugging" in caps

    def test_budget_blocks_router(self, clean_registry, clean_router, clean_budget):
        import asyncio
        p = self._make_provider("mock", caps=["coding"])
        clean_registry.register(p, priority=10)
        asyncio.run(p.health())
        clean_budget.set_limit(provider_id="mock", daily=5.0)
        clean_budget.record_spend(provider_id="mock", cost=10.0, tokens=100)
        assert clean_router.select(capability="coding") is None

    def test_memory_blocks_router(self, clean_registry, clean_router, clean_memory):
        import asyncio
        p = self._make_provider("mock", caps=["coding"])
        clean_registry.register(p, priority=10)
        asyncio.run(p.health())
        for _ in range(3):
            clean_memory.record_execution(provider_id="mock", success=False, duration_ms=100)
        assert clean_router.select(capability="coding") is None

    def test_full_pipeline_selects_best(self, clean_registry, clean_router, clean_memory):
        import asyncio
        from core.capability.registry import CapabilityRegistry
        cap = CapabilityRegistry(registry=clean_registry)

        p1 = self._make_provider("high_prio", caps=["coding"])
        p2 = self._make_provider("low_prio", caps=["coding"])
        clean_registry.register(p1, priority=90)
        clean_registry.register(p2, priority=10)
        asyncio.run(p1.health())
        asyncio.run(p2.health())

        providers = cap.get_providers("coding")
        assert len(providers) == 2

        selected = clean_router.select(capability="coding")
        assert selected is not None
        # High priority gets higher score
        assert selected.provider_id == "high_prio"
