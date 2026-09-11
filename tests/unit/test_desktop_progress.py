import pytest

from core.routes.progress import DesktopProgressReporter, ProgressEvent


def test_progress_report_is_bounded_and_serializable():
    reporter = DesktopProgressReporter()
    event = reporter.report("activity-1", "running", 1.5, "working")
    assert isinstance(event, ProgressEvent)
    assert event.progress == 1.0
    assert event.to_dict()["activity_id"] == "activity-1"


def test_progress_callback_and_latest():
    received = []
    reporter = DesktopProgressReporter(received.append)
    reporter.report("activity-1", "running", 0.25)
    event = reporter.report("activity-1", "completed", 1.0)
    assert received[-1]["status"] == "completed"
    assert reporter.latest("activity-1") == event
    assert reporter.latest("missing") is None


def test_progress_requires_identity_and_status():
    with pytest.raises(ValueError):
        ProgressEvent("", "running", 0.5)
    with pytest.raises(ValueError):
        ProgressEvent("activity-1", "", 0.5)
