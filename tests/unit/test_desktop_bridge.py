import pytest

import desktop_bridge
from core.action_engine import ActionEngine
from core.desktop.controller import DesktopController


def test_bridge_rejects_missing_or_invalid_token(monkeypatch):
    monkeypatch.setenv("DESKTOP_BRIDGE_TOKEN", "secret")
    request = desktop_bridge.ActionRequest(action="open_url", params={"url": "https://example.com"})
    with pytest.raises(desktop_bridge.HTTPException) as exc:
        desktop_bridge.action(request, "wrong")
    assert exc.value.status_code == 401


@pytest.mark.parametrize(
    "action_request",
    [
        desktop_bridge.ActionRequest(action="run_command", params={"command": "calc"}),
        desktop_bridge.ActionRequest(action="open_url", params={"url": "file:///secret"}),
        desktop_bridge.ActionRequest(action="launch_app", params={"app_name": "C:\\Windows\\calc.exe"}),
    ],
)
def test_bridge_validates_allowlisted_actions_and_inputs(monkeypatch, action_request):
    monkeypatch.setenv("DESKTOP_BRIDGE_TOKEN", "secret")
    with pytest.raises(desktop_bridge.HTTPException) as exc:
        desktop_bridge.action(action_request, "secret")
    assert exc.value.status_code == 400


def test_open_url_rejects_browser_false_success(monkeypatch):
    monkeypatch.setattr("webbrowser.open", lambda _url: False)
    result = DesktopController().open_url("https://example.com")
    assert result.success is False
    assert "could not be opened" in result.error


@pytest.mark.asyncio
async def test_action_engine_uses_local_fallback_without_bridge(monkeypatch):
    monkeypatch.delenv("DESKTOP_BRIDGE_URL", raising=False)
    engine = ActionEngine()

    class Result:
        success = True
        error = ""

    class Controller:
        def open_url(self, url):
            return Result()

    monkeypatch.setattr("core.desktop.controller.desktop_controller", Controller())
    result = await engine.open_url("https://example.com")
    assert result["success"] is True


@pytest.mark.asyncio
async def test_action_engine_reports_bridge_failure(monkeypatch):
    monkeypatch.setenv("DESKTOP_BRIDGE_URL", "http://127.0.0.1:8765")
    monkeypatch.setenv("DESKTOP_BRIDGE_TOKEN", "secret")
    engine = ActionEngine()

    class Response:
        status_code = 500
        text = "bridge failed"

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            return Response()

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: Client())
    result = await engine.launch_app("notepad")
    assert result["success"] is False
    assert "bridge failed" in result["error"]
