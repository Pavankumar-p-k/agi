"""
Module: core.workspace.clipboard_manager
Real clipboard management using pyperclip.
"""
from __future__ import annotations
from typing import Any
from dataclasses import dataclass, field
import logging
import pyperclip

logger = logging.getLogger(__name__)


@dataclass
class ClipboardResult:
    success: bool = False
    error: str = ""
    content: str = ""


class ClipboardManager:
    def __init__(self) -> None:
        logger.info("ClipboardManager initialized")

    def get_text(self) -> str:
        try:
            return pyperclip.paste()
        except Exception as e:
            logger.error("get_text failed: %s", e)
            return ""

    def set_text(self, text: str) -> ClipboardResult:
        try:
            pyperclip.copy(text)
            return ClipboardResult(success=True, content=text)
        except Exception as e:
            return ClipboardResult(error=str(e))

    def write(self, text: str) -> ClipboardResult:
        return self.set_text(text)

    def read(self) -> str:
        return self.get_text()

    def clear(self) -> ClipboardResult:
        try:
            pyperclip.copy("")
            return ClipboardResult(success=True, content="")
        except Exception as e:
            return ClipboardResult(error=str(e))
