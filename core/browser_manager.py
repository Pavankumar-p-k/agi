from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
BROWSER_DATA_DIR = DATA_DIR / "browser_sessions"
DOWNLOADS_DIR = DATA_DIR / "downloads"
SESSION_TIMEOUT = 1800
CLEANUP_INTERVAL = 60


@dataclass
class BrowserSession:
    session_id: str
    context: Any = None
    pages: list = field(default_factory=list)
    current_page_index: int = 0
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    history: list[str] = field(default_factory=list)
    action_history: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    logged_in: bool = False
    login_username: str | None = None
    login_domain: str | None = None
    storage_path: Path | None = None

    @property
    def current_page(self):
        if not self.pages:
            return None
        return self.pages[self.current_page_index]


class BrowserManager:
    _instance: BrowserManager | None = None
    _playwright = None
    _browser = None
    _sessions: dict[str, BrowserSession] = {}
    _cleanup_task: asyncio.Task | None = None
    _started: bool = False

    def __init__(self):
        pass

    @classmethod
    def instance(cls) -> BrowserManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def start(self):
        if self._started:
            return
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("playwright not installed — run: playwright install chromium")
            raise
        from core.config_registry import config
        bc = config.browser
        self._playwright_obj = await async_playwright().start()
        headless = not bc.headed
        self._browser = await self._playwright_obj.chromium.launch(headless=headless)
        self._started = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("[BrowserManager] started (headless=%s)", headless)

    async def stop(self):
        self._started = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            self._cleanup_task = None
        for sid in list(self._sessions):
            await self.close_session(sid)
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright_obj:
            await self._playwright_obj.stop()
            self._playwright_obj = None
        logger.info("[BrowserManager] stopped")

    async def _cleanup_loop(self):
        while self._started:
            await asyncio.sleep(CLEANUP_INTERVAL)
            now = time.time()
            for sid, session in list(self._sessions.items()):
                if now - session.last_used > SESSION_TIMEOUT:
                    logger.info("[BrowserManager] cleaning idle session: %s", sid)
                    await self.save_storage(sid)
                    await self.close_session(sid)

    async def ensure_browser_alive(self):
        if not self._started or not self._browser:
            await self.start()
        try:
            contexts = self._browser.contexts
        except Exception:
            logger.warning("[BrowserManager] browser dead, restarting")
            await self.stop()
            await self.start()

    async def ensure_context_alive(self, context) -> Any:
        if context is None:
            raise RuntimeError("ContextClosed: browser context is None")
        try:
            _ = context.pages
            return context
        except Exception as e:
            raise RuntimeError(f"ContextClosed: {e}") from e

    async def ensure_page_alive(self, page) -> Any:
        if page is None:
            raise RuntimeError("PageClosed: page is None")
        try:
            _ = await page.title()
            return page
        except Exception as e:
            raise RuntimeError(f"PageClosed: {e}") from e

    async def get_or_create_session(self, session_id: str) -> BrowserSession:
        if session_id in self._sessions:
            session = self._sessions[session_id]
            session.last_used = time.time()
            return session
        await self.ensure_browser_alive()
        storage_path = BROWSER_DATA_DIR / session_id / "state.json"
        storage_state = None
        if storage_path.exists():
            try:
                import json
                with open(storage_path) as f:
                    storage_state = json.load(f)
            except Exception as e:
                logger.warning("[BrowserManager] failed to load storage state: %s", e)
        context = await self._browser.new_context(
            storage_state=storage_state,
            viewport={"width": 1280, "height": 720},
        )
        page = await context.new_page()
        session = BrowserSession(
            session_id=session_id,
            context=context,
            pages=[page],
            current_page_index=0,
            storage_path=storage_path,
        )
        self._sessions[session_id] = session
        logger.info("[BrowserManager] created session: %s", session_id)
        return session

    async def save_storage(self, session_id: str):
        session = self._sessions.get(session_id)
        if not session or not session.context:
            return
        try:
            state_dir = BROWSER_DATA_DIR / session_id
            state_dir.mkdir(parents=True, exist_ok=True)
            state_path = state_dir / "state.json"
            await session.context.storage_state(path=str(state_path))
            logger.info("[BrowserManager] saved storage for session: %s", session_id)
        except Exception as e:
            logger.warning("[BrowserManager] save_storage failed: %s", e)

    async def close_session(self, session_id: str):
        session = self._sessions.pop(session_id, None)
        if session is None:
            return
        try:
            if session.context:
                await session.context.close()
        except Exception as e:
            logger.warning("[BrowserManager] close_session context error: %s", e)
        logger.info("[BrowserManager] closed session: %s", session_id)

    def get_session(self, session_id: str) -> BrowserSession | None:
        return self._sessions.get(session_id)

    async def list_tabs(self, session_id: str) -> list[dict]:
        session = self._sessions.get(session_id)
        if not session:
            return []
        result = []
        for i, p in enumerate(session.pages):
            try:
                url = p.url
                title = await p.title()
            except Exception:
                url = ""
                title = ""
            result.append({"index": i, "url": url, "title": title}) if url else None
        return result

    async def switch_tab(self, session_id: str, index: int) -> dict:
        session = self._sessions.get(session_id)
        if not session:
            return {"status": "error", "error": "Session not found"}
        if index < 0 or index >= len(session.pages):
            return {"status": "error", "error": f"Tab index {index} out of range"}
        session.current_page_index = index
        page = session.pages[index]
        try:
            await page.bring_to_front()
        except Exception:
            pass
        return {"status": "ok", "tab_index": index, "url": page.url}

    async def new_tab(self, session_id: str, url: str | None = None) -> dict:
        session = self._sessions.get(session_id)
        if not session:
            return {"status": "error", "error": "Session not found"}
        page = await session.context.new_page()
        if url:
            await page.goto(url, timeout=30000)
        session.pages.append(page)
        session.current_page_index = len(session.pages) - 1
        return {"status": "ok", "tab_index": session.current_page_index, "url": page.url}

    async def close_tab(self, session_id: str, index: int) -> dict:
        session = self._sessions.get(session_id)
        if not session:
            return {"status": "error", "error": "Session not found"}
        if index < 0 or index >= len(session.pages):
            return {"status": "error", "error": f"Tab index {index} out of range"}
        page = session.pages.pop(index)
        await page.close()
        if not session.pages:
            new_page = await session.context.new_page()
            session.pages.append(new_page)
        if session.current_page_index >= len(session.pages):
            session.current_page_index = len(session.pages) - 1
        return {"status": "ok", "tab_index": index, "closed": True}
