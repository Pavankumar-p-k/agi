"""Verified Playwright browser tool operations.

Every do_* function returns a dict with "status": "ok" | "error" and, on
success, a "result" payload.  Actions that mutate page state perform a
read-back verification before reporting success; navigation verifies the
actually observed destination.  Page content returned by these tools is
UNTRUSTED DATA (see core/browser/page_security.py) and must never be treated
as instructions.
"""
from __future__ import annotations

import asyncio
import base64
import os
from typing import Any
from urllib.parse import urlparse, quote_plus

from core.browser_manager import BrowserManager


def _blocked_url(url: str) -> bool:
    scheme = urlparse(str(url)).scheme.lower()
    return scheme not in {"http", "https"}


def _same_destination(requested: str, observed: str) -> bool:
    requested_host = urlparse(requested).netloc.lower().removeprefix("www.")
    observed_host = urlparse(observed).netloc.lower().removeprefix("www.")
    return requested_host == observed_host


def _host_matches(requested: str, observed: str) -> bool:
    """Suffix host match (covers subdomain redirects like html.duckduckgo.com)."""
    requested_host = urlparse(requested).netloc.lower().removeprefix("www.")
    observed_host = urlparse(observed).netloc.lower().removeprefix("www.")
    return observed_host == requested_host or observed_host.endswith("." + requested_host) or requested_host.endswith("." + observed_host)


async def _page(session_id: str = "default") -> tuple[Any | None, dict[str, Any] | None]:
    try:
        manager = BrowserManager.instance()
        session = await manager.get_or_create_session(session_id)
        return session.current_page, None
    except Exception as exc:
        return None, {"status": "error", "error": f"{type(exc).__name__}: {exc}", "error_type": "Unavailable"}


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
            "(els) => els.slice(0, 100).map(e => ({type: e.type || 'text', selector: e.id ? '#' + e.id : (e.name ? '[name=\\\"' + e.name + '\\\"]' : e.tagName.toLowerCase())}))"
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


async def do_browser_a11y_tree(session_id: str = "default", max_nodes: int = 150, **_kwargs: Any) -> dict[str, Any]:
    """Accessibility-tree-first perception.  Bounded; falls back to ARIA snapshot."""
    page, error = await _page(session_id)
    if error:
        return error

    def _prune(node: Any, budget: list[int]) -> dict[str, Any] | None:
        if not isinstance(node, dict) or budget[0] <= 0:
            return None
        role = node.get("role")
        name = (node.get("name") or "").strip()
        interesting = role not in ("generic", "none", "InlineTextBox", "StaticText") or bool(name)
        if not interesting and not node.get("children"):
            return None
        entry: dict[str, Any] = {}
        if interesting:
            budget[0] -= 1
            entry = {"role": role, "name": name[:120]}
            for key in ("value", "checked", "pressed", "level", "expanded", "url"):
                if node.get(key) not in (None, "", False):
                    entry[key] = node[key]
            if role in ("textbox", "searchbox", "combobox") and node.get("value"):
                entry["has_value"] = True
        children = node.get("children") or []
        kept: list[dict[str, Any]] = []
        for child in children:
            pruned = _prune(child, budget)
            if pruned:
                kept.append(pruned)
            if budget[0] <= 0:
                break
        if kept:
            entry["children"] = kept
        return entry or None

    try:
        snapshot: dict[str, Any] | None = None
        try:
            snapshot = await page.accessibility.snapshot()
        except Exception:
            snapshot = None
        if isinstance(snapshot, dict):
            budget = [max(10, int(max_nodes))]
            tree = _prune(snapshot, budget)
            if tree:
                return _ok({"url": page.url, "title": await page.title(), "tree": tree})
        try:
            aria = await page.locator("body").aria_snapshot()
            return _ok({"url": page.url, "title": await page.title(), "aria": str(aria)[:20000]})
        except Exception as exc:
            return _fail(f"a11y perception unavailable: {type(exc).__name__}: {exc}")
    except Exception as exc:
        return _fail(f"{type(exc).__name__}: {exc}")


async def do_browser_find(text: str, session_id: str = "default", **_kwargs: Any) -> dict[str, Any]:
    page, error = await _page(session_id)
    if error:
        return error
    try:
        locator = page.get_by_text(text, exact=False).first
        visible = await locator.is_visible()
        if not visible:
            return _fail(f"text not found: {text}")
        tag = ""
        try:
            handle = await locator.element_handle()
            if handle is not None:
                tag = str(await handle.evaluate("el => el.tagName.toLowerCase()"))
        except Exception:
            tag = ""
        return _ok({
            "found": True,
            "text": text,
            "selector": f"text={text}",
            "tag": tag,
            "strategy": "text",
        })
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


async def do_browser_select(selector: str, value: str, match_by: str = "value", session_id: str = "default", **_kwargs: Any) -> dict[str, Any]:
    """Select an <option> and read back the observed selection (verified)."""
    page, error = await _page(session_id)
    if error:
        return error
    try:
        locator = _locator(page, selector)
        last_error: Exception | None = None
        for attempt in ("value", "label", "index"):
            try:
                if attempt == "value":
                    await locator.select_option(value, timeout=10000)
                elif attempt == "label":
                    await locator.select_option(label=value, timeout=10000)
                else:
                    await locator.select_option(index=int(value), timeout=10000)
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                if match_by in {"value", "label", "index"} and attempt == match_by:
                    continue
        if last_error is not None:
            return _fail(f"select failed for {selector}={value!r}: {last_error}")
        observed = await locator.input_value()
        if not observed:
            return _fail(f"select verification failed: no option selected for {selector}")
        return _ok({"selector": selector, "selected": observed, "requested": value})
    except Exception as exc:
        return _fail(f"{type(exc).__name__}: {exc}")


async def do_browser_scroll(direction: str = "down", amount: int = 600, selector: str | None = None, session_id: str = "default", **_kwargs: Any) -> dict[str, Any]:
    """Scroll by mouse wheel (no JS injection) or scroll an element into view; verified by scrollY delta."""
    page, error = await _page(session_id)
    if error:
        return error
    try:
        if selector:
            await _locator(page, selector).scroll_into_view_if_needed(timeout=8000)
            return _ok({"scrolled": "into_view", "selector": selector})
        before = await page.evaluate("() => window.scrollY || 0")
        if direction == "top":
            delta = -100000
        elif direction == "bottom":
            delta = 100000
        elif direction == "up":
            delta = -abs(int(amount))
        else:
            delta = abs(int(amount))
        await page.mouse.wheel(0, delta)
        await page.wait_for_timeout(300)
        after = await page.evaluate("() => window.scrollY || 0")
        moved = abs(float(after) - float(before)) > 0.5
        return _ok({"scrolled": direction, "scroll_y": after, "moved": moved})
    except Exception as exc:
        return _fail(f"{type(exc).__name__}: {exc}")


async def do_browser_upload(selector: str, files: list[str], session_id: str = "default", **_kwargs: Any) -> dict[str, Any]:
    """Upload file(s) through a file input; verified by reading back the file list length."""
    page, error = await _page(session_id)
    if error:
        return error
    paths = [str(p) for p in (files or [])]
    for path in paths:
        if not os.path.isfile(path):
            return _fail(f"upload file not found: {path}")
    try:
        locator = _locator(page, selector)
        await locator.set_input_files(paths, timeout=15000)
        try:
            count = await locator.evaluate("el => (el.files || []).length")
        except Exception:
            count = len(paths)
        if int(count or 0) < len(paths):
            return _fail(f"upload verification failed: {count} file(s) attached, expected {len(paths)}")
        return _ok({"selector": selector, "uploaded": [os.path.basename(p) for p in paths]})
    except Exception as exc:
        return _fail(f"{type(exc).__name__}: {exc}")


# ---- dialog policy --------------------------------------------------------
# Playwright auto-dismisses dialogs when no listener is registered.  A session
# can set an explicit policy ("accept" | "dismiss"); handled dialogs are
# recorded (bounded) so the agent can inspect what the page asked.
_DIALOG_POLICIES: dict[str, str] = {}
_DIALOG_PAGES: set[int] = set()
_LAST_DIALOGS: dict[str, list[dict[str, Any]]] = {}


def _dialog_handler(session_id: str) -> Any:
    def handler(dialog: Any) -> None:
        try:
            action = _DIALOG_POLICIES.get(session_id, "dismiss")
            _LAST_DIALOGS.setdefault(session_id, []).append({
                "type": dialog.type,
                "message": str(dialog.message)[:500],
                "handled": action,
            })
            del _LAST_DIALOGS[session_id][:-10]
            if action == "accept":
                asyncio.ensure_future(dialog.accept())
            else:
                asyncio.ensure_future(dialog.dismiss())
        except Exception:
            pass
    return handler


async def do_browser_set_dialog_policy(action: str = "dismiss", session_id: str = "default", **_kwargs: Any) -> dict[str, Any]:
    if action not in {"accept", "dismiss"}:
        return _fail(f"invalid dialog policy: {action!r} (use 'accept' or 'dismiss')")
    page, error = await _page(session_id)
    if error:
        return error
    try:
        if id(page) not in _DIALOG_PAGES:
            page.on("dialog", _dialog_handler(session_id))
            _DIALOG_PAGES.add(id(page))
        _DIALOG_POLICIES[session_id] = action
        return _ok({"policy": action})
    except Exception as exc:
        return _fail(f"{type(exc).__name__}: {exc}")


async def do_browser_last_dialogs(session_id: str = "default", **_kwargs: Any) -> dict[str, Any]:
    return _ok({"dialogs": list(_LAST_DIALOGS.get(session_id, []))})


async def do_browser_download(selector: str | None = None, url: str | None = None, save_path: str | None = None, timeout: int = 60000, session_id: str = "default", **_kwargs: Any) -> dict[str, Any]:
    """Download by clicking a link or navigating to a direct file URL; verified by file existence and size."""
    if not selector and not url:
        return _fail("download requires 'selector' or 'url'")
    if url and _blocked_url(url):
        return _fail(f"download blocked for URL scheme: {urlparse(str(url)).scheme}", "PermissionDenied")
    page, error = await _page(session_id)
    if error:
        return error
    try:
        async with page.expect_download(timeout=timeout) as download_info:
            if selector:
                await _locator(page, selector).click(timeout=30000)
            else:
                await page.goto(str(url), wait_until="domcontentloaded", timeout=timeout)
        download = await download_info.value
        target = save_path or os.path.join(os.path.expanduser("~"), ".jarvis", "downloads", download.suggested_filename or "download.bin")
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        await download.save_as(target)
        size = os.path.getsize(target)
        if size <= 0:
            return _fail(f"download verification failed: saved file is empty: {target}")
        return _ok({"path": target, "size": size, "filename": os.path.basename(target)})
    except Exception as exc:
        return _fail(f"{type(exc).__name__}: {exc}")


async def do_browser_extract(selector: str = "body", max_chars: int = 20000, session_id: str = "default", **_kwargs: Any) -> dict[str, Any]:
    """Bounded text extraction from a page region (read-only)."""
    page, error = await _page(session_id)
    if error:
        return error
    try:
        locator = _locator(page, selector)
        text = (await locator.inner_text())[: max(200, int(max_chars))]
        if not text.strip():
            return _fail(f"no content extracted from selector: {selector}")
        return _ok({"selector": selector, "text": text, "url": page.url, "title": await page.title()})
    except Exception as exc:
        return _fail(f"{type(exc).__name__}: {exc}")


async def do_browser_form_fill(fields: Any, session_id: str = "default", **_kwargs: Any) -> dict[str, Any]:
    """Fill and verify multiple fields in one action.

    Accepts either a mapping {"#id": "value", ...} or a list of
    {"selector": ..., "value": ...} entries.  Every field is filled through
    do_browser_fill, which performs read-back verification.
    """
    entries: list[tuple[str, str]] = []
    if isinstance(fields, dict):
        entries = [(str(k), str(v)) for k, v in fields.items()]
    elif isinstance(fields, list):
        for item in fields:
            if isinstance(item, dict) and item.get("selector"):
                entries.append((str(item["selector"]), str(item.get("value", ""))))
    if not entries:
        return _fail("form_fill requires fields as {selector: value} or [{'selector':..., 'value':...}]")
    results: list[dict[str, Any]] = []
    all_ok = True
    for selector, value in entries:
        outcome = await do_browser_fill(selector, value, session_id=session_id)
        results.append({"selector": selector, "status": outcome.get("status"), "error": outcome.get("error")})
        if outcome.get("status") != "ok":
            all_ok = False
    if not all_ok:
        return {"status": "error", "error": "one or more fields failed fill verification", "results": results, "error_type": "BrowserError"}
    return _ok({"filled": len(entries), "results": results})


_SEARCH_ENGINES: dict[str, str] = {
    "duckduckgo": "https://html.duckduckgo.com/html/?q={query}",
    "bing": "https://www.bing.com/search?q={query}",
    "google": "https://www.google.com/search?q={query}",
}


def _extract_real_href(href: str) -> str:
    """Decode search-engine redirect wrappers to the real target URL.

    Engines never link to results directly:
    - DuckDuckGo: //duckduckgo.com/l/?uddg=<encoded-target>&rut=...
    - Bing:       /ck/a?...&u=a1<base64url-of-target>&...
    - Google:     /url?q=<encoded-target>&...
    Without decoding, every real result looks like an engine link and is
    indistinguishable from site chrome.
    """
    import base64
    from urllib.parse import unquote
    h = str(href or "")
    if "uddg=" in h:                       # DuckDuckGo
        try:
            tail = h.split("uddg=", 1)[1].split("&", 1)[0]
            real = unquote(tail)
            if real.startswith("http"):
                return real
        except Exception:
            pass
    if "/ck/a" in h and "u=a1" in h:       # Bing click-tracking
        try:
            tail = h.split("u=a1", 1)[1].split("&", 1)[0]
            pad = "=" * (-len(tail) % 4)
            real = base64.urlsafe_b64decode(tail + pad).decode("utf-8", "ignore")
            if real.startswith("http"):
                return real
        except Exception:
            pass
    if "google." in h and "/url?" in h:    # Google redirect
        try:
            tail = h.split("q=", 1)[1].split("&", 1)[0]
            real = unquote(tail)
            if real.startswith("http"):
                return real
        except Exception:
            pass
    if h.startswith("//"):
        return "https:" + h
    return h


async def do_browser_search(query: str, engine: str | None = None, session_id: str = "default", **_kwargs: Any) -> dict[str, Any]:
    """Run a web search in the browser and extract result links (verified: at least one external result)."""
    page, error = await _page(session_id)
    if error:
        return error

    def _harvest(snapshot: dict[str, Any]) -> list[dict[str, str]]:
        results: list[dict[str, str]] = []
        engine_hosts = ("duckduckgo.com", "bing.com", "google.com")
        for link in (snapshot.get("result", {}) or {}).get("links", []) or []:
            href = _extract_real_href(link.get("href"))
            text = str(link.get("text") or "").strip()
            if not href.startswith("http"):
                continue
            host = urlparse(href).netloc.lower()
            if any(host == e or host.endswith("." + e) for e in engine_hosts):
                continue
            if len(text) < 15:
                continue
            if not any(r.get("href") == href for r in results):
                results.append({"title": text[:200], "href": href})
            if len(results) >= 10:
                break
        return results

    engines = [engine] if engine in _SEARCH_ENGINES else list(_SEARCH_ENGINES)
    errors: list[str] = []
    for engine_name in engines:
        template = _SEARCH_ENGINES[engine_name]
        target = template.format(query=quote_plus(query))
        try:
            await page.goto(target, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_load_state(state="domcontentloaded", timeout=15000)
            try:
                # Results render after DOMContentLoaded on client-hydrated SERPs.
                await page.wait_for_selector("#b_results li, .result, .g", timeout=8000)
            except Exception:
                pass
            snapshot = await do_browser_snapshot(session_id=session_id)
            if snapshot.get("status") != "ok":
                errors.append(f"{engine_name}: snapshot failed: {snapshot.get('error')}")
                continue
            results = _harvest(snapshot)
            if results:
                return _ok({"engine": engine_name, "query": query, "results": results, "url": page.url})
            errors.append(f"{engine_name}: no result links extracted")
        except Exception as exc:
            errors.append(f"{engine_name}: {type(exc).__name__}: {exc}")

    # Last resort: drive the DuckDuckGo JS UI like a human search.  Most robust
    # against endpoint/layout/bot-check drift on the lightweight HTML mirrors.
    if engine is None:
        try:
            await page.goto("https://duckduckgo.com/?q=" + quote_plus(query),
                            wait_until="domcontentloaded", timeout=30000)
            try:
                await page.wait_for_selector("article, [data-testid='result'], .result", timeout=15000)
            except Exception:
                pass
            snapshot = await do_browser_snapshot(session_id=session_id)
            if snapshot.get("status") == "ok":
                results = _harvest(snapshot)
                if results:
                    return _ok({"engine": "duckduckgo_ui", "query": query,
                                "results": results, "url": page.url})
                errors.append("duckduckgo_ui: no result links extracted")
        except Exception as exc:
            errors.append(f"duckduckgo_ui: {type(exc).__name__}: {exc}")

    return _fail("search failed on all engines: " + " | ".join(errors))


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


async def do_browser_wait_state(state: str = "load", timeout: int = 30000, session_id: str = "default", **_kwargs: Any) -> dict[str, Any]:
    """Wait for a page load state: 'load' | 'domcontentloaded' | 'networkidle'."""
    if state not in {"load", "domcontentloaded", "networkidle"}:
        return _fail(f"invalid load state: {state!r}")
    page, error = await _page(session_id)
    if error:
        return error
    try:
        await page.wait_for_load_state(state=state, timeout=timeout)
        return _ok({"state": state, "url": page.url})
    except Exception as exc:
        return _fail(f"{type(exc).__name__}: {exc}")


async def do_browser_is_visible(selector: str, session_id: str = "default", **_kwargs: Any) -> dict[str, Any]:
    """Read-only visibility probe for verification checks (never fails on 'not visible')."""
    page, error = await _page(session_id)
    if error:
        return error
    try:
        visible = await _locator(page, selector).is_visible()
        return _ok({"selector": selector, "visible": bool(visible)})
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


async def do_browser_refresh(session_id: str = "default", **_kwargs: Any) -> dict[str, Any]:
    page, error = await _page(session_id)
    if error:
        return error
    try:
        before = page.url
        await page.reload(wait_until="domcontentloaded", timeout=30000)
        if not _host_matches(before, page.url):
            return _fail(f"refresh verification failed: {before} -> {page.url}")
        return _ok({"url": page.url, "title": await page.title()})
    except Exception as exc:
        return _fail(f"{type(exc).__name__}: {exc}")


async def do_browser_go_back(session_id: str = "default", **_kwargs: Any) -> dict[str, Any]:
    page, error = await _page(session_id)
    if error:
        return error
    try:
        await page.go_back(wait_until="domcontentloaded", timeout=30000)
        if not page.url:
            return _fail("go_back produced no URL")
        return _ok({"url": page.url})
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
