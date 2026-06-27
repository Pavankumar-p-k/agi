"""Unit tests for Phase 1 X.9 Learning Models.

Tests cover: RecoveryMode, ProviderEntry, WorkflowTemplate,
WorkflowFingerprint, WorkflowInstance, WorkflowOutcome.
"""

from core.workflow.learning_models import (
    ProviderEntry,
    RecoveryMode,
    WorkflowFingerprint,
    WorkflowInstance,
    WorkflowOutcome,
    WorkflowTemplate,
)


class TestRecoveryMode:
    def test_enum_values(self):
        assert RecoveryMode.FIRST_TRY.value == "FIRST_TRY"
        assert RecoveryMode.AFTER_RETRY.value == "AFTER_RETRY"
        assert RecoveryMode.AFTER_REPLAN.value == "AFTER_REPLAN"
        assert RecoveryMode.AFTER_PROVIDER_SWAP.value == "AFTER_PROVIDER_SWAP"
        assert RecoveryMode.AFTER_COMPENSATION.value == "AFTER_COMPENSATION"
        assert RecoveryMode.AFTER_HUMAN_APPROVAL.value == "AFTER_HUMAN_APPROVAL"
        assert RecoveryMode.FAILED.value == "FAILED"

    def test_recovery_mode_order(self):
        modes = list(RecoveryMode)
        assert modes[0] == RecoveryMode.FIRST_TRY
        assert modes[-1] == RecoveryMode.FAILED


class TestProviderEntry:
    def test_minimal_entry(self):
        e = ProviderEntry()
        assert e.provider == ""
        assert e.capability == ""
        assert e.duration_ms == 0.0
        assert e.success is False
        assert e.retries == 0
        assert e.cost == 0.0

    def test_full_entry(self):
        e = ProviderEntry(
            provider="forge",
            capability="coding",
            duration_ms=18342.0,
            success=True,
            retries=0,
            cost=0.0,
        )
        assert e.provider == "forge"
        assert e.capability == "coding"
        assert e.duration_ms == 18342.0
        assert e.success is True

    def test_entry_can_be_dict(self):
        d = {
            "provider": "codex",
            "capability": "security_review",
            "duration_ms": 7421.0,
            "success": True,
            "retries": 1,
            "cost": 0.02,
        }
        e = ProviderEntry(**d)
        assert e.provider == "codex"
        assert e.retries == 1
        assert e.cost == 0.02


class TestWorkflowTemplate:
    def test_minimal_template(self):
        t = WorkflowTemplate(template_id="test_build")
        assert t.template_id == "test_build"
        assert t.version == 1
        assert t.display_name == "test_build"

    def test_template_with_version(self):
        t = WorkflowTemplate(template_id="android_build", version=2)
        assert t.display_name == "android_build@2"

    def test_template_frozen(self):
        import dataclasses
        t = WorkflowTemplate(template_id="frozen_test")
        assert dataclasses.fields(t)

    def test_template_display_version_1(self):
        t = WorkflowTemplate(template_id="simple_build", version=1)
        assert t.display_name == "simple_build"

    def test_template_full(self):
        t = WorkflowTemplate(
            template_id="full_template",
            version=3,
            name="Full Test Template",
            description="A template with everything filled in",
            capabilities_required=["coding", "testing", "email"],
            orchestration_graph={"steps": ["build", "test", "notify"]},
            metadata={"author": "test", "created": "2026-01-01"},
        )
        assert t.name == "Full Test Template"
        assert t.description == "A template with everything filled in"
        assert len(t.capabilities_required) == 3
        assert "coding" in t.capabilities_required
        assert t.orchestration_graph["steps"] == ["build", "test", "notify"]
        assert t.metadata["author"] == "test"


class TestWorkflowFingerprint:
    def test_minimal_fingerprint(self):
        fp = WorkflowFingerprint()
        assert fp.context_key() == ""

    def test_task_type_only(self):
        fp = WorkflowFingerprint(task_type="build")
        assert "t:build" in fp.context_key()

    def test_full_fingerprint(self):
        fp = WorkflowFingerprint(
            task_type="build",
            complexity="medium",
            project_size="large",
            languages=["python", "typescript"],
            frameworks=["fastapi", "react"],
            capabilities=["coding", "testing"],
            artifact_types=["apk", "report"],
            requirements=["auth", "email"],
        )
        key = fp.context_key()
        assert "t:build" in key
        assert "c:medium" in key
        assert "s:large" in key
        assert "l:python,typescript" in key or "l:typescript,python" in key
        assert "f:fastapi,react" in key or "f:react,fastapi" in key
        assert "p:coding,testing" in key or "p:testing,coding" in key
        assert "a:apk,report" in key or "a:report,apk" in key
        assert "r:auth,email" in key or "r:email,auth" in key

    def test_fingerprint_deterministic(self):
        fp1 = WorkflowFingerprint(
            task_type="build",
            languages=["python", "typescript"],
        )
        fp2 = WorkflowFingerprint(
            task_type="build",
            languages=["typescript", "python"],
        )
        assert fp1.context_key() == fp2.context_key()

    def test_fingerprint_hash(self):
        fp1 = WorkflowFingerprint(task_type="build", languages=["python"])
        fp2 = WorkflowFingerprint(task_type="build", languages=["python"])
        assert hash(fp1) == hash(fp2)

    def test_fingerprint_hash_differs(self):
        fp1 = WorkflowFingerprint(task_type="build")
        fp2 = WorkflowFingerprint(task_type="research")
        assert hash(fp1) != hash(fp2)

    def test_fingerprint_context_key_consistent(self):
        fp = WorkflowFingerprint(task_type="build")
        assert fp.context_key() == fp.context_key()

    def test_partial_fingerprint(self):
        fp = WorkflowFingerprint(complexity="high", project_size="small")
        key = fp.context_key()
        assert "c:high" in key
        assert "s:small" in key
        assert "t:" not in key  # no task_type

    def test_fingerprint_json_context(self):
        fp = WorkflowFingerprint(
            task_type="build",
            context_json='{"custom": "value"}',
        )
        assert fp.context_json == '{"custom": "value"}'
        assert "t:build" in fp.context_key()


class TestWorkflowInstance:
    def test_minimal_instance(self):
        inst = WorkflowInstance()
        assert inst.workflow_id.startswith("wf_")
        assert inst.status == "PENDING"

    def test_instance_with_values(self):
        fp = WorkflowFingerprint(task_type="build")
        inst = WorkflowInstance(
            workflow_id="wf_abc123",
            template_id="android_build",
            template_version=2,
            fingerprint=fp,
            status="COMPLETED",
            started_at=1000.0,
            completed_at=2000.0,
        )
        assert inst.workflow_id == "wf_abc123"
        assert inst.template_id == "android_build"
        assert inst.template_version == 2
        assert inst.fingerprint is fp
        assert inst.status == "COMPLETED"
        assert inst.started_at == 1000.0
        assert inst.completed_at == 2000.0


class TestWorkflowOutcome:
    def test_minimal_outcome(self):
        outcome = WorkflowOutcome()
        assert outcome.success is False
        assert outcome.recovery_mode == RecoveryMode.FIRST_TRY

    def test_outcome_with_values(self):
        fp = WorkflowFingerprint(task_type="build")
        outcome = WorkflowOutcome(
            workflow_id="wf_abc123",
            template_id="android_build",
            template_version=2,
            fingerprint=fp,
            success=True,
            duration_ms=840000.0,
            cost=0.42,
            quality=0.92,
            recovery_mode=RecoveryMode.AFTER_RETRY,
            artifacts=["apk", "report"],
            error_categories=["timeout"],
            provider_summary=[
                {"provider": "forge", "capability": "coding",
                 "duration_ms": 18342.0, "success": True, "retries": 0, "cost": 0.0},
            ],
            activity_graph_id="ag_xyz789",
        )
        assert outcome.success is True
        assert outcome.duration_ms == 840000.0
        assert outcome.cost == 0.42
        assert outcome.quality == 0.92
        assert outcome.recovery_mode == RecoveryMode.AFTER_RETRY
        assert outcome.artifacts == ["apk", "report"]
        assert outcome.error_categories == ["timeout"]
        assert outcome.provider_summary[0]["provider"] == "forge"
        assert outcome.provider_summary[0]["capability"] == "coding"
        assert outcome.activity_graph_id == "ag_xyz789"

    def test_outcome_failed_mode(self):
        outcome = WorkflowOutcome(
            workflow_id="wf_failed",
            template_id="test",
            success=False,
            recovery_mode=RecoveryMode.FAILED,
            error_categories=["build_error", "test_failure"],
        )
        assert outcome.success is False
        assert outcome.recovery_mode == RecoveryMode.FAILED
        assert len(outcome.error_categories) == 2

    def test_outcome_recovery_mode_from_string(self):
        mode = RecoveryMode("AFTER_PROVIDER_SWAP")
        assert mode == RecoveryMode.AFTER_PROVIDER_SWAP

        outcome = WorkflowOutcome(
            workflow_id="wf_swap",
            template_id="test",
            recovery_mode=mode,
        )
        assert outcome.recovery_mode == RecoveryMode.AFTER_PROVIDER_SWAP
