from core.diagnostics import build_diagnostic_report


def test_diagnostic_report_has_operational_fields():
    report = build_diagnostic_report()

    assert report.status in {"ok", "warning", "degraded", "critical"}
    assert report.counts["python_files"] > 0
    assert "fastapi" in report.optional_dependencies
    assert "python_3_11_plus" in report.runtime_flags
    assert report.capability_gaps


def test_diagnostic_report_serializes_to_dict():
    data = build_diagnostic_report().to_dict()

    assert isinstance(data["issues"], list)
    assert isinstance(data["optional_dependencies"], dict)
    assert isinstance(data["capability_gaps"], list)
