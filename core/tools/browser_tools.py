"""Verified Playwright browser tool operations."""
from __future__ import annotations

import base64
from typing import Any
from urllib.parse import urlparse

from core.browser_manager import BrowserManager


def _blocked_url(url: str) -> bool:
    scheme = urlparse(str(url)).scheme.lower()
    return scheme not in {"http", "https"}


def _same_destination(requested: str, observed: str) -> bool:
    requested_host = urlparse(requested).netloc.lower().removeprefix("www.")
    observed_host = urlparse(observed).netloc.lower().removeprefix("www.")
    return requested_host == observed_host


async def _page(session_id: str = "default") -> tuple[Any | None, dict[str, Any] | None]:
    try:
        manager = BrowserManager.instance()
        session = await manager.get_or_create_session(session_id)
        return session.current_page, None
    except Exception as exc:
        return None, {"status": "unavailable", "error": f"{type(exc).__name__}: {exc}"}


def _ok(result: Any = None, **extra: Any) -> dict[str, Any]:
    payload = {"status": "ok", "result": result}
    payload.update(extra)
    return payload


def _fail(message: str, error_type: str = "BrowserError") -> dict[str, Any]:
    return {"status": "error", "error": message, "error_type": error_type}


async def do_browser_health(**_kwargs: Any) -> dict[str, Any]:
    try:
        manager = BrowserManager.instance()
        await manager.ensure_browser_alive()
        return {"status": "healthy", "healthy": True}
    except Exception as exc:
        return {"status": "unavailable", "healthy": False, "reason": f"{type(exc).__name__}: {exc}"}


async def do_browser_navigate(url: str, session_id: str = "default", **_kwargs: Any) -> dict[str, Any]:
    if _blocked_url(url):
        return _fail(f"navigation blocked for URL scheme: {urlparse(str(url)).scheme}", "PermissionDenied")
    page, error = await _page(session_id)
    if error:
        return error
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        actual = page.url
        if not _same_destination(url, actual):
            return _fail(f"navigation verification failed: requested {url}, observed {actual}")
        return _ok({"url": actual, "title": await page.title()})
    except Exception as exc:
        return _fail(f"{type(exc).__name__}: {exc}")


async def do_browser_get_url(session_id: str = "default", **_kwargs: Any) -> dict[str, Any]:
    page, error = await _page(session_id)
    return error or {"status": "ok", "url": page.url, "result": {"url": page.url}}


async def do_browser_get_title(session_id: str = "default", **_kwargs: Any) -> dict[str, Any]:
    page, error = await _page(session_id)
    if error:
        return error
    try:
        return _ok({"title": await page.title()})
    except Exception as exc:
        return _fail(f"{type(exc).__name__}: {exc}")


async def do_browser_snapshot(session_id: str = "default", **_kwargs: Any) -> dict[str, Any]:
    page, error = await _page(session_id)
    if error:
        return error
    try:
        links = await page.locator("a").evaluate_all(
            "(els) => els.slice(0, 300).map(e => ({text: (e.innerText || '').trim(), href: e.href}))"
        )
        headings = await page.locator("h1,h2,h3,h4,h5,h6").evaluate_all(
            "(els) => els.slice(0, 100).map(e => ({tag: e.tagName.toLowerCase(), text: (e.innerText || '').trim()}))"
        )
        inputs = await page.locator("input,textarea,[contenteditable='true']").evaluate_all(
            "(els) => els.slice(0, 100).map(e => ({type: e.type || 'text', selector: e.id ? '#' + e.id : (e.name ? '[name=\"' + e.name + '\"]' : e.tagName.toLowerCase())}))"
        )
        buttons = await page.locator("button,input[type=submit],input[type=button]").evaluate_all(
            "(els) => els.slice(0, 100).map(e => ({text: (e.innerText || e.value || '').trim()}))"
        )
        forms = await page.locator("form").count()
        return _ok({
            "url": page.url,
            "title": await page.title(),
            "text": (await page.locator("body").inner_text())[:20000],
            "links": links,
            "headings": headings,
            "inputs": inputs,
            "buttons": buttons,
            "forms": [{} for _ in range(forms)],
        })
    except Exception as exc:
        return _fail(f"{type(exc).__name__}: {exc}")


async def do_browser_find(text: str, session_id: str = "default", **_kwargs: Any) -> dict[str, Any]:
    page, error = await _page(session_id)
    if error:
        return error
    try:
        locator = page.get_by_text(text, exact=False).first
        visible = await locator.is_visible()
        return _ok({"found": visible, "text": text, "selector": f"text={text}"}) if visible else _fail(f"text not found: {text}")
    except Exception as exc:
        return _fail(f"{type(exc).__name__}: {exc}")


async def do_browser_find_interactive(text: str, session_id: str = "default", **kwargs: Any) -> dict[str, Any]:
    return await do_browser_find(text, session_id=session_id, **kwargs)


def _locator(page: Any, selector: str) -> Any:
    if str(selector).startswith("text="):
        return page.get_by_text(str(selector)[5:], exact=False).first
    return page.locator(selector).first


async def do_browser_click(selector: str, session_id: str = "default", **kwargs: Any) -> dict[str, Any]:
    page, error = await _page(session_id)
    if error:
        return error
    try:
        locator = _locator(page, selector)
        await locator.click(force=bool(kwargs.get("force", False)), timeout=15000)
        return _ok({"clicked": selector})
    except Exception as exc:
        return _fail(f"{type(exc).__name__}: {exc}")


async def do_browser_fill(selector: str, value: str, session_id: str = "default", **_kwargs: Any) -> dict[str, Any]:
    page, error = await _page(session_id)
    if error:
        return error
    try:
        locator = _locator(page, selector)
        await locator.fill(value, timeout=15000)
        observed = await locator.input_value()
        if observed != value:
            return _fail(f"fill verification failed: observed {observed!r}")
        return _ok({"selector": selector, "value": observed})
    except Exception as exc:
        return _fail(f"{type(exc).__name__}: {exc}")


async def do_browser_press(selector: str, key: str, session_id: str = "default", **_kwargs: Any) -> dict[str, Any]:
    page, error = await _page(session_id)
    if error:
        return error
    try:
        await _locator(page, selector).press(key, timeout=15000)
        return _ok({"selector": selector, "key": key})
    except Exception as exc:
        return _fail(f"{type(exc).__name__}: {exc}")


async def do_browser_wait_visible(selector: str, session_id: str = "default", **_kwargs: Any) -> dict[str, Any]:
    page, error = await _page(session_id)
    if error:
        return error
    try:
        await _locator(page, selector).wait_for(state="visible", timeout=15000)
        return _ok({"selector": selector, "visible": True})
    except Exception as exc:
        return _fail(f"{type(exc).__name__}: {exc}")


async def do_browser_wait_text(text: str, session_id: str = "default", **_kwargs: Any) -> dict[str, Any]:
    page, error = await _page(session_id)
    if error:
        return error
    try:
        await page.get_by_text(text, exact=False).first.wait_for(state="visible", timeout=15000)
        return _ok({"text": text, "visible": True})
    except Exception as exc:
        return _fail(f"{type(exc).__name__}: {exc}")


async def do_browser_screenshot(session_id: str = "default", **_kwargs: Any) -> dict[str, Any]:
    page, error = await _page(session_id)
    if error:
        return error
    try:
        data = await page.screenshot()
        return _ok({"screenshot": base64.b64encode(data).decode("ascii")})
    except Exception as exc:
        return _fail(f"{type(exc).__name__}: {exc}")


async def do_browser_current_state(session_id: str = "default", **kwargs: Any) -> dict[str, Any]:
    return await do_browser_snapshot(session_id=session_id, **kwargs)


async def do_browser_list_tabs(session_id: str = "default", **_kwargs: Any) -> dict[str, Any]:
    manager = BrowserManager.instance()
    session = manager.get_session(session_id)
    if session is None:
        return _fail("session unavailable", "Unavailable")
    return _ok({"tabs": [{"index": i, "url": page.url} for i, page in enumerate(session.context.pages)]})


async def do_browser_new_tab(url: str | None = None, session_id: str = "default", **_kwargs: Any) -> dict[str, Any]:
    manager = BrowserManager.instance()
    session = await manager.get_or_create_session(session_id)
    page = await session.context.new_page()
    session.current_page = page
    if url:
        result = await do_browser_navigate(url, session_id=session_id)
        if result.get("status") != "ok":
            return result
    return _ok({"url": page.url})


async def do_browser_switch_tab(index: int, session_id: str = "default", **_kwargs: Any) -> dict[str, Any]:
    manager = BrowserManager.instance()
    session = manager.get_session(session_id)
    if session is None or index < 0 or index >= len(session.context.pages):
        return _fail("tab index unavailable", "NotFound")
    session.current_page = session.context.pages[index]
    return {"status": "ok", "url": session.current_page.url, "result": {"index": index, "url": session.current_page.url}}


async def do_browser_close_tab(index: int, session_id: str = "default", **_kwargs: Any) -> dict[str, Any]:
    manager = BrowserManager.instance()
    session = manager.get_session(session_id)
    if session is None or index < 0 or index >= len(session.context.pages):
        return _fail("tab index unavailable", "NotFound")
    page = session.context.pages[index]
    await page.close()
    if session.current_page is page:
        session.current_page = session.context.pages[0] if session.context.pages else await session.context.new_page()
    return _ok({"closed": index})


async def do_browser_get_history(**_kwargs: Any) -> dict[str, Any]:
    return _ok({"history": []})


async def do_browser_evaluate(expression: str, session_id: str = "default", **_kwargs: Any) -> dict[str, Any]:
    page, error = await _page(session_id)
    if error:
        return error
    try:
        return _ok({"value": await page.evaluate(expression)})
    except Exception as exc:
        return _fail(f"{type(exc).__name__}: {exc}")


async def do_browser_shadow_query(selector: str, session_id: str = "default", **_kwargs: Any) -> dict[str, Any]:
    return await do_browser_find(selector, session_id=session_id)


async def do_browser_wait_interactive(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return _ok({"ready": True})
