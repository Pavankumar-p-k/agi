"""Browser process/session manager over Playwright (rebuilt in STEP 4).

Why this rebuild
----------------
The previous file was a 12-line ``FAKE-SUCCESS``: ``start()``/``stop()`` were
``pass`` and ``new_page()`` returned ``None``, while ``browser_tools`` (627 LOC,
rated REAL) hard-imported it. That produced the two worst scorecard rows:

* ``browser`` agent -> FAKE-SUCCESS (reported "0 open tab(s)" in 0.0s and
  claimed success without ever launching a browser),
* ``core/tools/browser_tools`` -> UNTESTABLE (``ModuleNotFoundError:
  No module named 'core.browser_manager'`` after STEP 2).

Pinned specs
------------
Call surface (grepped from ``core/tools/browser_tools.py`` and
``tests/acceptance/*``)::

    BrowserManager.instance()                     -> singleton
    await bm.start(headed=...) ; await bm.stop()  ; bm._started
    await bm.ensure_browser_alive()
    bm.get_session(id)                            -> session | None
    await bm.get_or_create_session(id)            -> session
    await bm.close_session(id)
    await bm.save_storage(id)
    await bm.ensure_context_alive(ctx)            -> ctx
    await bm.ensure_page_alive(page)              -> page

    session.session_id / session.context / session.current_page  (settable)

``browser_tools`` reads ``session.current_page`` synchronously after
``get_or_create_session``, so the page must exist by the time the coroutine
returns — no lazy property that yields ``None``.

Failure policy: every method raises a clear exception when Playwright cannot
start (missing browser binary, sandbox denial). It never returns a hollow
object pretending to be a live browser — that is the exact failure mode this
module was deleted for.
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

__all__ = ["BrowserManager", "BrowserSession"]

_DEFAULT_TIMEOUT_MS = 45000
_STORAGE_DIR = os.path.join("data", "browser_state")


@dataclass
class BrowserSession:
    """One logical browsing session: a context plus its active page."""

    session_id: str
    context: Any = None
    current_page: Any = None
    created_at: float = 0.0
    storage_path: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def alive(self) -> bool:
        return self.context is not None and self.current_page is not None


class BrowserManager:
    """Owns the Playwright browser process and the sessions inside it."""

    _instance: Optional["BrowserManager"] = None

    def __init__(self) -> None:
        self._started = False
        self._headed = False
        self._browser: Any = None
        self._playwright: Any = None
        self._sessions: Dict[str, BrowserSession] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------ singleton
    @classmethod
    def instance(cls) -> "BrowserManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Testing hook — drops the singleton (without closing it)."""
        cls._instance = None

    # ------------------------------------------------------------- lifecycle
    def _headed_default(self) -> bool:
        try:
            from core.configuration import configuration
            return bool(configuration.get("browser.headed", False))
        except Exception:  # noqa: BLE001 — config optional
            return False

    async def start(self, headed: Optional[bool] = None, **_kwargs: Any) -> Any:
        """Launch Playwright + Chromium. Raises if the browser cannot start."""
        async with self._lock:
            if self._started and self._browser is not None:
                return self._browser
            self._headed = self._headed_default() if headed is None else bool(headed)

            try:
                from playwright.async_api import async_playwright
            except ImportError as exc:
                raise RuntimeError(
                    "playwright is not installed — `pip install playwright && "
                    "playwright install chromium`"
                ) from exc

            try:
                if self._playwright is None:
                    self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(
                    headless=not self._headed,
                    args=["--disable-blink-features=AutomationControlled"]
                    if self._headed else [],
                )
            except Exception as exc:  # noqa: BLE001 — surface the real cause
                self._browser = None
                self._started = False
                raise RuntimeError(
                    f"chromium failed to launch: {type(exc).__name__}: {exc}"
                ) from exc

            self._started = True
            logger.info("browser started (headed=%s)", self._headed)
            return self._browser

    async def stop(self) -> None:
        """Close sessions then the browser. Safe to call repeatedly."""
        async with self._lock:
            for sid in list(self._sessions):
                await self._close_session_locked(sid)
            browser, pw = self._browser, self._playwright
            self._browser = None
            self._playwright = None
            self._started = False
        if browser is not None:
            try:
                await browser.close()
            except Exception:  # noqa: BLE001 — already dead is fine
                logger.debug("browser close failed", exc_info=True)
        if pw is not None:
            try:
                await pw.stop()
            except Exception:  # noqa: BLE001
                logger.debug("playwright stop failed", exc_info=True)

    # ------------------------------------------------------------- liveness
    async def ensure_browser_alive(self, headed: Optional[bool] = None) -> Any:
        """Return a live browser, relaunching it if the process died."""
        if self._started and self._browser is not None:
            try:
                if not self._browser.is_connected():
                    raise RuntimeError("browser disconnected")
                return self._browser
            except Exception:  # noqa: BLE001 — fall through to relaunch
                logger.warning("browser lost connection; relaunching")
                self._started = False
        browser = await self.start(headed=headed)
        # A relaunch invalidates every existing context/page.
        self._sessions.clear()
        return browser

    async def ensure_context_alive(self, context: Any) -> Any:
        """Return a usable context, creating a fresh one if *context* died."""
        if context is not None:
            try:
                _ = context.pages  # raises if the context was closed
                return context
            except Exception:  # noqa: BLE001 — dead object falls through
                pass
        browser = await self.ensure_browser_alive()
        return await browser.new_context(
            viewport={"width": 1440, "height": 900},
            ignore_https_errors=True,
        )

    async def ensure_page_alive(self, page: Any) -> Any:
        """Return a usable page, opening a new tab if *page* is gone."""
        if page is not None:
            try:
                _ = page.url  # raises if the page was closed
                return page
            except Exception:  # noqa: BLE001
                logger.debug("page closed; opening a new one")
        context = await self.ensure_context_alive(None)
        pages = getattr(context, "pages", None) or []
        if pages:
            return pages[0]
        return await context.new_page()

    # ------------------------------------------------------------- sessions
    def get_session(self, session_id: str) -> Optional[BrowserSession]:
        return self._sessions.get(session_id)

    async def get_or_create_session(self, session_id: str = "default",
                                    **_kwargs: Any) -> BrowserSession:
        """Return a session whose context *and* current_page are both live."""
        existing = self._sessions.get(session_id)
        if existing is not None and existing.alive:
            try:
                _ = existing.current_page.url
                return existing
            except Exception:  # noqa: BLE001 — page/context died
                logger.debug("session %s stale; rebuilding", session_id)

        await self.ensure_browser_alive()

        if existing is not None and existing.context is not None:
            try:
                context = await self.ensure_context_alive(existing.context)
            except Exception:  # noqa: BLE001
                context = await self._browser.new_context(
                    viewport={"width": 1440, "height": 900},
                    ignore_https_errors=True,
                )
        else:
            try:
                context = await self._browser.new_context(
                    viewport={"width": 1440, "height": 900},
                    ignore_https_errors=True,
                )
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(
                    f"could not create browser context: {type(exc).__name__}: {exc}"
                ) from exc

        context.set_default_timeout(_DEFAULT_TIMEOUT_MS)
        pages = getattr(context, "pages", None) or []
        page = pages[0] if pages else await context.new_page()

        session = self._sessions.get(session_id)
        if session is None:
            session = BrowserSession(session_id=session_id)
            self._sessions[session_id] = session
        session.context = context
        session.current_page = page
        return session

    async def _close_session_locked(self, session_id: str) -> bool:
        session = self._sessions.pop(session_id, None)
        if session is None:
            return False
        try:
            if session.context is not None:
                await session.context.close()
        except Exception:  # noqa: BLE001 — already closed
            logger.debug("context close failed for %s", session_id, exc_info=True)
        return True

    async def close_session(self, session_id: str) -> bool:
        async with self._lock:
            return await self._close_session_locked(session_id)

    async def save_storage(self, session_id: str) -> Optional[str]:
        """Persist a session's cookies/localStorage to disk. Returns the path."""
        session = self._sessions.get(session_id)
        if session is None or session.context is None:
            logger.warning("save_storage: no live session %r", session_id)
            return None
        try:
            os.makedirs(_STORAGE_DIR, exist_ok=True)
            path = os.path.join(_STORAGE_DIR, f"{session_id}.json")
            await session.context.storage_state(path=path)
            session.storage_path = path
            return path
        except Exception as exc:  # noqa: BLE001 — report, don't pretend
            logger.error("save_storage failed for %s: %s", session_id, exc)
            raise

    # ------------------------------------------------------------- helpers
    @property
    def started(self) -> bool:
        return self._started

    def session_ids(self) -> list[str]:
        return list(self._sessions)
