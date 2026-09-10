"""Async desktop action client with a local-controller fallback."""
from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urlparse

import httpx


class ActionEngine:
    """Dispatch supported desktop actions to the bridge or local controller."""

    _ACTION_PARAMS = {
        "click": None,
        "desktop_state": None,
        "open_url": "url",
        "launch_app": "app_name",
        "type_text": "text",
        "press_key": "key",
        "focus_window": "window_title",
    }

    def __init__(self, **config: Any) -> None:
        self.config = config

    def __call__(self, *args: Any, **kwargs: Any) -> "ActionEngine":
        return self

    async def __aenter__(self) -> "ActionEngine":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        return None

    def __getattr__(self, name: str):
        if name not in self._ACTION_PARAMS:
            raise AttributeError(name)

        async def dispatch(*args: Any, **kwargs: Any) -> dict[str, Any]:
            if name == "click":
                if len(args) > 2:
                    raise TypeError("click expects x and y coordinates")
                for key, value in zip(("x", "y"), args):
                    if key in kwargs:
                        raise TypeError(f"click received duplicate {key}")
                    kwargs[key] = value
                if "x" not in kwargs or "y" not in kwargs:
                    raise TypeError("click requires x and y coordinates")
                return await self.execute(name, kwargs)
            if name == "desktop_state":
                if args or kwargs:
                    raise TypeError("desktop_state takes no arguments")
                return await self.execute(name, {})
            param = self._ACTION_PARAMS[name]
            if args:
                if len(args) != 1 or param in kwargs:
                    raise TypeError(f"{name} expects one {param} argument")
                kwargs[param] = args[0]
            return await self.execute(name, kwargs)

        return dispatch

    async def click(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return await self.__getattr__("click")(*args, **kwargs)

    async def execute(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        validation_error = self._validation_error(action, params)
        if validation_error:
            return {"success": False, "error": validation_error}
        bridge_url = os.getenv("DESKTOP_BRIDGE_URL")
        if bridge_url:
            try:
                headers = {}
                token = os.getenv("DESKTOP_BRIDGE_TOKEN")
                if token:
                    headers["X-Desktop-Bridge-Token"] = token
                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.post(
                        f"{bridge_url.rstrip('/')}/action",
                        json={"action": action, "params": params},
                        headers=headers,
                    )
                if response.status_code >= 400:
                    return {"success": False, "error": response.text or f"Bridge HTTP {response.status_code}"}
                return response.json()
            except (httpx.HTTPError, ValueError) as exc:
                return {"success": False, "error": f"Desktop bridge failed: {exc}"}

        from core.desktop.controller import desktop_controller
        method = getattr(desktop_controller, action, None)
        if action == "desktop_state":
            method = desktop_controller.desktop_state
        if method is None:
            return {"success": False, "error": f"Unsupported desktop action: {action}"}
        try:
            result = method(**params)
        except (TypeError, ValueError, OSError) as exc:
            return {"success": False, "error": f"Invalid desktop action: {exc}"}
        return {
            "success": bool(result.success),
            "result": getattr(result, "details", {}),
            "error": getattr(result, "error", ""),
        }

    @staticmethod
    def _validation_error(action: str, params: dict[str, Any]) -> str | None:
        if action == "desktop_state":
            return None if not params else "desktop_state takes no parameters"
        if action == "open_url":
            value = params.get("url")
            parsed = urlparse(value) if isinstance(value, str) else None
            if set(params) != {"url"} or not value or len(value) > 2048 or parsed.scheme not in {"http", "https"} or not parsed.netloc:
                return "A valid http/https URL is required"
        elif action == "launch_app":
            value = params.get("app_name")
            if set(params) != {"app_name"} or not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}", value):
                return "A valid application name is required"
        elif action == "click":
            if not isinstance(params.get("x"), int) or not isinstance(params.get("y"), int):
                return "Integer x and y coordinates are required"
        elif action == "type_text":
            interval = params.get("interval", 0.05)
            if not isinstance(params.get("text"), str) or len(params["text"]) > 10000:
                return "Text is required and must be at most 10000 characters"
            if not isinstance(interval, (int, float)) or interval <= 0 or interval > 10:
                return "interval must be between 0 and 10 seconds"
        elif action == "press_key":
            if not isinstance(params.get("key"), str) or not re.fullmatch(r"[A-Za-z0-9_+-]{1,32}", params["key"]):
                return "A valid key is required"
        elif action == "focus_window":
            if not isinstance(params.get("window_title"), str) or not params["window_title"].strip():
                return "A window title is required"
        else:
            return f"Unsupported desktop action: {action}"
        return None


action_engine = ActionEngine()
