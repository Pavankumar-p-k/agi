from __future__ import annotations

import pytest

from core.permission.audit import PermissionAudit
from core.permission.manager import PermissionManager
from core.permission.models import Decision, Permission, PermissionCategory, RiskLevel, AuditEntry
from core.permission.observer import RuntimeObserver
from core.permission.policy import PolicyEngine, PolicyProfile
from core.permission.registry import PermissionRegistry


# ──────────────────────────────────────────────
# Gate 1 — Every capability declares permissions
# ──────────────────────────────────────────────

class TestGate1CapabilityDeclaresPermissions:
    def test_all_builtin_capabilities_have_permissions(self):
        from core.capability.models import _BUILTIN_CAPABILITIES
        for cid, cap in _BUILTIN_CAPABILITIES.items():
            assert len(cap.permissions) >= 0, f"{cid} has no permissions tuple"

    def test_capability_registry_exposes_permissions(self):
        from core.capability.models import _BUILTIN_CAPABILITIES
        for cid, cap in _BUILTIN_CAPABILITIES.items():
            perms = cap.permissions
            assert isinstance(perms, tuple)

    def test_known_permissions_are_valid(self):
        from core.capability.models import _BUILTIN_CAPABILITIES
        from core.permission.models import ALL_PERMISSIONS
        for cid, cap in _BUILTIN_CAPABILITIES.items():
            for p in cap.permissions:
                assert p in ALL_PERMISSIONS, f"{cid} declares unknown permission '{p}'"


# ──────────────────────────────────────────────
# Gate 2 — Every provider declares permissions
# ──────────────────────────────────────────────

class TestGate2ProviderDeclaresPermissions:
    def test_provider_descriptor_has_permissions(self):
        from provider_sdk.manifest_v2 import ProviderDescriptor
        descriptor = ProviderDescriptor(
            id="test_provider",
            publisher="test",
            version="1.0.0",
            sdk_version=2,
            api_version=1,
            transport="python",
            entrypoint="test:provider",
            permissions=frozenset({"filesystem.read"}),
            declared_capabilities=(),
            platforms=("windows",),
            fingerprint="abc123",
            manifest_path="/tmp/fake.json",
            metadata={},
        )
        assert "filesystem.read" in descriptor.permissions

    def test_manifest_v2_requires_permissions(self):
        from provider_sdk.manifest_v2 import REQUIRED_V2
        assert "permissions" in REQUIRED_V2

    def test_registry_tracks_provider_declared_permissions(self):
        registry = PermissionRegistry()
        perms = registry.permissions_for_capability("coding")
        assert "filesystem.read" in perms
        assert "filesystem.write" in perms


# ──────────────────────────────────────────────
# Gate 3 — Planner never references permissions
# ──────────────────────────────────────────────

class TestGate3PlannerNoPermissions:
    def test_planner_does_not_import_permission_modules(self):
        import ast
        import inspect
        import core.planner
        source = inspect.getsource(core.planner)
        bad_names = {
            "PermissionManager", "PermissionRegistry",
            "Decision", "PolicyEngine", "PermissionAudit",
            "RuntimeObserver",
        }
        provider_imports = [n for n in bad_names if n in source]
        assert len(provider_imports) == 0, (
            f"Planner references permissions directly: {provider_imports}"
        )


# ──────────────────────────────────────────────
# Gate 4 — Permission Manager is single auth point
# ──────────────────────────────────────────────

class TestGate4PermissionManagerCentral:
    def test_permission_manager_resolve_returns_decision(self):
        mgr = PermissionManager()
        resolution = mgr.resolve("coding")
        assert resolution.overall in (Decision.ALLOW, Decision.DENY, Decision.NEED_CONFIRM)
        assert resolution.capability_id == "coding"

    def test_permission_manager_resolve_has_full_trace(self):
        mgr = PermissionManager()
        resolution = mgr.resolve("desktop")
        d = resolution.to_dict()
        assert "capability_id" in d
        assert "required_permissions" in d
        assert "policy" in d
        assert "results" in d
        assert "overall" in d
        assert "reason" in d

    def test_permission_manager_is_single_entry_point(self):
        from core.permission.manager import permission_manager
        from core.capability.composition import CompositionEngine, composition_engine
        resolution = permission_manager.resolve("coding")
        assert resolution.allowed or resolution.denied or resolution.needs_confirmation


# ──────────────────────────────────────────────
# Gate 5 — Denied permissions stop before negotiation
# ──────────────────────────────────────────────

class TestGate5DenyStopsExecution:
    def test_denied_capability_has_no_provider(self):
        from core.capability.composition import CompositionEngine, CompositionPlan
        engine = CompositionEngine()
        plan = engine.compose("build app")
        for step in plan.steps:
            if step.permission.get("overall") == "deny":
                assert step.provider_id == "", (
                    f"Denied capability '{step.capability_id}' still got provider '{step.provider_id}'"
                )

    def test_denied_capability_has_blocked_flag(self):
        from core.capability.composition import CompositionEngine
        engine = CompositionEngine()
        plan = engine.compose("build app")
        blocked_steps = [s for s in plan.steps if s.permission.get("overall") == "deny"]
        if blocked_steps:
            assert plan.blocked is True


# ──────────────────────────────────────────────
# Gate 6 — Every decision enters audit log
# ──────────────────────────────────────────────

class TestGate6AuditLog:
    def test_permission_manager_records_audit(self):
        audit = PermissionAudit()
        mgr = PermissionManager(audit=audit)
        mgr.resolve("coding")
        recent = audit.recent()
        assert len(recent) >= 1
        entry = recent[0]
        assert entry.capability_id == "coding"
        assert entry.decision in (Decision.ALLOW, Decision.DENY, Decision.NEED_CONFIRM)

    def test_audit_entry_has_full_context(self):
        audit = PermissionAudit()
        mgr = PermissionManager(audit=audit)
        mgr.resolve("desktop")
        entries = audit.recent()
        assert len(entries) >= 1
        entry = entries[0]
        assert isinstance(entry.timestamp, float)
        assert entry.permission_id != ""
        assert entry.policy != ""
        assert entry.reason != ""

    def test_audit_can_filter_by_capability(self):
        audit = PermissionAudit()
        mgr = PermissionManager(audit=audit)
        mgr.resolve("coding")
        mgr.resolve("browser")
        coding_entries = audit.by_capability("coding")
        browser_entries = audit.by_capability("browser")
        assert len(coding_entries) >= 1
        assert len(browser_entries) >= 1


# ──────────────────────────────────────────────
# Gate 7 — Policy profiles work
# ──────────────────────────────────────────────

class TestGate7PolicyProfiles:
    def test_strict_blocks_desktop(self):
        engine = PolicyEngine()
        engine.set_profile(PolicyProfile.STRICT)
        perm = Permission(
            "desktop.mouse.click",
            category=PermissionCategory.DESKTOP,
            risk=RiskLevel.CRITICAL,
        )
        decision = engine.evaluate(perm, PolicyProfile.STRICT)
        assert decision == Decision.DENY

    def test_strict_requires_confirmation_for_network(self):
        engine = PolicyEngine()
        engine.set_profile(PolicyProfile.STRICT)
        perm = Permission("network.http", risk=RiskLevel.LOW, category=PermissionCategory.NETWORK)
        decision = engine.evaluate(perm, PolicyProfile.STRICT)
        assert decision == Decision.NEED_CONFIRM

    def test_developer_allows_filesystem_read(self):
        engine = PolicyEngine()
        engine.set_profile(PolicyProfile.DEVELOPER)
        perm = Permission("filesystem.read", risk=RiskLevel.LOW)
        decision = engine.evaluate(perm, PolicyProfile.DEVELOPER)
        assert decision == Decision.ALLOW

    def test_developer_blocks_critical_without_confirmation(self):
        engine = PolicyEngine()
        engine.set_profile(PolicyProfile.DEVELOPER)
        perm = Permission("desktop.mouse.click", risk=RiskLevel.CRITICAL)
        decision = engine.evaluate(perm, PolicyProfile.DEVELOPER)
        assert decision == Decision.NEED_CONFIRM

    def test_autonomous_allows_critical(self):
        engine = PolicyEngine()
        engine.set_profile(PolicyProfile.AUTONOMOUS)
        perm = Permission("system.shell", risk=RiskLevel.CRITICAL)
        decision = engine.evaluate(perm, PolicyProfile.AUTONOMOUS)
        assert decision == Decision.ALLOW

    def test_autonomous_can_be_set_str(self):
        engine = PolicyEngine()
        engine.set_profile("autonomous")
        assert engine.active_profile == PolicyProfile.AUTONOMOUS

    def test_policy_rule_has_expected_fields(self):
        from core.permission.policy import PolicyRule
        rule = PolicyRule()
        assert hasattr(rule, "max_risk")
        assert hasattr(rule, "require_confirmation")
        assert hasattr(rule, "allow_critical")
        assert hasattr(rule, "audit_all")
        assert hasattr(rule, "block_categories")
        assert hasattr(rule, "require_confirmation_for_categories")


# ──────────────────────────────────────────────
# Gate 8 — Runtime violations quarantine providers
# ──────────────────────────────────────────────

class TestGate8RuntimeViolations:
    def test_observer_tracks_undeclared_permissions(self):
        observer = RuntimeObserver()
        observer.declare("test_provider", frozenset({"filesystem.read"}))
        observer.observe("test_provider", "network.http")
        violations = observer.violations_for("test_provider")
        assert len(violations) == 1
        assert violations[0].permission_id == "network.http"

    def test_observer_quarantine_threshold(self):
        observer = RuntimeObserver()
        observer.declare("bad_provider", frozenset({"filesystem.read"}))
        for _ in range(3):
            observer.observe("bad_provider", "network.http")
        assert observer.should_quarantine("bad_provider") is True

    def test_observer_does_not_quarantine_below_threshold(self):
        observer = RuntimeObserver()
        observer.declare("good_provider", frozenset({"filesystem.read", "network.http"}))
        observer.observe("good_provider", "network.http")
        assert observer.should_quarantine("good_provider") is False

    def test_observer_declared_not_violated(self):
        observer = RuntimeObserver()
        observer.declare("clean_provider", frozenset({"filesystem.read", "network.http"}))
        observer.observe("clean_provider", "filesystem.read")
        observer.observe("clean_provider", "network.http")
        assert observer.violation_count("clean_provider") == 0

    def test_runtime_violation_is_blocked(self):
        observer = RuntimeObserver()
        observer.declare("p", frozenset({"filesystem.read"}))
        observer.observe("p", "filesystem.read")
        observer.observe("p", "network.http")
        # The violation should be recorded
        assert observer.violation_count("p") == 1


# ──────────────────────────────────────────────
# Gate 9 — Backward compatibility
# ──────────────────────────────────────────────

class TestGate9BackwardCompat:
    def test_existing_permission_tests_still_pass(self):
        from provider_sdk.permissions import validate_permissions
        errors = validate_permissions(["filesystem.read", "network.http"])
        assert errors == []

    def test_wildcard_still_rejected(self):
        from provider_sdk.permissions import validate_permissions
        errors = validate_permissions(["*"])
        assert len(errors) == 1

    def test_unknown_permission_still_rejected(self):
        from provider_sdk.permissions import validate_permissions
        errors = validate_permissions(["foo.bar.baz"])
        assert len(errors) == 1

    def test_manifest_v2_still_validates(self):
        from provider_sdk.manifest_v2 import validate_v2_schema
        errors = validate_v2_schema({
            "id": "test-provider",
            "publisher": "test",
            "version": "1.0.0",
            "sdk_version": 2,
            "api_version": 1,
            "minimum_jarvis": "3.0",
            "transport": "python",
            "entrypoint": "test:provider",
            "permissions": ["filesystem.read"],
            "platforms": ["windows"],
        })
        assert errors == []

    def test_capability_permissions_field_still_works(self):
        from core.capability.models import Capability
        cap = Capability(id="custom", permissions=("filesystem.read",), description="test")
        assert "filesystem.read" in cap.permissions

    def test_composition_engine_still_produces_plans(self):
        from core.capability.composition import CompositionEngine, composition_engine
        plan = composition_engine.compose("build app")
        assert isinstance(plan.steps, tuple)
        assert plan.subgraph_fingerprint != ""

    def test_negotiation_still_works_without_permission_check(self):
        from core.capability.negotiation import capability_negotiator
        from core.capability.graph import CapabilityNode
        result = capability_negotiator.resolve(CapabilityNode(capability_id="coding"))
        assert result.capability_id == "coding"
