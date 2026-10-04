"""Secure Windows-only desktop bridge for JARVIS.

Run on the Windows host (not in the JARVIS container):
    python desktop_bridge.py
"""

from __future__ import annotations

import hmac
import os
import re
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from core.desktop.controller import desktop_controller

HOST = "127.0.0.1"
PORT = int(os.getenv("DESKTOP_BRIDGE_PORT", "8765"))
_APP_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}$")
ALLOWED_ACTIONS = frozenset((
    "open_url", "launch_app", "desktop_state", "click", "type_text",
    "press_key", "focus_window",
))

app = FastAPI(title="JARVIS Windows Desktop Bridge")


class ActionRequest(BaseModel):
    action: str
    params: dict[str, Any] = Field(default_factory=dict)


def _valid_url(value: Any) -> bool:
    if not isinstance(value, str) or len(value) > 2048:
        return False
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _validate(request: ActionRequest) -> None:
    if request.action not in ALLOWED_ACTIONS:
        raise HTTPException(status_code=400, detail="Unsupported desktop action")
    if request.action == "desktop_state":
        if request.params:
            raise HTTPException(status_code=400, detail="desktop_state takes no parameters")
    elif request.action == "click":
        if not isinstance(request.params.get("x"), int) or not isinstance(request.params.get("y"), int):
            raise HTTPException(status_code=400, detail="Integer x and y coordinates are required")
        if request.params.get("button", "left") not in ("left", "right", "middle"):
            raise HTTPException(status_code=400, detail="Unsupported mouse button")
    elif request.action == "type_text":
        if not isinstance(request.params.get("text"), str) or len(request.params["text"]) > 10000:
            raise HTTPException(status_code=400, detail="Text is required and must be at most 10000 characters")
        interval = request.params.get("interval", 0.05)
        if not isinstance(interval, (int, float)) or interval <= 0 or interval > 10:
            raise HTTPException(status_code=400, detail="interval must be between 0 and 10 seconds")
    elif request.action == "press_key":
        if not isinstance(request.params.get("key"), str) or not re.fullmatch(r"[A-Za-z0-9_+-]{1,32}", request.params["key"]):
            raise HTTPException(status_code=400, detail="A valid key is required")
    elif request.action == "focus_window":
        if not isinstance(request.params.get("window_title"), str) or not request.params["window_title"].strip():
            raise HTTPException(status_code=400, detail="A window title is required")
    elif request.action == "open_url":
        if set(request.params) != {"url"} or not _valid_url(request.params["url"]):
            raise HTTPException(status_code=400, detail="A valid http/https URL is required")
    elif (
        set(request.params) != {"app_name"}
        or not isinstance(request.params["app_name"], str)
        or not _APP_NAME.fullmatch(request.params["app_name"])
    ):
        raise HTTPException(status_code=400, detail="A valid application name is required")


def _configured_token() -> str | None:
    return os.getenv("DESKTOP_BRIDGE_TOKEN")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/action")
def action(request: ActionRequest, x_desktop_bridge_token: str | None = Header(default=None)) -> dict[str, Any]:
    token = _configured_token()
    if not token:
        raise HTTPException(status_code=503, detail="DESKTOP_BRIDGE_TOKEN is not configured")
    if not x_desktop_bridge_token or not hmac.compare_digest(x_desktop_bridge_token, token):
        raise HTTPException(status_code=401, detail="Invalid desktop bridge token")
    _validate(request)

    if request.action == "open_url":
        result = desktop_controller.open_url(request.params["url"])
    elif request.action == "launch_app":
        result = desktop_controller.launch_app(request.params["app_name"])
    elif request.action == "click":
        result = desktop_controller.click(request.params["x"], request.params["y"], request.params.get("button", "left"))
    elif request.action == "type_text":
        result = desktop_controller.type_text(request.params["text"], request.params.get("interval", 0.05))
    elif request.action == "press_key":
        result = desktop_controller.press_key(request.params["key"])
    elif request.action == "focus_window":
        result = desktop_controller.focus_window(request.params["window_title"])
    else:
        from core.workspace.desktop_state import DesktopState
        import asyncio
        snapshot = asyncio.run(DesktopState().snapshot())
        active = snapshot.active_window.__dict__ if snapshot.active_window else None
        result = type("StateResult", (), {
            "success": True,
            "error": "",
            "details": {
                "active_window": active,
                "windows": [
                    {
                        "title": w.title,
                        "left": w.left,
                        "top": w.top,
                        "width": w.width,
                        "height": w.height,
                    }
                    for w in snapshot.windows
                ],
                "tabs": [t.__dict__ for t in snapshot.browser.tabs],
                "processes": [
                    {"name": p.name, "pid": p.pid, "status": p.status}
                    for p in snapshot.processes[:100]
                ],
            },
        })()
    response: dict[str, Any] = {
        "success": bool(result.success),
        "action": request.action,
        "result": result.details if request.action == "desktop_state" and result.success else (
            f"{request.action} completed" if result.success else ""
        ),
        "error": result.error,
    }
    return response


if __name__ == "__main__":
    import uvicorn

    if os.name != "nt":
        raise SystemExit("The desktop bridge must run on Windows.")
    if not _configured_token():
        raise SystemExit("Set DESKTOP_BRIDGE_TOKEN before starting the desktop bridge.")
    uvicorn.run(app, host=HOST, port=PORT)
