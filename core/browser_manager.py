"""Bounded Playwright browser lifecycle and session management."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class BrowserSession:
    session_id: str
    context: Any
    current_page: Any


class BrowserManager:
    _instance: "BrowserManager | None" = None

    def __init__(self, **kwargs: Any):
        self.options = kwargs
        self._started = False
        self._playwright = None
        self.browser = None
        self._sessions: dict[str, BrowserSession] = {}

    @classmethod
    def instance(cls) -> "BrowserManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def start(self, headed: bool = False) -> None:
        if self._started:
            return
        from playwright.async_api import async_playwright
        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch(headless=not headed)
        self._started = True

    async def ensure_browser_alive(self) -> None:
        if not self._started or self.browser is None:
            await self.start()

    async def stop(self) -> None:
        for session in list(self._sessions.values()):
            await session.context.close()
        self._sessions.clear()
        if self.browser is not None:
            await self.browser.close()
        if self._playwright is not None:
            await self._playwright.stop()
        self.browser = None
        self._playwright = None
        self._started = False

    async def close_session(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session is not None:
            await session.context.close()

    async def save_storage(self, session_id: str) -> dict[str, Any]:
        session = self._sessions.get(session_id)
        if session is None:
            raise RuntimeError("browser session is unavailable")
        return await session.context.storage_state()

    async def get_or_create_session(self, session_id: str) -> BrowserSession:
        await self.ensure_browser_alive()
        existing = self._sessions.get(session_id)
        if existing is not None:
            return existing
        context = await self.browser.new_context()
        page = await context.new_page()
        session = BrowserSession(session_id, context, page)
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> BrowserSession | None:
        return self._sessions.get(session_id)

    async def ensure_context_alive(self, context: Any) -> Any:
        return context

    async def ensure_page_alive(self, page: Any) -> Any:
        if page is None or page.is_closed():
            for session in self._sessions.values():
                if session.current_page is page:
                    session.current_page = await session.context.new_page()
                    return session.current_page
            raise RuntimeError("browser page is unavailable")
        return page

    async def new_page(self) -> Any:
        session = await self.get_or_create_session("default")
        page = await session.context.new_page()
        session.current_page = page
        return page
