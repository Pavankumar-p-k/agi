from unittest.mock import patch

import pytest

from core.desktop.discovery import ControlInfo, DesktopDiscovery


def test_control_info_serializes():
    control = ControlInfo(name="Save", control_type="Button", patterns=("invoke",))
    assert control.to_dict()["patterns"] == ("invoke",)


def test_discovery_rejects_invalid_limits():
    with pytest.raises(ValueError):
        DesktopDiscovery(max_controls=0)


@patch("pygetwindow.getAllWindows")
def test_window_discovery_returns_structured_snapshot(get_windows):
    class FakeWindow:
        title = "Notepad"
        left, top, width, height = 1, 2, 300, 200
        isActive = True

    get_windows.return_value = [FakeWindow()]
    discovery = DesktopDiscovery()
    window = discovery.discover_window("note")
    assert window is not None
    assert window.title == "Notepad"
    assert window.bounds["width"] == 300
    assert discovery.capability_snapshot("missing")["found"] is False


def test_discovery_uses_shared_window_controller():
    class Controller:
        def list_windows(self):
            return [{"title": "Editor", "width": 10, "height": 20}]

    window = DesktopDiscovery(window_controller=Controller()).discover_window("edit", include_controls=False)
    assert window is not None
    assert window.bounds["height"] == 20
