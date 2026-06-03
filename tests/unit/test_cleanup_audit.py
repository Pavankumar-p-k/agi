from core.cleanup_audit import build_cleanup_audit


def test_cleanup_audit_has_entrypoints_and_totals():
    audit = build_cleanup_audit()

    assert "core.main" in audit.entrypoints
    assert audit.totals["python_files"] > 0
    assert audit.totals["active_modules"] > 0
    assert isinstance(audit.orphan_candidates, list)


def test_cleanup_audit_serializes():
    data = build_cleanup_audit().to_dict()

    assert "root_clutter" in data
    assert "duplicate_basenames" in data
    assert "recommendations" in data
