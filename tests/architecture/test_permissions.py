from __future__ import annotations

import pytest


class TestPermissions:
    def test_known_permission_valid(self):
        from provider_sdk.permissions import validate_permissions
        errors = validate_permissions(["filesystem.read", "network.http"])
        assert errors == []

    def test_wildcard_rejected(self):
        from provider_sdk.permissions import validate_permissions
        for wild in ("all", "*", "everything", "any"):
            errors = validate_permissions([wild])
            assert any("Wildcard" in e for e in errors), f"{wild} not rejected"

    def test_unknown_permission_rejected(self):
        from provider_sdk.permissions import validate_permissions
        errors = validate_permissions(["foo.bar.baz"])
        assert any("Unknown" in e for e in errors)

    def test_allows_known_permission(self):
        from provider_sdk.permissions import PermissionManager
        pm = PermissionManager()
        pm.clear()
        pm.grant("test-provider", frozenset({"filesystem.read", "network.http"}))
        assert pm.check("test-provider", "filesystem.read") is True
        assert pm.check("test-provider", "network.http") is True

    def test_denies_unknown_permission(self):
        from provider_sdk.permissions import PermissionManager
        pm = PermissionManager()
        pm.clear()
        pm.grant("test-provider", frozenset({"filesystem.read"}))
        assert pm.check("test-provider", "network.http") is False

    def test_denies_no_grant(self):
        from provider_sdk.permissions import PermissionManager
        pm = PermissionManager()
        pm.clear()
        assert pm.check("unknown-provider", "filesystem.read") is False

    def test_high_risk_detected(self):
        from provider_sdk.permissions import PermissionManager
        pm = PermissionManager()
        pm.clear()
        grant = pm.grant("risky", frozenset({"system.shell", "filesystem.read"}))
        assert grant.high_risk_warning is True

    def test_low_risk_not_detected(self):
        from provider_sdk.permissions import PermissionManager
        pm = PermissionManager()
        pm.clear()
        grant = pm.grant("safe", frozenset({"filesystem.read"}))
        assert grant.high_risk_warning is False

    def test_audit_log(self):
        from provider_sdk.permissions import PermissionManager
        pm = PermissionManager()
        pm.clear()
        pm.grant("audit-provider", frozenset({"clipboard.read"}))
        pm.check("audit-provider", "clipboard.read")
        pm.check("audit-provider", "network.http")
        log = pm.get_audit_log()
        assert len(log) == 2
        allow_entries = [e for e in log if e["result"] == "ALLOW"]
        deny_entries = [e for e in log if e["result"] == "DENY"]
        assert len(allow_entries) == 1
        assert len(deny_entries) == 1

    def test_violations_filtered(self):
        from provider_sdk.permissions import PermissionManager
        pm = PermissionManager()
        pm.clear()
        pm.grant("violations-test", frozenset({"clipboard.read"}))
        pm.check("violations-test", "filesystem.write")
        pm.check("violations-test", "network.http")
        pm.check("other-provider", "clipboard.read")
        violations = pm.violations("violations-test")
        assert len(violations) == 2
        assert all(v["provider_id"] == "violations-test" for v in violations)
