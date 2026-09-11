from unittest.mock import Mock

from core.desktop.control import SemanticControlService
from core.desktop.discovery import ControlInfo, WindowInfo


def test_semantic_control_requires_unique_match():
    discovery = Mock()
    discovery.discover_window.return_value = WindowInfo(
        title="Editor",
        controls=(
            ControlInfo(name="Save", control_type="Button", patterns=("invoke",)),
            ControlInfo(name="Save As", control_type="Button", patterns=("invoke",)),
        ),
    )
    service = SemanticControlService(discovery)
    result = service.invoke("Editor", "Save")
    assert result["success"] is False
    assert result["verified"] is False


def test_semantic_control_reports_missing_executor():
    discovery = Mock()
    discovery.discover_window.return_value = WindowInfo(
        title="Editor",
        controls=(ControlInfo(name="Save", control_type="Button"),),
    )
    result = SemanticControlService(discovery).invoke("Editor", "Save")
    assert result["success"] is False
    assert "executor" in result["error"]
