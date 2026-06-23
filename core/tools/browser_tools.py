from __future__ import annotations

import base64
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

DANGEROUS_SCHEMES = ("file://", "chrome://", "edge://", "about:", "javascript:", "data:")


def _validate_url(url: str, is_admin: bool = False) -> str:
    url = url.strip()
    if not url:
        raise ValueError("URL is empty")
    if not url.startswith(("http://", "https://")):
        if not is_admin and any(url.lower().startswith(s) for s in DANGEROUS_SCHEMES):
            raise PermissionError(
                f"Navigation to '{url.split(':')[0]}://' is blocked for non-admin users"
            )
        url = f"https://{url}"
    return url


async def _resolve_selector(page, selector: str, timeout: int = 10000):
    locator = page.locator(selector).first
    await locator.wait_for(state="attached", timeout=timeout)
    return locator


def _action_result(tool: str, url: str, title: str, result=None, error=None, error_type=None, selector=None):
    d = {
        "status": "error" if error else "ok",
        "tool": tool,
        "url": url or "",
        "title": title or "",
    }
    if result is not None:
        d["result"] = result
    if error:
        d["error"] = error
    if error_type:
        d["error_type"] = error_type
    if selector:
        d["selector"] = selector
    return d


def _update_session_memory(session_id: str, url: str, title: str, action: str):
    try:
        from core.routing.project_context import get_context_manager
        cm = get_context_manager()
        mem = cm.get_session(session_id)
        if url:
            mem.browser_last_url = url
        if title:
            mem.browser_last_title = title
        mem.browser_last_action = action
        if url and (not mem.browser_history or mem.browser_history[-1] != url):
            mem.browser_history.append(url)
    except Exception as e:
        logger.debug("_update_session_memory failed: %s", e)


def _record_action(session, tool, url, selector, status):
    if session is None:
        return
    session.action_history.append({
        "timestamp": time.time(),
        "tool": tool,
        "url": url or "",
        "selector": selector or "",
        "status": status,
    })
    session.last_used = time.time()


def _bm():
    from core.browser_manager import BrowserManager
    return BrowserManager.instance()


async def _ensure(session_id: str):
    bm = _bm()
    await bm.ensure_browser_alive()
    session = bm.get_session(session_id)
    if session is None:
        session = await bm.get_or_create_session(session_id)
    await bm.ensure_context_alive(session.context)
    page = await bm.ensure_page_alive(session.current_page)
    return bm, session, page


async def do_browser_navigate(url: str, session_id: str = None, is_admin: bool = False) -> dict:
    try:
        url = _validate_url(url, is_admin=is_admin)
    except (ValueError, PermissionError) as e:
        et = "PermissionDenied" if isinstance(e, PermissionError) else "ValidationError"
        return _action_result("browser_navigate", "", "", error=str(e), error_type=et)
    try:
        bm, session, page = await _ensure(session_id)
        try:
            await page.goto(url, timeout=30000, wait_until="load")
        except Exception:
            try:
                await page.goto(url, timeout=10000, wait_until="domcontentloaded")
            except Exception:
                pass
        title = await page.title()
        session.history.append(url)
        _update_session_memory(session_id, url, title, "navigate")
        _record_action(session, "browser_navigate", url, None, "ok")
        return _action_result("browser_navigate", url, title, {"url": url, "title": title})
    except Exception as e:
        et = "NavigationTimeout" if "Timeout" in str(e) else "BrowserError"
        return _action_result("browser_navigate", url, "", error=str(e), error_type=et)


async def do_browser_find(text: str, session_id: str = None) -> dict:
    if not text or not text.strip():
        return _action_result("browser_find", "", "", error="text is required", error_type="ValidationError")
    try:
        bm, session, page = await _ensure(session_id)
        locator = page.get_by_text(text, exact=False).first
        try:
            await locator.wait_for(state="attached", timeout=5000)
            tag = await locator.evaluate("el => el.tagName.toLowerCase()")
            selector = await locator.evaluate("el => { let s = el.tagName.toLowerCase(); if (el.id) s += '#' + el.id; else if (el.className && typeof el.className === 'string') s += '.' + el.className.trim().split(/\\s+/).join('.'); return s; }")
            found = True
        except Exception:
            found = False
            tag = ""
            selector = ""
        result = {"found": found, "text": text, "tag": tag, "selector": selector}
        _record_action(session, "browser_find", page.url, text, "ok" if found else "not_found")
        return _action_result("browser_find", page.url, await page.title(), result)
    except Exception as e:
        return _action_result("browser_find", "", "", error=str(e), error_type="BrowserError")


async def do_browser_find_interactive(text: str, session_id: str = None) -> dict:
    """Find an interactive element by text. Prioritises fillable, then clickable.

    Strategy order (fillable first):
      1. textbox / searchbox / combobox (role)
      2. get_by_placeholder(text, exact=False)
      3. get_by_label(text, exact=False)
      4. button / link (role)
      5. CSS input/textarea matching aria-label or title
      6. get_by_text(text) — final fallback
    """
    if not text or not text.strip():
        return _action_result("browser_find_interactive", "", "", error="text is required", error_type="ValidationError")
    try:
        bm, session, page = await _ensure(session_id)

        from playwright.async_api import Locator
        strategies: list[tuple[str, Locator]] = []

        # Priority 1: role-based fillable elements
        for role in ("searchbox", "combobox", "textbox"):
            loc = page.get_by_role(role, name=text, exact=False).first
            strategies.append((role, loc))

        # Priority 2: placeholder / label (non-role, fillable)
        strategies.append(("placeholder", page.get_by_placeholder(text, exact=False).first))
        strategies.append(("label", page.get_by_label(text, exact=False).first))

        # Priority 3: clickable elements (buttons, links)
        for role in ("button", "link"):
            loc = page.get_by_role(role, name=text, exact=False).first
            strategies.append((role, loc))

        # Priority 4: CSS fallback — inputs/textareas whose aria-label or title
        # contains the text (helps when get_by_role doesn't resolve the name)
        escaped = text.replace('"', '\\"')
        strategies.append(("css-input",
            page.locator(
                f'input[aria-label*="{escaped}" i], '
                f'textarea[aria-label*="{escaped}" i], '
                f'input[title*="{escaped}" i], '
                f'textarea[title*="{escaped}" i]'
            ).first
        ))

        # Priority 5: plain text fallback
        strategies.append(("text", page.get_by_text(text, exact=False).first))

        for strategy_name, locator in strategies:
            try:
                await locator.wait_for(state="attached", timeout=2000)
                # Skip invisible elements
                visible = await locator.is_visible()
                if not visible:
                    continue
                tag = await locator.evaluate("el => el.tagName.toLowerCase()")
                # If text-fallback matched a non-interactive element, drill into it
                if strategy_name == "text" and tag in ("ul", "ol", "li", "div", "span", "p", "section", "nav"):
                    interactive = await locator.evaluate("""el => {
                        let sel = el.querySelector('button, a, input, textarea, select, [role=button], [role=link], [role=textbox], [role=searchbox], [role=combobox]');
                        if (sel) return sel.tagName.toLowerCase();
                        return null;
                    }""")
                    if interactive:
                        tag = interactive
                        locator = locator.locator("button, a, input, textarea, select, [role=button], [role=link], [role=textbox], [role=searchbox], [role=combobox]").first
                        try:
                            await locator.wait_for(state="attached", timeout=1000)
                        except Exception:
                            pass
                selector = await locator.evaluate("""el => {
                    let t = el.tagName.toLowerCase();
                    if (el.id) return t + '#' + el.id;
                    let cls = el.className;
                    if (cls && typeof cls === 'string') {
                        let parts = cls.trim().split(/\\s+/).filter(Boolean);
                        if (parts.length) return t + '.' + parts[0];
                    }
                    let p = el.parentElement;
                    if (p) {
                        let kids = p.querySelectorAll(':scope > ' + t);
                        for (let i = 0; i < kids.length; i++) {
                            if (kids[i] === el) return t + ':nth-of-type(' + (i + 1) + ')';
                        }
                    }
                    return t;
                }""")
                result = {"found": True, "text": text, "tag": tag, "selector": selector, "strategy": strategy_name}
                _record_action(session, "browser_find_interactive", page.url, text, f"ok_{strategy_name}")
                return _action_result("browser_find_interactive", page.url, await page.title(), result)
            except Exception:
                continue

        result = {"found": False, "text": text, "tag": "", "selector": "", "strategy": "none"}
        _record_action(session, "browser_find_interactive", page.url, text, "not_found")
        return _action_result("browser_find_interactive", page.url, await page.title(), result)
    except Exception as e:
        return _action_result("browser_find_interactive", "", "", error=str(e), error_type="BrowserError")


async def do_browser_click(selector: str, session_id: str = None, force: bool = False) -> dict:
    if not selector or not selector.strip():
        return _action_result("browser_click", "", "", error="selector is required", error_type="ValidationError")
    try:
        bm, session, page = await _ensure(session_id)
        locator = await _resolve_selector(page, selector)
        try:
            if force:
                await locator.click(force=True)
            else:
                await locator.click()
        except Exception as e:
            err_str = str(e)
            if "intercepted" in err_str or "intercepts" in err_str or "overlay" in err_str:
                await locator.click(force=True)
            else:
                raise
        url = page.url
        title = await page.title()
        _update_session_memory(session_id, url, title, "click")
        _record_action(session, "browser_click", url, selector, "ok")
        return _action_result("browser_click", url, title, {"clicked": selector})
    except Exception as e:
        et = "SelectorNotFound"
        url = ""
        try:
            url = page.url if page else ""
        except Exception:
            pass
        return _action_result("browser_click", url, "", error=str(e), error_type=et, selector=selector)


async def do_browser_fill(selector: str, text: str, session_id: str = None) -> dict:
    if not selector or not selector.strip():
        return _action_result("browser_fill", "", "", error="selector is required", error_type="ValidationError")
    try:
        bm, session, page = await _ensure(session_id)
        locator = await _resolve_selector(page, selector)
        try:
            await locator.fill(text)
        except Exception as fill_err:
            err_str = str(fill_err)
            # If it's a contenteditable or custom element, use JS to set text
            if "not an <input>" in err_str or "not an <textarea>" in err_str or "not an <select>" in err_str or "contenteditable" in err_str:
                tag = await locator.evaluate("el => el.tagName.toLowerCase()")
                is_contenteditable = await locator.evaluate("el => el.isContentEditable")
                if is_contenteditable or tag in ("div", "span", "p", "section"):
                    await locator.evaluate(f"(el, val) => {{ el.textContent = val; el.dispatchEvent(new Event('input', {{ bubbles: true }})); el.dispatchEvent(new Event('change', {{ bubbles: true }})); }}", text)
                elif "-" in tag:
                    # Custom web component — try shadow DOM input
                    inner = page.locator(f"{selector} >>> input, {selector} >>> textarea, {selector} >>> [contenteditable]").first
                    try:
                        await inner.wait_for(state="attached", timeout=3000)
                        try:
                            await inner.fill(text)
                        except Exception:
                            await inner.evaluate(f"(el, val) => {{ el.textContent = val; el.dispatchEvent(new Event('input', {{ bubbles: true }})); el.dispatchEvent(new Event('change', {{ bubbles: true }})); }}", text)
                    except Exception:
                        raise fill_err
                else:
                    raise fill_err
            else:
                raise fill_err
        url = page.url
        title = await page.title()
        _update_session_memory(session_id, url, title, "fill")
        _record_action(session, "browser_fill", url, selector, "ok")
        return _action_result("browser_fill", url, title, {"filled": selector})
    except Exception as e:
        et = "SelectorNotFound"
        url = ""
        try:
            url = page.url if page else ""
        except Exception:
            pass
        return _action_result("browser_fill", url, "", error=str(e), error_type=et, selector=selector)


async def do_browser_press(selector: str, key: str, session_id: str = None) -> dict:
    if not selector or not selector.strip():
        return _action_result("browser_press", "", "", error="selector is required", error_type="ValidationError")
    if not key or not key.strip():
        return _action_result("browser_press", "", "", error="key is required", error_type="ValidationError")
    try:
        bm, session, page = await _ensure(session_id)
        locator = await _resolve_selector(page, selector)
        await locator.press(key)
        url = page.url
        title = await page.title()
        _update_session_memory(session_id, url, title, f"press:{key}")
        _record_action(session, "browser_press", url, selector, "ok")
        return _action_result("browser_press", url, title, {"pressed": key, "on": selector})
    except Exception as e:
        et = "SelectorNotFound"
        url = ""
        try:
            url = page.url if page else ""
        except Exception:
            pass
        return _action_result("browser_press", url, "", error=str(e), error_type=et, selector=selector)


async def do_browser_snapshot(session_id: str = None) -> dict:
    try:
        bm, session, page = await _ensure(session_id)
        title = await page.title()
        url = page.url
        snapshot = await page.evaluate("""() => {
            function collect(selector, attr) {
                return Array.from(document.querySelectorAll(selector)).map(el => {
                    const rect = el.getBoundingClientRect();
                    const info = { tag: el.tagName.toLowerCase(), text: (el.textContent || '').trim().slice(0, 120), visible: rect.width > 0 && rect.height > 0 };
                    if (el.id) info.id = el.id;
                    const cls = el.className;
                    if (cls && typeof cls === 'string') info.classes = cls.trim().split(/\\s+/).slice(0, 3);
                    if (attr && el.getAttribute) {
                        const v = el.getAttribute(attr);
                        if (v) info[attr] = v;
                    }
                    return info;
                });
            }
            function collectShadow() {
                const results = [];
                document.querySelectorAll('*').forEach(el => {
                    if (el.shadowRoot) {
                        const tag = el.tagName.toLowerCase();
                        const inputs = Array.from(el.shadowRoot.querySelectorAll('input, textarea, select')).map(inp => ({
                            tag: inp.tagName.toLowerCase(),
                            id: inp.id,
                            name: inp.name,
                            placeholder: inp.placeholder,
                            type: inp.type,
                        }));
                        results.push({ host: tag, id: el.id, shadow_inputs: inputs, shadow_count: el.shadowRoot.children.length });
                    }
                });
                return results;
            }
            return {
                buttons: collect('button, input[type=\"button\"], input[type=\"submit\"], [role=\"button\"]', null),
                inputs: collect('input:not([type=\"hidden\"]):not([type=\"button\"]):not([type=\"submit\"]), textarea, select', 'name'),
                links: collect('a[href]', 'href').filter(l => l.href && !l.href.startsWith('#')),
                forms: Array.from(document.querySelectorAll('form')).map(f => ({ id: f.id, action: f.action, method: f.method, inputs: f.querySelectorAll('input, select, textarea').length })),
                headings: collect('h1, h2, h3, h4, h5, h6', null),
                shadow_elements: collectShadow(),
                contenteditable: collect('[contenteditable=\"true\"], [contenteditable=\"\"], div[contenteditable], span[contenteditable]', null),
                modals: collect('[role=\"dialog\"], [role=\"alertdialog\"], dialog, [aria-modal=\"true\"]', null),
                dialogs: collect('dialog[open], [role=\"dialog\"][aria-hidden=\"false\"]', null),
            };
        }""")
        result = {"title": title, "url": url, **snapshot}
        _update_session_memory(session_id, url, title, "snapshot")
        _record_action(session, "browser_snapshot", url, None, "ok")
        return _action_result("browser_snapshot", url, title, result)
    except Exception as e:
        return _action_result("browser_snapshot", "", "", error=str(e), error_type="BrowserError")


async def do_browser_get_url(session_id: str = None) -> dict:
    try:
        bm, session, page = await _ensure(session_id)
        url = page.url
        title = await page.title()
        return _action_result("browser_get_url", url, title, {"url": url})
    except Exception as e:
        return _action_result("browser_get_url", "", "", error=str(e), error_type="BrowserError")


async def do_browser_get_title(session_id: str = None) -> dict:
    try:
        bm, session, page = await _ensure(session_id)
        title = await page.title()
        url = page.url
        return _action_result("browser_get_title", url, title, {"title": title})
    except Exception as e:
        return _action_result("browser_get_title", "", "", error=str(e), error_type="BrowserError")


async def do_browser_screenshot(session_id: str = None) -> dict:
    try:
        bm, session, page = await _ensure(session_id)
        png_bytes = await page.screenshot(full_page=False)
        b64 = base64.b64encode(png_bytes).decode("utf-8")
        url = page.url
        title = await page.title()
        _record_action(session, "browser_screenshot", url, None, "ok")
        return _action_result("browser_screenshot", url, title, {"screenshot": b64, "mime": "image/png"})
    except Exception as e:
        return _action_result("browser_screenshot", "", "", error=str(e), error_type="BrowserError")


async def do_browser_current_state(session_id: str = None) -> dict:
    try:
        bm, session, page = await _ensure(session_id)
        url = page.url
        title = await page.title()
        tab_count = len(session.pages)
        state = await page.evaluate("""() => {
            const buttons = document.querySelectorAll('button, input[type=\"button\"], input[type=\"submit\"], [role=\"button\"]').length;
            const inputs = document.querySelectorAll('input:not([type=\"hidden\"]):not([type=\"button\"]):not([type=\"submit\"]), textarea, select').length;
            const links = document.querySelectorAll('a[href]').length;
            const forms = document.querySelectorAll('form').length;
            return { form_count: forms, input_count: inputs, button_count: buttons, links_count: links };
        }""")
        result = {"url": url, "title": title, "tab_count": tab_count, **state}
        _record_action(session, "browser_current_state", url, None, "ok")
        return _action_result("browser_current_state", url, title, result)
    except Exception as e:
        return _action_result("browser_current_state", "", "", error=str(e), error_type="BrowserError")


async def do_browser_evaluate(js: str, session_id: str = None) -> dict:
    try:
        bm, session, page = await _ensure(session_id)
        result = await page.evaluate(js)
        url = page.url
        title = await page.title()
        _record_action(session, "browser_evaluate", url, None, "ok")
        return _action_result("browser_evaluate", url, title, {"result": result})
    except Exception as e:
        return _action_result("browser_evaluate", "", "", error=str(e), error_type="BrowserError")


async def do_browser_get_history(session_id: str = None) -> dict:
    try:
        bm, session, page = await _ensure(session_id)
        url = page.url
        title = await page.title()
        return _action_result("browser_get_history", url, title, {
            "navigation_history": session.history,
            "action_history": session.action_history,
            "total_navigations": len(session.history),
            "total_actions": len(session.action_history),
        })
    except Exception as e:
        return _action_result("browser_get_history", "", "", error=str(e), error_type="BrowserError")

async def do_browser_list_tabs(session_id: str = None) -> dict:
    try:
        bm, session, page = await _ensure(session_id)
        tabs = await bm.list_tabs(session_id)
        _record_action(session, "browser_list_tabs", page.url, None, "ok")
        return _action_result("browser_list_tabs", page.url, await page.title(), {"tabs": tabs, "count": len(tabs), "active": session.current_page_index})
    except Exception as e:
        return _action_result("browser_list_tabs", "", "", error=str(e), error_type="BrowserError")

async def do_browser_switch_tab(index: int, session_id: str = None) -> dict:
    try:
        bm, session, page = await _ensure(session_id)
        result = await bm.switch_tab(session_id, index)
        if result.get("status") == "error":
            return _action_result("browser_switch_tab", "", "", error=result.get("error"), error_type="TabError")
        updated_page = session.current_page
        url = updated_page.url
        title = await updated_page.title()
        _update_session_memory(session_id, url, title, f"switch_tab:{index}")
        _record_action(session, "browser_switch_tab", url, None, "ok")
        return _action_result("browser_switch_tab", url, title, {"tab_index": index, "url": url})
    except Exception as e:
        return _action_result("browser_switch_tab", "", "", error=str(e), error_type="BrowserError")

async def do_browser_new_tab(url: str = None, session_id: str = None) -> dict:
    try:
        bm, session, page = await _ensure(session_id)
        result = await bm.new_tab(session_id, url)
        if result.get("status") == "error":
            return _action_result("browser_new_tab", "", "", error=result.get("error"), error_type="TabError")
        updated_page = session.current_page
        target_url = updated_page.url
        title = await updated_page.title()
        _update_session_memory(session_id, target_url, title, "new_tab")
        _record_action(session, "browser_new_tab", target_url, None, "ok")
        return _action_result("browser_new_tab", target_url, title, {"tab_index": result["tab_index"], "url": target_url})
    except Exception as e:
        return _action_result("browser_new_tab", "", "", error=str(e), error_type="BrowserError")

async def do_browser_close_tab(index: int, session_id: str = None) -> dict:
    try:
        bm, session, page = await _ensure(session_id)
        result = await bm.close_tab(session_id, index)
        if result.get("status") == "error":
            return _action_result("browser_close_tab", "", "", error=result.get("error"), error_type="TabError")
        url = session.current_page.url
        title = await session.current_page.title()
        _update_session_memory(session_id, url, title, f"close_tab:{index}")
        _record_action(session, "browser_close_tab", url, None, "ok")
        return _action_result("browser_close_tab", url, title, {"closed_index": index})
    except Exception as e:
        return _action_result("browser_close_tab", "", "", error=str(e), error_type="BrowserError")

async def do_browser_wait_visible(selector: str, timeout: int = 10000, session_id: str = None) -> dict:
    """Wait until a CSS selector is visible in the DOM."""
    if not selector or not selector.strip():
        return _action_result("browser_wait_visible", "", "", error="selector is required", error_type="ValidationError")
    try:
        bm, session, page = await _ensure(session_id)
        locator = page.locator(selector).first
        await locator.wait_for(state="visible", timeout=timeout)
        url = page.url
        title = await page.title()
        _record_action(session, "browser_wait_visible", url, selector, "ok")
        return _action_result("browser_wait_visible", url, title, {"selector": selector, "visible": True})
    except Exception as e:
        return _action_result("browser_wait_visible", "", "", error=str(e), error_type="TimeoutError" if "Timeout" in str(e) else "BrowserError")


async def do_browser_wait_text(text: str, timeout: int = 10000, session_id: str = None) -> dict:
    """Wait until text appears on the page."""
    if not text or not text.strip():
        return _action_result("browser_wait_text", "", "", error="text is required", error_type="ValidationError")
    try:
        bm, session, page = await _ensure(session_id)
        locator = page.get_by_text(text, exact=False).first
        await locator.wait_for(state="visible", timeout=timeout)
        url = page.url
        title = await page.title()
        _record_action(session, "browser_wait_text", url, text, "ok")
        return _action_result("browser_wait_text", url, title, {"text": text, "found": True})
    except Exception as e:
        return _action_result("browser_wait_text", "", "", error=str(e), error_type="TimeoutError" if "Timeout" in str(e) else "BrowserError")


async def do_browser_wait_interactive(text: str, timeout: int = 10000, session_id: str = None) -> dict:
    """Wait until an interactive element (button, link, input) with matching text is visible and enabled."""
    if not text or not text.strip():
        return _action_result("browser_wait_interactive", "", "", error="text is required", error_type="ValidationError")
    try:
        bm, session, page = await _ensure(session_id)
        # Try to find an interactive element first
        from playwright.async_api import expect
        for role in ("button", "link", "textbox", "searchbox", "combobox"):
            try:
                locator = page.get_by_role(role, name=text, exact=False).first
                await locator.wait_for(state="visible", timeout=timeout)
                enabled = await locator.is_enabled()
                if enabled:
                    tag = await locator.evaluate("el => el.tagName.toLowerCase()")
                    selector = await locator.evaluate("""el => {
                        let t = el.tagName.toLowerCase();
                        if (el.id) return t + '#' + el.id;
                        let cls = el.className;
                        if (cls && typeof cls === 'string') {
                            let parts = cls.trim().split(/\\s+/).filter(Boolean);
                            if (parts.length) return t + '.' + parts[0];
                        }
                        let p = el.parentElement;
                        if (p) {
                            let kids = p.querySelectorAll(':scope > ' + t);
                            for (let i = 0; i < kids.length; i++) {
                                if (kids[i] === el) return t + ':nth-of-type(' + (i + 1) + ')';
                            }
                        }
                        return t;
                    }""")
                    url = page.url
                    title = await page.title()
                    _record_action(session, "browser_wait_interactive", url, text, "ok")
                    return _action_result("browser_wait_interactive", url, title,
                                          {"text": text, "tag": tag, "selector": selector, "ready": True})
            except Exception:
                continue
        return _action_result("browser_wait_interactive", page.url, await page.title(),
                              error=f"Interactive element with text '{text}' not found within {timeout}ms",
                              error_type="TimeoutError")
    except Exception as e:
        return _action_result("browser_wait_interactive", "", "", error=str(e), error_type="BrowserError")


async def do_browser_shadow_query(selector: str, session_id: str = None) -> dict:
    """Query elements inside shadow DOM roots. Use CSS '>>>' concatenation syntax.
    Example: 'my-component >>> input' finds inputs inside my-component's shadow root.
    """
    if not selector or not selector.strip():
        return _action_result("browser_shadow_query", "", "", error="selector is required", error_type="ValidationError")
    try:
        bm, session, page = await _ensure(session_id)
        locator = page.locator(selector)
        count = await locator.count()
        elements = []
        for i in range(min(count, 50)):
            try:
                el = locator.nth(i)
                tag = await el.evaluate("el => el.tagName.toLowerCase()")
                visible = await el.is_visible()
                text = await el.evaluate("el => (el.textContent || '').trim().slice(0, 200)")
                attrs = await el.evaluate("""el => {
                    const a = {};
                    if (el.id) a.id = el.id;
                    if (el.name) a.name = el.name;
                    if (el.placeholder) a.placeholder = el.placeholder;
                    if (el.type) a.type = el.type;
                    if (el.getAttribute) {
                        const aria = el.getAttribute('aria-label');
                        if (aria) a['aria-label'] = aria;
                        const role = el.getAttribute('role');
                        if (role) a.role = role;
                    }
                    return a;
                }""")
                elements.append({"index": i, "tag": tag, "visible": visible,
                                 "text": text, "attributes": attrs})
            except Exception:
                elements.append({"index": i, "tag": "unknown"})
        url = page.url
        title = await page.title()
        result = {"selector": selector, "count": count, "elements": elements}
        _record_action(session, "browser_shadow_query", url, selector, "ok")
        return _action_result("browser_shadow_query", url, title, result)
    except Exception as e:
        return _action_result("browser_shadow_query", "", "", error=str(e), error_type="BrowserError")


async def do_browser_health(session_id: str = None) -> dict:
    try:
        bm = _bm()
        await bm.ensure_browser_alive()
        contexts = len(bm._browser.contexts) if bm._browser else 0
        tabs = sum(len(s.pages) for s in bm._sessions.values()) if hasattr(bm, '_sessions') else 0
        active_sessions = len(bm._sessions) if hasattr(bm, '_sessions') else 0
        return _action_result("browser_health", "", "", {
            "browser_alive": bm._started,
            "contexts": contexts,
            "active_sessions": active_sessions,
            "tabs": tabs,
            "uptime_seconds": 0,
        })
    except Exception as e:
        return _action_result("browser_health", "", "", error=str(e), error_type="BrowserError")
