"""
Module: core.workspace.browser_context
Browser context awareness - detects open browser windows and tabs.
"""
from __future__ import annotations
from typing import Any
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class BrowserTab:
    title: str = ""
    url: str = ""
    index: int = 0


class BrowserContextAwareness:
    def __init__(self) -> None:
        logger.info("BrowserContextAwareness initialized")

    def detect_browsers(self) -> dict[str, list[dict[str, Any]]]:
        try:
            import pygetwindow as gw
            browsers = {}
            for w in gw.getAllWindows():
                title = w.title.strip()
                if not title:
                    continue
                lower = title.lower()
                detected_name = None
                for bname in ["chrome", "firefox", "edge", "brave", "opera", "vivaldi", "safari"]:
                    if bname in lower:
                        detected_name = bname
                        break
                if detected_name:
                    browsers.setdefault(detected_name, []).append({
                        "title": title,
                        "left": w.left,
                        "top": w.top,
                        "width": w.width,
                        "height": w.height,
                        "isActive": w.isActive,
                    })
            return browsers
        except Exception as e:
            logger.error("detect_browsers failed: %s", e)
            return {}

    def snapshot(self) -> dict[str, Any]:
        browsers = self.detect_browsers()
        return {
            "browsers": browsers,
            "total_browser_windows": sum(len(v) for v in browsers.values()),
        }
