"""ClipboardManager — read-only-friendly clipboard awareness."""
from __future__ import annotations

from typing import Optional


class ClipboardManager:
    """Clipboard access with a lazy pyperclip backend."""

    def __init__(self) -> None:
        self._pyperclip = None

    def _lazy_import(self):
        if self._pyperclip is None:
            try:
                import pyperclip
                self._pyperclip = pyperclip
            except ImportError:
                self._pyperclip = False
        return self._pyperclip

    def is_available(self) -> bool:
        self._lazy_import()
        return self._pyperclip is not False

    def get_text(self) -> str:
        if not self.is_available():
            return ""
        try:
            return self._pyperclip.paste() or ""
        except Exception:  # noqa: BLE001
            return ""

    def set_text(self, text: str):
        """Set clipboard text; returns an object with .success."""
        if not self.is_available():
            return _ClipboardResult(success=False, error="pyperclip unavailable")
        try:
            self._pyperclip.copy(str(text))
            return _ClipboardResult(success=True)
        except Exception as exc:  # noqa: BLE001
            return _ClipboardResult(success=False, error=str(exc))


class _ClipboardResult:
    def __init__(self, success: bool, error: str = "") -> None:
        self.success = success
        self.error = error


__all__ = ["ClipboardManager"]
