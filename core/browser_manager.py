"""Browser manager for web automation."""
from __future__ import annotations
from typing import Any


class BrowserManager:
    def __init__(self, **kwargs):
        self.options = kwargs

    async def start(self):
        pass

    async def stop(self):
        pass

    async def new_page(self) -> Any:
        return None
