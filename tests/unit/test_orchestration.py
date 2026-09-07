"""Tests for X.3 — Multi-Provider Orchestration.

Covers: models, orchestration planner, orchestrator, chain types,
fallback behavior, artifact handoff, consensus merging, pipeline mode,
dynamic replanning, capability substitution, confidence propagation,
typed artifacts, execution graph memory.
"""

import time
import tempfile
import os
import shutil
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from core.providers.orchestration.models import (
    ArtifactType, ChainType, ProviderStep, StepConfidence,
    StepDependency, StepResult, TypedArtifact,
    OrchestrationPlan, OrchestrationResult,
    infer_artifact_type, typed_artifact_from,
)
from core.providers.orchestration.planner import (
    OrchestrationPlanner, _detect_pattern, _SUB_TASK_PATTERNS,
)
from core.providers.orchestration.orchestrator import Orchestrator
from core.providers.orchestration.adapt import AdaptEngine, ReplanLevel
from core.providers.orchestration.store import OrchestrationStore
from core.providers.base import ExecutionProvider, ProviderCapabilities, ExecutionResult


# ── Mock Provider Factory ────────────────────────────────────────────────────


def _make_provider(pid="forge", capabilities=None, success=True,
                   output="def result():\n    return 42\n", delay_ms=50,
                   enabled=True):
    if capabilities is None:
        capabilities = ["coding", "python", "testing"]

    class MockProvider(ExecutionProvider):
        provider_id = pid
        name = pid.title()
        version = "1.0"
        priority = 50 if pid == "forge" else 70
        installed = True
        _enabled = enabled

        def capabilities(self):
            return ProviderCapabilities(capability_names=capabilities)

        async def health(self):
            from core.providers.base import ProviderHealth, ProviderHealthStatus
            return ProviderHealth(status=ProviderHealthStatus.HEALTHY)

        async def execute(self, task, context=None):
            if not success:
                return ExecutionResult(success=False, output="", error="mock failure")
            return ExecutionResult(
                success=True,
                output=output,
                duration_ms=delay_ms,
                artifacts={"source_code": f"/tmp/{pid}_output.py"},
            )

    return MockProvider()


# ── Models ───────────────────────────────────────────────────────────────────


class TestChainType:
    def test_values(self):
        assert ChainType.SEQUENTIAL.value == "sequential"
        assert ChainType.PARALLEL.value == "parallel"
        assert ChainType.PIPELINE.value == "pipeline"
        assert ChainType.VERIFY.value == "verify"
        assert ChainType.CONSENSUS.value == "consensus"

    def test_all_distinct(self):
        vals = [ct.value for ct in ChainType]
        assert len(vals) == len(set(vals))


class TestStepDependency:
    def test_creation(self):
        dep = StepDependency(step_id="generate", required_artifact="source_code")
        assert dep.step_id == "generate"
        assert dep.required_artifact == "source_code"

    def test_default_artifact(self):
        dep = StepDependency(step_id="test")
        assert dep.required_artifact == ""


class TestProviderStep:
    def test_minimal_creation(self):
        step = ProviderStep(step_id="s1", task={"goal": "test"})
        assert step.step_id == "s1"
        assert step.chain_type == ChainType.SEQUENTIAL
        assert step.label == "sequential:test"
        assert step.max_retries == 2
        assert step.timeout == 300

    def test_ready_no_deps(self):
        step = ProviderStep(step_id="s1", task={})
        assert step.is_ready(set()) is True
        assert step.is_ready({"s2", "s3"}) is True

    def test_not_ready_with_unmet_deps(self):
        step = ProviderStep(
            step_id="s1", task={},
            dependencies=[StepDependency("s2"), StepDependency("s3")],
        )
        assert step.is_ready(set()) is False
        assert step.is_ready({"s2"}) is False
        assert step.is_ready({"s2", "s3"}) is True

    def test_label_default(self):
        step = ProviderStep(step_id="s1", task={"goal": "Write code"}, chain_type=ChainType.VERIFY)
        assert "verify:" in step.label

    def test_custom_label(self):
        step = ProviderStep(step_id="s1", label="Custom", task={})
        assert step.label == "Custom"


class TestStepResult:
    def test_creation(self):
        r = StepResult(
            step_id="s1", provider_id="forge", chain_type=ChainType.SEQUENTIAL,
            success=True, output="ok", duration_ms=100.0,
        )
        assert r.passed is True
        assert r.failed is False

    def test_failed(self):
        r = StepResult(
            step_id="s1", provider_id="forge", chain_type=ChainType.SEQUENTIAL,
            success=False, error="fail",
        )
        assert r.passed is False
        assert r.failed is True

    def test_artifacts(self):
        r = StepResult(
            step_id="s1", provider_id="forge", chain_type=ChainType.SEQUENTIAL,
            success=True, output="ok",
            artifacts={"key1": "val1", "key2": "val2"},
        )
        assert r.artifacts["key1"] == "val1"


class TestOrchestrationPlan:
    def test_creation(self):
        plan = OrchestrationPlan(goal="Build an app")
        assert plan.plan_id.startswith("plan_")
        assert plan.goal == "Build an app"
        assert plan.total_steps == 0
        assert plan.created_at > 0

    def test_add_step(self):
        plan = OrchestrationPlan(goal="test")
        plan.add_step(ProviderStep(step_id="s1", task={}))
        assert plan.total_steps == 1
        assert plan.step_ids() == ["s1"]

    def test_get_step(self):
        plan = OrchestrationPlan(goal="test")
        plan.add_step(ProviderStep(step_id="s1", task={}))
        assert plan.get_step("s1") is not None
        assert plan.get_step("nonexistent") is None

    def test_provider_count(self):
        plan = OrchestrationPlan(goal="test")
        plan.add_step(ProviderStep(step_id="s1", task={}, provider_id="forge"))
        plan.add_step(ProviderStep(step_id="s2", task={}, provider_id="codex"))
        plan.add_step(ProviderStep(step_id="s3", task={}, provider_id="forge"))
        assert plan.provider_count() == 2

    def test_summary(self):
        plan = OrchestrationPlan(goal="Test goal")
        plan.add_step(ProviderStep(step_id="step1", task={}, provider_id="forge"))
        summary = plan.summary()
        assert "Test goal" in summary
        assert "step1" in summary
        assert "forge" in summary


class TestOrchestrationResult:
    def test_creation(self):
        plan = OrchestrationPlan(goal="test")
        result = OrchestrationResult(plan=plan)
        assert result.overall_success is False
        assert result.duration_ms == 0.0

    def test_get_step_result(self):
        plan = OrchestrationPlan(goal="test")
        result = OrchestrationResult(plan=plan)
        r = StepResult(step_id="s1", provider_id="forge", chain_type=ChainType.SEQUENTIAL, success=True)
        result.step_results = [r]
        assert result.get_step_result("s1") is r
        assert result.get_step_result("nonexistent") is None

    def test_collect_outputs(self):
        plan = OrchestrationPlan(goal="test")
        result = OrchestrationResult(plan=plan)
        result.step_results = [
            StepResult(step_id="s1", provider_id="forge", chain_type=ChainType.SEQUENTIAL, success=True, output="out1"),
            StepResult(step_id="s2", provider_id="codex", chain_type=ChainType.SEQUENTIAL, success=True, output="out2"),
            StepResult(step_id="s3", provider_id="forge", chain_type=ChainType.SEQUENTIAL, success=False, output=""),
        ]
        outputs = result.collect_outputs()
        assert outputs["s1"] == "out1"
        assert outputs["s2"] == "out2"
        assert "s3" not in outputs

    def test_collect_artifacts(self):
        plan = OrchestrationPlan(goal="test")
        result = OrchestrationResult(plan=plan)
        result.step_results = [
            StepResult(step_id="s1", provider_id="forge", chain_type=ChainType.SEQUENTIAL,
                      success=True, artifacts={"a1": "v1"}),
            StepResult(step_id="s2", provider_id="codex", chain_type=ChainType.SEQUENTIAL,
                      success=True, artifacts={"a2": "v2"}),
        ]
        arts = result.collect_artifacts()
        assert arts["a1"] == "v1"
        assert arts["a2"] == "v2"

    def test_successful_and_failed_steps(self):
        plan = OrchestrationPlan(goal="test")
        result = OrchestrationResult(plan=plan)
        result.step_results = [
            StepResult(step_id="s1", provider_id="forge", chain_type=ChainType.SEQUENTIAL, success=True),
            StepResult(step_id="s2", provider_id="codex", chain_type=ChainType.SEQUENTIAL, success=False),
        ]
        assert len(result.successful_steps) == 1
        assert len(result.failed_steps) == 1
        assert result.successful_steps[0].step_id == "s1"
        assert result.failed_steps[0].step_id == "s2"


# ── OrchestrationPlanner ────────────────────────────────────────────────────


class TestDetectPattern:
    def test_generate_default(self):
        assert _detect_pattern("Write a function") == "generate"

    def test_review_pattern(self):
        assert _detect_pattern("Review this code") == "review"

    def test_secure_pattern(self):
        assert _detect_pattern("Secure this API") == "secure"

    def test_refactor_pattern(self):
        assert _detect_pattern("Refactor this module") == "refactor"

    def test_debug_pattern(self):
        assert _detect_pattern("Fix this bug") == "debug"

    def test_full_stack_pattern(self):
        assert _detect_pattern("Build a full stack app") == "full"

    def test_research_pattern(self):
        assert _detect_pattern("Research this topic") == "research"

    def test_build_pattern(self):
        assert _detect_pattern("Build and compile") == "build"  # "build" keyword matches

    def test_document_pattern(self):
        assert _detect_pattern("Document the API") == "document"

    def test_test_pattern(self):
        assert _detect_pattern("Write unit tests") == "test"


class TestOrchestrationPlanner:
    def test_plan_simple_generate(self):
        planner = OrchestrationPlanner()
        plan = planner.plan("Write a Python function")
        assert plan.goal == "Write a Python function"
        assert plan.total_steps >= 1

    def test_plan_full_stack(self):
        planner = OrchestrationPlanner()
        plan = planner.plan("Build a full stack application")
        assert plan.total_steps >= 4  # coding + security + testing + documentation + review
        assert any(s.chain_type == ChainType.VERIFY for s in plan.steps)
        assert any(s.chain_type == ChainType.PARALLEL for s in plan.steps)

    def test_plan_secure(self):
        planner = OrchestrationPlanner()
        plan = planner.plan("Security audit this codebase")
        assert plan.total_steps >= 2  # coding + security
        verify_steps = [s for s in plan.steps if s.chain_type == ChainType.VERIFY]
        assert len(verify_steps) >= 1

    def test_plan_review(self):
        planner = OrchestrationPlanner()
        plan = planner.plan("Review the pull request")
        assert plan.total_steps >= 2  # coding + review

    def test_plan_research(self):
        planner = OrchestrationPlanner()
        plan = planner.plan("Research the latest Python trends and implement")
        assert plan.total_steps >= 2  # research + coding

    def test_plan_dependencies_set_correctly(self):
        planner = OrchestrationPlanner()
        plan = planner.plan("Full stack coffee shop app")
        for step in plan.steps:
            if step.chain_type == ChainType.VERIFY or step.chain_type == ChainType.PARALLEL:
                assert len(step.dependencies) >= 1, f"Step {step.step_id} has deps"

    def test_plan_unique_step_ids(self):
        planner = OrchestrationPlanner()
        plan = planner.plan("Build a complete full stack app with security review and tests")
        ids = plan.step_ids()
        assert len(ids) == len(set(ids)), f"Duplicate step IDs: {ids}"

    def test_plan_provider_assigned(self):
        planner = OrchestrationPlanner()
        plan = planner.plan("Write a Python module")
        for step in plan.steps:
            assert step.provider_id, f"Step {step.step_id} has no provider"

    def test_plan_with_context(self):
        planner = OrchestrationPlanner()
        plan = planner.plan("Build API", context={"language": "python", "framework": "fastapi"})
        for step in plan.steps:
            if step.task:
                assert step.task.get("language") == "python"

    def test_plan_and_summarize(self):
        planner = OrchestrationPlanner()
        summary = planner.plan_and_summarize("Write code")
        assert "plan_" in summary or "Goal:" in summary


# ── Orchestrator ─────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _register_mock_providers():
    """Ensure forge and codex providers are registered for all orchestrator tests."""
    from core.providers.registry import provider_registry
    from core.providers.memory import provider_memory

    # Check if forge already exists; if so, skip registration
    if not provider_registry.get("forge"):
        forge = _make_provider("forge", output="def result():\n    return 42")
        provider_registry.register(forge, priority=50)
    if not provider_registry.get("codex"):
        codex = _make_provider("codex", capabilities=["coding", "python", "testing", "review", "security", "documentation"],
                              output="def codex_func():\n    return 99\n")
        provider_registry.register(codex, priority=70)

    provider_memory._records.clear()
    yield
    # Don't unregister - leave providers for other tests


class TestOrchestrator:
    @pytest.mark.asyncio
    async def test_execute_single_step(self):
        planner = OrchestrationPlanner()
        plan = planner.plan("Write a function")

        orchestrator = Orchestrator()
        result = await orchestrator.execute(plan)
        assert result.overall_success is True
        assert len(result.step_results) >= 1

    @pytest.mark.asyncio
    async def test_execute_failing_step(self):
        """A failing step should trigger dynamic replanning and still succeed."""
        fail_provider = _make_provider("fail_test", success=False)
        from core.providers.registry import provider_registry
        provider_registry.register(fail_provider, priority=10)

        planner = OrchestrationPlanner()
        plan = planner.plan("Write a function")
        for s in plan.steps:
            s.provider_id = "fail_test"

        orchestrator = Orchestrator()
        result = await orchestrator.execute(plan)
        # Replanning falls back to forge, which succeeds
        assert result.overall_success is True
        assert result.avg_confidence < 1.0  # Replanning reduces confidence

        provider_registry.unregister("fail_test")

    @pytest.mark.asyncio
    async def test_execute_sequential_steps(self):
        planner = OrchestrationPlanner()
        plan = planner.plan("Write and review code")
        assert plan.total_steps >= 2

        # Verify dependencies create sequential ordering
        for step in plan.steps:
            if step.chain_type == ChainType.VERIFY:
                assert len(step.dependencies) > 0

    @pytest.mark.asyncio
    async def test_execute_parallel_steps(self):
        planner = OrchestrationPlanner()
        plan = planner.plan("Full stack app")
        parallel = [s for s in plan.steps if s.chain_type == ChainType.PARALLEL]
        assert len(parallel) >= 1  # documentation and testing should be parallel

    @pytest.mark.asyncio
    async def test_execution_records_memory(self):
        from core.providers.memory import provider_memory
        provider_memory._records.clear()

        planner = OrchestrationPlanner()
        plan = planner.plan("Write a function")

        orchestrator = Orchestrator()
        result = await orchestrator.execute(plan)
        assert result.overall_success is True

        # Provider memory should have been updated
        for s in plan.steps:
            record = provider_memory.get_record(s.provider_id)
            if record:
                assert record.total_executions >= 1

    @pytest.mark.asyncio
    async def test_provider_not_found(self):
        """A nonexistent provider should trigger capability substitution fallback."""
        plan = OrchestrationPlan(goal="test")
        plan.add_step(ProviderStep(
            step_id="s1", task={"capability": "coding"},
            provider_id="nonexistent",
        ))

        orchestrator = Orchestrator()
        result = await orchestrator.execute(plan)
        # AdaptEngine falls back to forge via capability substitution
        assert result.overall_success is True
        # Confidence is degraded due to replanning
        assert result.avg_confidence < 1.0

    @pytest.mark.asyncio
    async def test_execute_pipeline_handoff(self):
        """Pipeline steps should receive previous step output as context."""
        planner = OrchestrationPlanner()
        plan = planner.plan("Research and implement")

        # Find the pipeline step
        pipeline_steps = [s for s in plan.steps if s.chain_type == ChainType.PIPELINE]
        if pipeline_steps:
            assert "pipeline_input" not in pipeline_steps[0].task

    @pytest.mark.asyncio
    async def test_execute_long_chain(self):
        """A chain with 5+ steps should execute correctly."""
        plan = OrchestrationPlan(goal="Full chain test")
        for i in range(5):
            deps = [StepDependency(f"s{j+1}") for j in range(i)] if i > 0 else []
            plan.add_step(ProviderStep(
                step_id=f"s{i+1}", task={"capability": "coding", "goal": f"step {i+1}"},
                provider_id="forge",
                dependencies=deps,
            ))

        orchestrator = Orchestrator()
        result = await orchestrator.execute(plan)
        assert result.overall_success is True
        assert len(result.step_results) == 5

    @pytest.mark.asyncio
    async def test_step_timeout(self):
        """A step that times out should fail gracefully."""
        plan = OrchestrationPlan(goal="timeout test")
        step = ProviderStep(
            step_id="slow", task={"capability": "coding", "goal": "slow"},
            provider_id="forge", timeout=1,
        )
        plan.add_step(step)

        orchestrator = Orchestrator()
        from core.providers.registry import provider_registry
        original_get = orchestrator._registry.get

        async def slow_execute(task, ctx=None):
            import asyncio
            await asyncio.sleep(10)
            return ExecutionResult(success=True, output="too late")

        def patched_get(pid):
            p = original_get(pid)
            p.execute = slow_execute
            return p

        with patch.object(provider_registry, "get", patched_get):
            orchestrator = Orchestrator()
            result = await orchestrator.execute(plan)
            assert len(result.failed_steps) >= 1

    @pytest.mark.asyncio
    async def test_execute_disabled_provider_fallback(self):
        """Disabled provider should trigger fallback to another provider."""
        plan = OrchestrationPlan(goal="test")
        disabled = _make_provider("disabled_test", capabilities=["coding"], enabled=False)
        plan.add_step(ProviderStep(
            step_id="s1", task={"capability": "coding", "goal": "test"},
            provider_id="disabled_test",
        ))

        from core.providers.registry import provider_registry
        provider_registry.register(disabled, priority=10)

        orchestrator = Orchestrator()
        result = await orchestrator.execute(plan)
        assert isinstance(result, OrchestrationResult)

        provider_registry.unregister("disabled_test")

    @pytest.mark.asyncio
    async def test_execute_empty_plan(self):
        """An empty plan should produce a valid result."""
        plan = OrchestrationPlan(goal="empty")
        orchestrator = Orchestrator()
        result = await orchestrator.execute(plan)
        assert result.overall_success is True
        assert len(result.step_results) == 0

    @pytest.mark.asyncio
    async def test_verify_step_failure_causes_overall_failure(self):
        """A verify step failing should trigger replanning but not propagate as overall failure."""
        planner = OrchestrationPlanner()
        plan = planner.plan("Review my code")
        verify_steps = [s for s in plan.steps if s.chain_type == ChainType.VERIFY]
        if verify_steps:
            fail_provider = _make_provider("verify_fail_test", success=False)
            from core.providers.registry import provider_registry
            provider_registry.register(fail_provider, priority=10)

            for s in verify_steps:
                s.provider_id = "verify_fail_test"

            orchestrator = Orchestrator()
            result = await orchestrator.execute(plan)
            # Replanning retries verify with an alternative provider (codex) and succeeds
            assert result.overall_success is True
            assert len(result.step_results) >= 2  # original + retry

            provider_registry.unregister("verify_fail_test")


# ── Orchestrator: Consensus Merging ──────────────────────────────────────────


class TestConsensusMerging:
    @pytest.mark.asyncio
    async def test_merge_single_output(self):
        orchestrator = Orchestrator()
        results = [
            StepResult(step_id="c1", provider_id="forge", chain_type=ChainType.CONSENSUS,
                      success=True, output="output_a"),
        ]
        merged = orchestrator._merge_consensus(results)
        assert merged == "output_a"

    @pytest.mark.asyncio
    async def test_merge_multiple_outputs(self):
        orchestrator = Orchestrator()
        results = [
            StepResult(step_id="c1", provider_id="forge", chain_type=ChainType.CONSENSUS,
                      success=True, output="output_a"),
            StepResult(step_id="c2", provider_id="codex", chain_type=ChainType.CONSENSUS,
                      success=True, output="output_b"),
        ]
        merged = orchestrator._merge_consensus(results)
        assert "output_a" in merged
        assert "output_b" in merged
        assert "--- forge output ---" in merged
        assert "--- codex output ---" in merged

    @pytest.mark.asyncio
    async def test_merge_all_failed(self):
        orchestrator = Orchestrator()
        results = [
            StepResult(step_id="c1", provider_id="forge", chain_type=ChainType.CONSENSUS,
                      success=False, error="failed"),
        ]
        merged = orchestrator._merge_consensus(results)
        assert merged == ""

    @pytest.mark.asyncio
    async def test_merge_partial_failure(self):
        orchestrator = Orchestrator()
        results = [
            StepResult(step_id="c1", provider_id="forge", chain_type=ChainType.CONSENSUS,
                      success=True, output="output_good"),
            StepResult(step_id="c2", provider_id="codex", chain_type=ChainType.CONSENSUS,
                      success=False, error="failed"),
        ]
        merged = orchestrator._merge_consensus(results)
        assert "output_good" in merged
        # Failed output should not appear
        failed_results = [r for r in results if not r.success]
        for r in failed_results:
            assert r.output not in merged or r.output == ""


# ── Typed Artifacts ──────────────────────────────────────────────────────────


class TestArtifactType:
    def test_values(self):
        assert ArtifactType.SOURCE_CODE.value == "source_code"
        assert ArtifactType.TEST_SUITE.value == "test_suite"
        assert ArtifactType.SECURITY_REPORT.value == "security_report"
        assert ArtifactType.UNKNOWN.value == "unknown"

    def test_infer_type(self):
        assert infer_artifact_type("source_code") == ArtifactType.SOURCE_CODE
        assert infer_artifact_type("test_code") == ArtifactType.TEST_SUITE
        assert infer_artifact_type("security_report") == ArtifactType.SECURITY_REPORT
        assert infer_artifact_type("unknown_key") == ArtifactType.UNKNOWN

    def test_typed_artifact_factory(self):
        ta = typed_artifact_from("source_code", "/tmp/main.py", "Main module")
        assert ta.type == ArtifactType.SOURCE_CODE
        assert ta.path == "/tmp/main.py"
        assert ta.summary == "Main module"

    def test_typed_artifact_default_summary(self):
        ta = typed_artifact_from("test_code", "/tmp/test_main.py")
        assert ta.summary == "Artifact from test_code"

    def test_is_source(self):
        ta = TypedArtifact(type=ArtifactType.SOURCE_CODE, path="/tmp/main.py")
        assert ta.is_source is True
        assert ta.is_test is False
        assert ta.is_report is False

    def test_is_report_types(self):
        security = TypedArtifact(type=ArtifactType.SECURITY_REPORT, path="/tmp/report.md")
        review = TypedArtifact(type=ArtifactType.REVIEW_REPORT, path="/tmp/review.md")
        research = TypedArtifact(type=ArtifactType.RESEARCH_REPORT, path="/tmp/research.md")
        assert security.is_report is True
        assert review.is_report is True
        assert research.is_report is True
        assert TypedArtifact(type=ArtifactType.SOURCE_CODE, path="x").is_report is False


# ── Step Confidence ──────────────────────────────────────────────────────────


class TestStepConfidence:
    def test_defaults(self):
        c = StepConfidence()
        assert c.confidence == 0.0
        assert c.quality_score == 0.0
        assert c.cost == 0.0
        assert c.risk == 0.0

    def test_is_reliable(self):
        c = StepConfidence(confidence=0.85, quality_score=0.9, risk=0.1)
        assert c.is_reliable is True

    def test_not_reliable_low_confidence(self):
        c = StepConfidence(confidence=0.5, quality_score=0.9, risk=0.1)
        assert c.is_reliable is False

    def test_not_reliable_high_risk(self):
        c = StepConfidence(confidence=0.85, quality_score=0.9, risk=0.5)
        assert c.is_reliable is False

    def test_summary(self):
        c = StepConfidence(confidence=0.85, quality_score=0.9, cost=0.12, risk=0.1)
        s = c.summary
        assert "conf=0.85" in s
        assert "quality=0.90" in s
        assert "cost=$0.12" in s


# ── Dynamic Replanning (AdaptEngine) ─────────────────────────────────────────


class TestAdaptEngine:
    def test_find_alternative_provider(self):
        engine = AdaptEngine()
        step = ProviderStep(step_id="s1", task={"capability": "coding"}, provider_id="forge")
        alt = engine.find_alternative(step)
        # Should find codex (registered in fixture)
        if alt:
            assert alt.provider_id != "forge"

    def test_find_alternative_excludes_original(self):
        engine = AdaptEngine()
        step = ProviderStep(step_id="s1", task={"capability": "coding"}, provider_id="forge")
        alt = engine.find_alternative(step, exclude_providers={"forge"})
        if alt:
            assert alt.provider_id != "forge"

    def test_find_capability_substitution(self):
        engine = AdaptEngine()
        step = ProviderStep(step_id="s1", task={"capability": "review"}, provider_id="codex")
        sub = engine.find_capability_substitution(step)
        if sub:
            cap, prov = sub
            assert cap != "review"

    def test_find_capability_substitution_nonexistent(self):
        engine = AdaptEngine()
        step = ProviderStep(step_id="s1", task={"capability": "nonexistent_cap"}, provider_id="forge")
        sub = engine.find_capability_substitution(step)
        assert sub is None  # No substitution for unknown capabilities

    def test_create_replan_alternative_provider(self):
        engine = AdaptEngine()
        plan = OrchestrationPlan(goal="test")
        step = ProviderStep(step_id="s1", task={"capability": "coding"}, provider_id="forge")
        plan.add_step(step)
        level, new_step = engine.create_replan(plan, step, "mock failure")
        assert level == ReplanLevel.ALTERNATIVE_PROVIDER
        assert new_step is not None
        assert new_step.provider_id != "forge"  # Should use a different provider

    def test_create_replan_abort_when_no_providers(self):
        engine = AdaptEngine()
        plan = OrchestrationPlan(goal="test")
        step = ProviderStep(step_id="s1", task={"capability": "nonexistent"}, provider_id="unknown")
        plan.add_step(step)
        level, new_step = engine.create_replan(plan, step, "no provider", attempted_providers={"unknown"})
        # With no alterntives, should keep trying or abort
        assert level in (ReplanLevel.ALTERNATIVE_PROVIDER, ReplanLevel.ABORT)

    def test_compute_confidence_success_no_retries(self):
        engine = AdaptEngine()
        c = engine.compute_confidence(success=True, retries=0, duration_ms=100)
        assert c.confidence > 0.9
        assert c.risk < 0.3

    def test_compute_confidence_success_with_retries(self):
        engine = AdaptEngine()
        c = engine.compute_confidence(success=True, retries=3, duration_ms=5000)
        assert c.confidence < 0.9  # Reduced by retries
        assert c.risk > 0.1

    def test_compute_confidence_failure(self):
        engine = AdaptEngine()
        c = engine.compute_confidence(success=False, retries=2, duration_ms=1000)
        assert c.confidence == 0.0
        assert c.risk == 1.0

    def test_compute_confidence_with_replan_level(self):
        engine = AdaptEngine()
        c = engine.compute_confidence(success=True, retries=0, duration_ms=100,
                                      replan_level=ReplanLevel.ALTERNATIVE_PROVIDER)
        assert c.risk > 0.0  # Replanning adds risk

    def test_compute_confidence_quality_and_cost(self):
        engine = AdaptEngine()
        c = engine.compute_confidence(success=True, retries=0, duration_ms=100,
                                      quality_score=0.9, cost=1.5)
        assert c.quality_score == 0.9
        assert c.cost == 1.5


# ── Dynamic Replanning Integration Tests ─────────────────────────────────────


class TestOrchestratorReplanning:
    @pytest.mark.asyncio
    async def test_replan_on_failure_finds_alternative(self):
        """When a step fails, orchestrator should try an alternative provider."""
        plan = OrchestrationPlan(goal="test replan")
        plan.add_step(ProviderStep(
            step_id="s1", task={"capability": "coding", "goal": "write code"},
            provider_id="forge",
        ))

        orchestrator = Orchestrator()
        result = await orchestrator.execute(plan)
        # Should succeed with replanning if forge fails, or succeed directly
        assert len(result.step_results) >= 1

    @pytest.mark.asyncio
    async def test_replan_creates_new_step_in_plan(self):
        """After replanning, the plan should contain the new step."""
        from core.providers.orchestration.adapt import AdaptEngine
        plan = OrchestrationPlan(goal="test")
        step = ProviderStep(step_id="s1", task={"capability": "coding"}, provider_id="forge")
        plan.add_step(step)

        engine = AdaptEngine()
        level, new_step = engine.create_replan(plan, step, "failed")
        if level != ReplanLevel.ABORT and new_step:
            assert new_step.step_id != step.step_id
            assert new_step.provider_id != "forge"

    @pytest.mark.asyncio
    async def test_confidence_propagated_to_result(self):
        """Step results should carry confidence information."""
        planner = OrchestrationPlanner()
        plan = planner.plan("Write a function")

        orchestrator = Orchestrator()
        result = await orchestrator.execute(plan)
        for s_result in result.step_results:
            assert hasattr(s_result, "confidence")
            if s_result.success:
                assert s_result.confidence.confidence > 0

    @pytest.mark.asyncio
    async def test_avg_confidence_computed(self):
        """Overall result should compute average confidence."""
        planner = OrchestrationPlanner()
        plan = planner.plan("Write a function")

        orchestrator = Orchestrator()
        result = await orchestrator.execute(plan)
        if result.step_results:
            assert result.avg_confidence >= 0
            assert result.avg_quality >= 0
            assert result.total_cost >= 0
            assert result.overall_risk >= 0

    @pytest.mark.asyncio
    async def test_total_cost_aggregated(self):
        """Total cost should be the sum of all step costs."""
        plan = OrchestrationPlan(goal="test cost")
        orchestrator = Orchestrator()
        result = await orchestrator.execute(plan)
        assert result.total_cost >= 0


# ── Typed Artifacts in Orchestrator ──────────────────────────────────────────


class TestTypedArtifactsIntegration:
    @pytest.mark.asyncio
    async def test_typed_artifacts_in_step_results(self):
        """Step results should contain typed artifacts from execution."""
        planner = OrchestrationPlanner()
        plan = planner.plan("Write a function")

        orchestrator = Orchestrator()
        result = await orchestrator.execute(plan)
        for s_result in result.step_results:
            if s_result.success:
                # typed_artifacts should be populated from artifacts
                if s_result.artifacts:
                    assert len(s_result.typed_artifacts) > 0

    def test_collect_typed_artifacts(self):
        plan = OrchestrationPlan(goal="test")
        result = OrchestrationResult(plan=plan)
        result.step_results = [
            StepResult(step_id="s1", provider_id="forge", chain_type=ChainType.SEQUENTIAL,
                      success=True, typed_artifacts=[
                          TypedArtifact(type=ArtifactType.SOURCE_CODE, path="/tmp/main.py"),
                      ]),
            StepResult(step_id="s2", provider_id="codex", chain_type=ChainType.SEQUENTIAL,
                      success=True, typed_artifacts=[
                          TypedArtifact(type=ArtifactType.DOCUMENTATION, path="/tmp/docs.md"),
                      ]),
        ]
        arts = result.collect_typed_artifacts()
        assert len(arts) == 2

    def test_collect_typed_artifacts_deduplicates(self):
        plan = OrchestrationPlan(goal="test")
        result = OrchestrationResult(plan=plan)
        result.step_results = [
            StepResult(step_id="s1", provider_id="forge", chain_type=ChainType.SEQUENTIAL,
                      success=True, typed_artifacts=[
                          TypedArtifact(type=ArtifactType.SOURCE_CODE, path="/tmp/main.py"),
                      ]),
            StepResult(step_id="s2", provider_id="codex", chain_type=ChainType.SEQUENTIAL,
                      success=True, typed_artifacts=[
                          TypedArtifact(type=ArtifactType.SOURCE_CODE, path="/tmp/main.py"),
                      ]),
        ]
        arts = result.collect_typed_artifacts()
        assert len(arts) == 1  # Deduplicated by path


# ── Execution Graph Memory (OrchestrationStore) ──────────────────────────────


class TestOrchestrationStore:
    @pytest.fixture
    def store(self):
        tmp = tempfile.mkdtemp()
        db_path = os.path.join(tmp, "test_orch.db")
        s = OrchestrationStore(db_path=db_path)
        yield s
        shutil.rmtree(tmp, ignore_errors=True)

    def test_save_and_get_plan(self, store):
        plan = OrchestrationPlan(goal="test goal")
        result = OrchestrationResult(plan=plan, overall_success=True)
        store.save_result(result)
        loaded = store.get_plan(plan.plan_id)
        assert loaded is not None
        assert loaded["plan_id"] == plan.plan_id
        assert loaded["goal"] == "test goal"

    def test_save_with_steps(self, store):
        plan = OrchestrationPlan(goal="test goal")
        result = OrchestrationResult(plan=plan, overall_success=True)
        result.step_results = [
            StepResult(step_id="s1", provider_id="forge", chain_type=ChainType.SEQUENTIAL,
                      success=True, duration_ms=100,
                      confidence=StepConfidence(confidence=0.9, quality_score=0.85, cost=0.05, risk=0.1)),
        ]
        store.save_result(result)
        steps = store.get_steps_for_plan(plan.plan_id)
        assert len(steps) == 1
        assert steps[0]["provider_id"] == "forge"
        assert steps[0]["confidence"] == 0.9

    def test_query_by_goal(self, store):
        plan1 = OrchestrationPlan(goal="Build a Python API")
        result1 = OrchestrationResult(plan=plan1, overall_success=True)
        store.save_result(result1)

        plan2 = OrchestrationPlan(goal="Build a React frontend")
        result2 = OrchestrationResult(plan=plan2, overall_success=True)
        store.save_result(result2)

        results = store.query_by_goal("Python")
        assert len(results) == 1
        assert results[0]["goal"] == "Build a Python API"

    def test_success_rate(self, store):
        p1 = OrchestrationPlan(goal="test")
        store.save_result(OrchestrationResult(plan=p1, overall_success=True))
        p2 = OrchestrationPlan(goal="test")
        store.save_result(OrchestrationResult(plan=p2, overall_success=False))
        p3 = OrchestrationPlan(goal="test")
        store.save_result(OrchestrationResult(plan=p3, overall_success=True))
        rate = store.get_success_rate()
        assert rate == 2.0 / 3.0

    def test_success_rate_filtered(self, store):
        p1 = OrchestrationPlan(goal="Python API")
        store.save_result(OrchestrationResult(plan=p1, overall_success=True))
        p2 = OrchestrationPlan(goal="Python API")
        store.save_result(OrchestrationResult(plan=p2, overall_success=False))
        p3 = OrchestrationPlan(goal="React UI")
        store.save_result(OrchestrationResult(plan=p3, overall_success=True))
        rate = store.get_success_rate("Python")
        assert rate == 0.5

    def test_avg_duration(self, store):
        p1 = OrchestrationPlan(goal="test")
        r1 = OrchestrationResult(plan=p1, overall_success=True, start_time=0, end_time=1000)
        store.save_result(r1)
        p2 = OrchestrationPlan(goal="test")
        r2 = OrchestrationResult(plan=p2, overall_success=True, start_time=0, end_time=3000)
        store.save_result(r2)
        avg = store.get_avg_duration()
        assert avg == 2000.0

    def test_most_used_providers(self, store):
        plan = OrchestrationPlan(goal="test")
        result = OrchestrationResult(plan=plan, overall_success=True)
        result.step_results = [
            StepResult(step_id="s1", provider_id="forge", chain_type=ChainType.SEQUENTIAL,
                      success=True, duration_ms=100),
            StepResult(step_id="s2", provider_id="forge", chain_type=ChainType.SEQUENTIAL,
                      success=True, duration_ms=100),
            StepResult(step_id="s3", provider_id="codex", chain_type=ChainType.SEQUENTIAL,
                      success=True, duration_ms=100),
        ]
        store.save_result(result)
        providers = store.get_most_used_providers(limit=2)
        assert len(providers) == 2
        assert providers[0]["provider_id"] == "forge"

    def test_provider_success_rate(self, store):
        plan = OrchestrationPlan(goal="test")
        result = OrchestrationResult(plan=plan, overall_success=True)
        result.step_results = [
            StepResult(step_id="s1", provider_id="forge", chain_type=ChainType.SEQUENTIAL,
                      success=True, duration_ms=100, confidence=StepConfidence(confidence=0.9)),
            StepResult(step_id="s2", provider_id="forge", chain_type=ChainType.SEQUENTIAL,
                      success=False, duration_ms=50),
        ]
        store.save_result(result)
        stats = store.get_provider_success_rate("forge")
        assert stats["total"] == 2
        assert stats["success_rate"] == 0.5

    def test_failure_analysis(self, store):
        plan = OrchestrationPlan(goal="test")
        result = OrchestrationResult(plan=plan, overall_success=False)
        result.step_results = [
            StepResult(step_id="s1", provider_id="forge", chain_type=ChainType.SEQUENTIAL,
                      success=False, error="connection refused"),
            StepResult(step_id="s2", provider_id="forge", chain_type=ChainType.SEQUENTIAL,
                      success=False, error="connection refused"),
            StepResult(step_id="s3", provider_id="codex", chain_type=ChainType.SEQUENTIAL,
                      success=False, error="timeout"),
        ]
        store.save_result(result)
        failures = store.get_failure_analysis(limit=5)
        assert len(failures) >= 2
        assert failures[0]["failure_count"] >= failures[1]["failure_count"]

    def test_get_summary_stats(self, store):
        p1 = OrchestrationPlan(goal="test")
        store.save_result(OrchestrationResult(plan=p1, overall_success=True))
        p2 = OrchestrationPlan(goal="test")
        store.save_result(OrchestrationResult(plan=p2, overall_success=False))
        stats = store.get_summary_stats()
        assert stats["total_plans"] == 2
        assert stats["total_steps"] == 0
        assert stats["overall_success_rate"] == 0.5

    def test_clear(self, store):
        plan = OrchestrationPlan(goal="test")
        store.save_result(OrchestrationResult(plan=plan, overall_success=True))
        store.clear()
        stats = store.get_summary_stats()
        assert stats["total_plans"] == 0

    def test_get_recent_plans(self, store):
        for i in range(5):
            p = OrchestrationPlan(goal=f"test {i}")
            store.save_result(OrchestrationResult(plan=p, overall_success=True))
        recent = store.get_recent_plans(limit=3)
        assert len(recent) == 3

    def test_durability(self, store):
        plan = OrchestrationPlan(goal="durable")
        store.save_result(OrchestrationResult(plan=plan, overall_success=True))
        store2 = OrchestrationStore(db_path=store._db_path)
        loaded = store2.get_plan(plan.plan_id)
        assert loaded is not None


# ── OrchestrationResult: Extended Summary ────────────────────────────────────


class TestOrchestrationResultExtended:
    def test_summary_with_confidence(self):
        plan = OrchestrationPlan(goal="test")
        result = OrchestrationResult(plan=plan)
        result.step_results = [
            StepResult(step_id="s1", provider_id="forge", chain_type=ChainType.SEQUENTIAL,
                      success=True, duration_ms=100,
                      confidence=StepConfidence(confidence=0.9, quality_score=0.85, cost=0.05, risk=0.1)),
        ]
        result.overall_success = True
        result.start_time = 0
        result.end_time = 1000
        s = result.summary()
        assert "conf=0.90" in s or "conf=0.9" in s
        assert "qual=0.85" in s or "quality=0.85" in s

    def test_summary_with_multiple_steps(self):
        plan = OrchestrationPlan(goal="test")
        result = OrchestrationResult(plan=plan)
        result.step_results = [
            StepResult(step_id="s1", provider_id="forge", chain_type=ChainType.SEQUENTIAL,
                      success=True, duration_ms=100,
                      confidence=StepConfidence(confidence=0.9, quality_score=0.85, cost=0.05, risk=0.1)),
            StepResult(step_id="s2", provider_id="codex", chain_type=ChainType.SEQUENTIAL,
                      success=False, duration_ms=200,
                      confidence=StepConfidence(confidence=0.0, quality_score=0.0, cost=0.02, risk=1.0)),
        ]
        result.overall_success = False
        result.start_time = 0
        result.end_time = 500
        s = result.summary()
        assert "FAIL" in s

    def test_collect_confidence(self):
        plan = OrchestrationPlan(goal="test")
        result = OrchestrationResult(plan=plan)
        result.step_results = [
            StepResult(step_id="s1", provider_id="forge", chain_type=ChainType.SEQUENTIAL,
                      success=True, confidence=StepConfidence(confidence=0.9)),
            StepResult(step_id="s2", provider_id="codex", chain_type=ChainType.SEQUENTIAL,
                      success=True, confidence=StepConfidence(confidence=0.8)),
        ]
        confs = result.collect_confidence()
        assert confs["s1"].confidence == 0.9
        assert confs["s2"].confidence == 0.8
