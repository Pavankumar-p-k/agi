from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class ClipboardManager:
    def __init__(self) -> None:
        self._pyperclip: object | None = None

    def _lazy_import(self) -> None:
        if self._pyperclip is not None:
            return
        try:
            import pyperclip
            self._pyperclip = pyperclip
        except ImportError:
            self._pyperclip = False

    def get_text(self) -> str:
        self._lazy_import()
        if not self._pyperclip:
            return ""
        try:
            return self._pyperclip.paste() or ""
        except Exception as e:
            logger.debug("ClipboardManager.get_text failed: %s", e)
            return ""

    def set_text(self, text: str) -> bool:
        self._lazy_import()
        if not self._pyperclip:
            return False
        try:
            self._pyperclip.copy(text)
            return True
        except Exception as e:
            logger.debug("ClipboardManager.set_text failed: %s", e)
            return False

    def is_available(self) -> bool:
        self._lazy_import()
        return bool(self._pyperclip)
