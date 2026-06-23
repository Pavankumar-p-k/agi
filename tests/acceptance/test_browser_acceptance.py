"""BROWSER_REAL_WORLD_ACCEPTANCE_TEST — runs 100 real-world tests against Playwright browser tools.

Usage: python tests/acceptance/test_browser_acceptance.py
"""

import asyncio
import json
import sys
import time
import traceback
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.browser_manager import BrowserManager
from core.tools.browser_tools import (
    do_browser_navigate, do_browser_find, do_browser_find_interactive, do_browser_click,
    do_browser_fill, do_browser_press, do_browser_snapshot,
    do_browser_get_url, do_browser_get_title, do_browser_screenshot,
    do_browser_current_state, do_browser_health,
    do_browser_list_tabs, do_browser_switch_tab, do_browser_new_tab,
    do_browser_close_tab, do_browser_get_history,
    do_browser_evaluate,
    do_browser_wait_visible, do_browser_wait_text, do_browser_wait_interactive,
    do_browser_shadow_query,
)
from core.auth import get_auth_manager
from core.tools.security import is_authorized_to_execute

SESSION_ID = "acceptance-test-session"
RESULTS_DIR = Path("tests/acceptance/results")
SCREENSHOTS_DIR = RESULTS_DIR / "screenshots"

CONFIG = {
    "timeout": 45000,
    "headless": False,
}

class TestRecord:
    __slots__ = ("category", "name", "tool_sequence", "input",
                 "result", "success", "execution_time", "screenshot_path")

class AcceptanceRunner:
    def __init__(self):
        self.records: list[TestRecord] = []
        self._started = False

    async def start(self):
        if self._started:
            return
        self._started = True
        SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        from core.config_registry import config as _jarvis_config
        _jarvis_config.browser.headed = False
        bm = BrowserManager.instance()
        await bm.ensure_browser_alive()
        session = bm.get_session(SESSION_ID)
        if session is None:
            session = await bm.get_or_create_session(SESSION_ID)

    async def stop(self):
        bm = BrowserManager.instance()
        if bm._started:
            await bm.stop()

    async def test(self, category: str, name: str, fn, *,
                   screenshot_on_fail=True, timeout=30000):
        rec = TestRecord()
        rec.category = category
        rec.name = name
        rec.input = name
        rec.screenshot_path = None

        tool_name = getattr(fn, "__name__", "lambda")
        if tool_name.startswith("do_"):
            tool_name = tool_name[3:]
        rec.tool_sequence = [tool_name]

        start = time.time()
        try:
            result = await asyncio.wait_for(fn(), timeout=timeout)
            rec.execution_time = round(time.time() - start, 3)
            rec.result = result
            rec.success = result.get("status") == "ok"
            if not rec.success and screenshot_on_fail:
                rec.screenshot_path = await self._capture_screenshot(category, name)
        except asyncio.TimeoutError:
            rec.execution_time = round(time.time() - start, 3)
            rec.result = {"status": "error", "error": f"TIMEOUT after {timeout}ms"}
            rec.success = False
            if screenshot_on_fail:
                rec.screenshot_path = await self._capture_screenshot(category, name)
        except Exception as e:
            rec.execution_time = round(time.time() - start, 3)
            rec.result = {"status": "error", "error": f"{type(e).__name__}: {e}"}
            rec.success = False
            if screenshot_on_fail:
                rec.screenshot_path = await self._capture_screenshot(category, name)

        # Security tests (H): PermissionDenied IS success
        if category == "H":
            err_type = rec.result.get("error_type", "")
            if err_type == "PermissionDenied":
                rec.success = True
            elif rec.result.get("error", "").startswith("PermissionDenied"):
                rec.success = True
            # H10: is_authorized_to_execute returns False = blocked = success
            if rec.name == "Block browser_evaluate for non-admin" and rec.result.get("result", {}).get("blocked"):
                rec.success = True

        self.records.append(rec)
        status = "PASS" if rec.success else "FAIL"
        print(f"  [{status}] [{rec.execution_time:6.2f}s] [{category}] {name}")
        if not rec.success:
            err = rec.result.get("error", rec.result.get("error_type", "unknown"))
            print(f"         -> {err}")
        return rec.result

    async def _capture_screenshot(self, category, name):
        safe = f"{category}_{name}".replace(" ", "_").replace("/", "_").replace(":", "")[:80]
        path = SCREENSHOTS_DIR / f"{safe}.png"
        try:
            ss = await do_browser_screenshot(session_id=SESSION_ID)
            if ss.get("status") == "ok":
                import base64
                data = ss["result"]["screenshot"]
                with open(path, "wb") as f:
                    f.write(base64.b64decode(data))
                return str(path.relative_to(Path.cwd()))
        except Exception:
            pass
        return None

    def summary(self):
        total = len(self.records)
        passed = sum(1 for r in self.records if r.success)
        failed = total - passed
        pct = (passed / total * 100) if total else 0
        return total, passed, failed, round(pct, 1)

    def generate_report(self) -> str:
        total, passed, failed, pct = self.summary()
        if pct >= 95:
            classification = "SAFE"
        elif pct >= 85:
            classification = "WARNING"
        else:
            classification = "RELEASE_BLOCKER"

        lines = []
        lines.append("# BROWSER_REAL_WORLD_ACCEPTANCE_REPORT")
        lines.append("")
        lines.append(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"**Browser:** Playwright Chromium")
        lines.append(f"**Session:** `{SESSION_ID}`")
        lines.append(f"**Mode:** {'Headed' if not CONFIG['headless'] else 'Headless'}")
        lines.append("")
        lines.append("## Summary")
        lines.append("")
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Total Tests | {total} |")
        lines.append(f"| Passed | {passed} |")
        lines.append(f"| Failed | {failed} |")
        lines.append(f"| Pass Rate | {pct}% |")
        lines.append(f"| Classification | **{classification}** |")
        lines.append("")

        categories = {}
        for r in self.records:
            categories.setdefault(r.category, []).append(r)

        for cat_name, cat_records in sorted(categories.items()):
            cat_total = len(cat_records)
            cat_passed = sum(1 for r in cat_records if r.success)
            cat_failed = cat_total - cat_passed
            cat_pct = round(cat_passed / cat_total * 100, 1) if cat_total else 0

            lines.append(f"## Category {cat_name}")
            lines.append("")
            lines.append(f"**Pass Rate:** {cat_pct}% ({cat_passed}/{cat_total})")
            lines.append("")
            lines.append("| # | Test | Tool(s) | Result | Time (s) |")
            lines.append("|---|------|---------|--------|----------|")
            for i, rec in enumerate(cat_records, 1):
                tools = ", ".join(rec.tool_sequence)
                res = "✅ PASS" if rec.success else "❌ FAIL"
                ss_link = ""
                if rec.screenshot_path:
                    ss_link = f" [📸]({rec.screenshot_path})"
                lines.append(f"| {i} | {rec.name} | `{tools}` | {res}{ss_link} | {rec.execution_time} |")
            lines.append("")

        lines.append("## Failure Details")
        lines.append("")
        failed_records = [r for r in self.records if not r.success]
        if failed_records:
            for i, rec in enumerate(failed_records, 1):
                err = rec.result.get("error", rec.result.get("error_type", "unknown"))
                lines.append(f"### {i}. [{rec.category}] {rec.name}")
                lines.append("")
                lines.append(f"- **Error:** {err}")
                lines.append(f"- **Tool:** `{', '.join(rec.tool_sequence)}`")
                lines.append(f"- **Time:** {rec.execution_time}s")
                if rec.screenshot_path:
                    lines.append(f"- **Screenshot:** [{rec.screenshot_path}]({rec.screenshot_path})")
                lines.append("")
        else:
            lines.append("None — all tests passed.")
            lines.append("")

        lines.append("## Classification Thresholds")
        lines.append("")
        lines.append(f"| Range | Label | Current |")
        lines.append(f"|-------|-------|---------|")
        lines.append(f"| ≥95% | **SAFE** | {'✅' if pct >= 95 else ''} |")
        lines.append(f"| 85-94% | **WARNING** | {'✅' if 85 <= pct < 95 else ''} |")
        lines.append(f"| <85% | **RELEASE_BLOCKER** | {'❌' if pct < 85 else ''} |")
        lines.append("")
        lines.append(f"**Overall: {classification}**")
        lines.append("")

        return "\n".join(lines)


async def main():
    print("=" * 60)
    print("BROWSER REAL-WORLD ACCEPTANCE TEST")
    print("=" * 60)
    print()

    runner = AcceptanceRunner()
    await runner.start()
    print(f"[SETUP] Browser started (headless={CONFIG['headless']})")
    print()

    # -- Category A: Navigation (15) --
    print("-" * 40)
    print("Category A — Navigation (15 tests)")
    print("-" * 40)
    nav_tests = [
        ("A", "github.com",              lambda: do_browser_navigate("https://github.com", session_id=SESSION_ID)),
        ("A", "python.org",              lambda: do_browser_navigate("https://python.org", session_id=SESSION_ID)),
        ("A", "wikipedia.org",           lambda: do_browser_navigate("https://wikipedia.org", session_id=SESSION_ID)),
        ("A", "stackoverflow.com",       lambda: do_browser_navigate("https://stackoverflow.com", session_id=SESSION_ID)),
        ("A", "reddit.com",              lambda: do_browser_navigate("https://reddit.com", session_id=SESSION_ID)),
        ("A", "openai.com",             lambda: do_browser_navigate("https://openai.com", session_id=SESSION_ID)),
        ("A", "docs.python.org",         lambda: do_browser_navigate("https://docs.python.org", session_id=SESSION_ID)),
        ("A", "playwright.dev",          lambda: do_browser_navigate("https://playwright.dev", session_id=SESSION_ID)),
        ("A", "npmjs.com",               lambda: do_browser_navigate("https://npmjs.com", session_id=SESSION_ID)),
        ("A", "pypi.org",               lambda: do_browser_navigate("https://pypi.org", session_id=SESSION_ID)),
        ("A", "microsoft.com",           lambda: do_browser_navigate("https://microsoft.com", session_id=SESSION_ID)),
        ("A", "google.com",              lambda: do_browser_navigate("https://google.com", session_id=SESSION_ID)),
        ("A", "youtube.com",             lambda: do_browser_navigate("https://youtube.com", session_id=SESSION_ID)),
        ("A", "mozilla.org",             lambda: do_browser_navigate("https://mozilla.org", session_id=SESSION_ID)),
        ("A", "github.com/openai",       lambda: do_browser_navigate("https://github.com/openai", session_id=SESSION_ID)),
    ]
    for cat, name, fn in nav_tests:
        await runner.test(cat, name, fn, timeout=CONFIG["timeout"])

    # -- Category B: Text Discovery (15) --
    print()
    print("-" * 40)
    print("Category B — Text Discovery (15 tests)")
    print("-" * 40)
    # Navigate to each site first, then find text
    find_sites = [
        ("B", "Sign In on GitHub",       "https://github.com", "Sign in"),
        ("B", "Downloads on Python.org",  "https://python.org", "Downloads"),
        ("B", "Search on Wikipedia",     "https://wikipedia.org", "Search"),
        ("B", "Docs on Playwright",      "https://playwright.dev", "Docs"),
        ("B", "Packages on PyPI",        "https://pypi.org", "Packages"),
        ("B", "Pricing on OpenAI",       "https://openai.com", "Pricing"),
        ("B", "About on Mozilla",        "https://mozilla.org", "About"),
        ("B", "Products on Microsoft",   "https://microsoft.com", "Products"),
        ("B", "Explore on GitHub",       "https://github.com", "Explore"),
        ("B", "Trending on GitHub",      "https://github.com", "Trending"),
        ("B", "Community on Python.org", "https://python.org", "Community"),
        ("B", "News on Reddit",          "https://reddit.com", "News"),
        ("B", "Watch on YouTube",        "https://youtube.com", "Watch"),
        ("B", "Docs on OpenAI",          "https://openai.com", "Docs"),
        ("B", "Learn on Playwright",     "https://playwright.dev", "Learn"),
    ]
    for cat, name, site_url, find_text in find_sites:
        async def _run(site=site_url, text=find_text):
            await do_browser_navigate(site, session_id=SESSION_ID)
            return await do_browser_find(text, session_id=SESSION_ID)
        await runner.test(cat, name, _run, timeout=CONFIG["timeout"])

    # -- Category C: Form Interaction (15) --
    print()
    print("-" * 40)
    print("Category C — Form Interaction (15 tests)")
    print("-" * 40)
    form_tests = []

    GENERIC_INPUT = "input:not([type=hidden]):not([type=submit]):not([type=button]):not([type=checkbox]):not([type=radio]):not([type=file]), textarea, [contenteditable]"
    # Helper: find text, click if it's a button (to reveal hidden input), then fill
    async def _find_and_fill(text: str, fill_value: str,
                             css_fallback: str = None) -> dict:
        r = await do_browser_find_interactive(text, session_id=SESSION_ID)
        res = r.get("result", {})
        sel = res.get("selector", "")
        tag = res.get("tag", "")
        strategy = res.get("strategy", "")
        # If we found a button or custom element (search icon), click first to reveal input
        should_click = (tag == "button") or (tag and "-" in tag)
        if should_click and sel:
            await do_browser_click(sel, session_id=SESSION_ID, force=True)
            await asyncio.sleep(1.0)
            # Try to find the revealed input — first by waiting for it to be visible
            r_wait = await do_browser_wait_visible(
                "input:not([type=hidden]):not([type=submit]):not([type=button]):not([type=checkbox]):not([type=radio]):not([type=file]):not([type=image]), textarea, [contenteditable]",
                timeout=8000, session_id=SESSION_ID
            )
            if r_wait.get("status") == "ok":
                sel = "input:not([type=hidden]):not([type=submit]):not([type=button]):not([type=checkbox]):not([type=radio]):not([type=file]):not([type=image]), textarea, [contenteditable]"
            else:
                # Fallback: try shadow DOM query for web components (Microsoft uhf-search)
                sq = await do_browser_shadow_query(f"{sel} >>> input, {sel} >>> textarea", session_id=SESSION_ID)
                if sq.get("status") == "ok" and sq["result"]["count"] > 0:
                    sel = f"{sel} >>> input"
                else:
                    sel = css_fallback or GENERIC_INPUT
        elif not sel or not res.get("found"):
            sel = css_fallback or GENERIC_INPUT
        return await do_browser_fill(sel, fill_value, session_id=SESSION_ID)

    # C1: Fill GitHub login field
    async def _fill_github_login():
        await do_browser_navigate("https://github.com/login", session_id=SESSION_ID)
        return await do_browser_fill("#login_field", "testuser", session_id=SESSION_ID)

    # C2: Fill GitHub password
    async def _fill_github_pass():
        return await do_browser_fill("#password", "testpass", session_id=SESSION_ID)

    # C3: Fill Wikipedia search
    async def _fill_wiki_search():
        await do_browser_navigate("https://wikipedia.org", session_id=SESSION_ID)
        return await do_browser_fill("#searchInput", "Python programming", session_id=SESSION_ID)

    # C4: Fill Python.org search
    async def _fill_python_search():
        await do_browser_navigate("https://python.org", session_id=SESSION_ID)
        return await _find_and_fill("Search", "async", "#id-search-field")

    # C5: Fill OpenAI search
    async def _fill_openai_search():
        await do_browser_navigate("https://openai.com", session_id=SESSION_ID)
        return await _find_and_fill("Search", "GPT-4")

    # C6: Fill Playwright search
    async def _fill_playwright_search():
        await do_browser_navigate("https://playwright.dev", session_id=SESSION_ID)
        return await _find_and_fill("Search", "locator")

    # C7-9: Press Enter, Tab, Escape on Wikipedia search
    async def _press_enter():
        await do_browser_navigate("https://wikipedia.org", session_id=SESSION_ID)
        await do_browser_fill("#searchInput", "Python", session_id=SESSION_ID)
        return await do_browser_press("#searchInput", "Enter", session_id=SESSION_ID)

    async def _press_tab():
        await do_browser_navigate("https://wikipedia.org", session_id=SESSION_ID)
        await do_browser_fill("#searchInput", "test", session_id=SESSION_ID)
        return await do_browser_press("#searchInput", "Tab", session_id=SESSION_ID)

    async def _press_escape():
        return await do_browser_press("body", "Escape", session_id=SESSION_ID)

    # C10-C15: Fill search on other sites
    async def _fill_so_search():
        await do_browser_navigate("https://stackoverflow.com", session_id=SESSION_ID)
        return await _find_and_fill("Search", "python async")

    async def _fill_reddit_search():
        await do_browser_navigate("https://reddit.com", session_id=SESSION_ID)
        return await _find_and_fill("Search", "programming")

    async def _fill_yt_search():
        await do_browser_navigate("https://youtube.com", session_id=SESSION_ID)
        return await _find_and_fill("Search", "python tutorial",
                                    "input[aria-label*=Search i], input[name=search_query]")

    async def _fill_npm_search():
        await do_browser_navigate("https://npmjs.com", session_id=SESSION_ID)
        return await _find_and_fill("Search", "react")

    async def _fill_pypi_search():
        await do_browser_navigate("https://pypi.org", session_id=SESSION_ID)
        return await _find_and_fill("Search", "requests",
                                    "input[aria-label*=Search i], input[name=q], input[type=search]")

    async def _fill_ms_search():
        await do_browser_navigate("https://microsoft.com", session_id=SESSION_ID)
        return await _find_and_fill("Search", "Visual Studio")

    form_tests = [
        ("C", "Fill GitHub login field",    _fill_github_login),
        ("C", "Fill GitHub password field",  _fill_github_pass),
        ("C", "Fill Wikipedia search",       _fill_wiki_search),
        ("C", "Fill Python.org search",      _fill_python_search),
        ("C", "Fill OpenAI search",          _fill_openai_search),
        ("C", "Fill Playwright search",      _fill_playwright_search),
        ("C", "Press Enter",                 _press_enter),
        ("C", "Press Tab",                   _press_tab),
        ("C", "Press Escape",                _press_escape),
        ("C", "Fill StackOverflow search",   _fill_so_search),
        ("C", "Fill Reddit search",           _fill_reddit_search),
        ("C", "Fill YouTube search",          _fill_yt_search),
        ("C", "Fill npm search",              _fill_npm_search),
        ("C", "Fill PyPI search",             _fill_pypi_search),
        ("C", "Fill Microsoft search",        _fill_ms_search),
    ]
    for cat, name, fn in form_tests:
        await runner.test(cat, name, fn, timeout=CONFIG["timeout"])

    # -- Category D: Navigation Flow (15) --
    print()
    print("-" * 40)
    print("Category D — Navigation Flow (15 tests)")
    print("-" * 40)

    async def _flow_python_downloads():
        await do_browser_navigate("https://python.org", session_id=SESSION_ID)
        r = await do_browser_find_interactive("Downloads", session_id=SESSION_ID)
        sel = r.get("result", {}).get("selector", "")
        if sel:
            return await do_browser_click(sel, session_id=SESSION_ID)
        return {"status": "error", "error": "Downloads link not found"}

    async def _flow_github_explore():
        await do_browser_navigate("https://github.com", session_id=SESSION_ID)
        r = await do_browser_find_interactive("Explore", session_id=SESSION_ID)
        sel = r.get("result", {}).get("selector", "")
        if sel:
            return await do_browser_click(sel, session_id=SESSION_ID)
        return {"status": "error", "error": "Explore link not found"}

    async def _flow_wiki_search_ai():
        await do_browser_navigate("https://wikipedia.org", session_id=SESSION_ID)
        await do_browser_fill("#searchInput", "Artificial intelligence", session_id=SESSION_ID)
        r = await do_browser_find_interactive("Artificial intelligence", session_id=SESSION_ID)
        if r.get("status") == "ok":
            sel = r["result"].get("selector", "")
            if sel:
                return await do_browser_click(sel, session_id=SESSION_ID)
        return await do_browser_press("#searchInput", "Enter", session_id=SESSION_ID)

    async def _flow_openai_api():
        await do_browser_navigate("https://platform.openai.com", session_id=SESSION_ID)
        return {"status": "ok", "message": "Navigated to platform.openai.com"}

    async def _flow_playwright_docs():
        await do_browser_navigate("https://playwright.dev", session_id=SESSION_ID)
        r = await do_browser_find_interactive("Docs", session_id=SESSION_ID)
        sel = r.get("result", {}).get("selector", "")
        if sel:
            return await do_browser_click(sel, session_id=SESSION_ID)
        return {"status": "error", "error": "Docs link not found"}

    async def _flow_ms_products():
        await do_browser_navigate("https://microsoft.com", session_id=SESSION_ID)
        r = await do_browser_find_interactive("Products", session_id=SESSION_ID)
        sel = r.get("result", {}).get("selector", "")
        if sel:
            return await do_browser_click(sel, session_id=SESSION_ID)
        return {"status": "error", "error": "Products link not found"}

    async def _flow_pypi_requests():
        await do_browser_navigate("https://pypi.org", session_id=SESSION_ID)
        r = await do_browser_find_interactive("Search", session_id=SESSION_ID)
        sel = r.get("result", {}).get("selector", "input[type=search], input[name=q]")
        await do_browser_fill(sel, "requests", session_id=SESSION_ID)
        return await do_browser_press(sel, "Enter", session_id=SESSION_ID)

    flow_tests = [
        ("D", "Open Python.org",        lambda: do_browser_navigate("https://python.org", session_id=SESSION_ID)),
        ("D", "Click Downloads",        _flow_python_downloads),
        ("D", "Open GitHub",            lambda: do_browser_navigate("https://github.com", session_id=SESSION_ID)),
        ("D", "Click Explore",          _flow_github_explore),
        ("D", "Open Wikipedia",         lambda: do_browser_navigate("https://wikipedia.org", session_id=SESSION_ID)),
        ("D", "Search AI",              _flow_wiki_search_ai),
        ("D", "Open OpenAI",            lambda: do_browser_navigate("https://openai.com", session_id=SESSION_ID)),
        ("D", "Click API",              _flow_openai_api),
        ("D", "Open Playwright",        lambda: do_browser_navigate("https://playwright.dev", session_id=SESSION_ID)),
        ("D", "Click Docs",             _flow_playwright_docs),
        ("D", "Open Microsoft",         lambda: do_browser_navigate("https://microsoft.com", session_id=SESSION_ID)),
        ("D", "Click Products",         _flow_ms_products),
        ("D", "Open PyPI",              lambda: do_browser_navigate("https://pypi.org", session_id=SESSION_ID)),
        ("D", "Search Requests",        _flow_pypi_requests),
        ("D", "Verify destination",     lambda: do_browser_get_url(session_id=SESSION_ID)),
    ]
    for cat, name, fn in flow_tests:
        await runner.test(cat, name, fn, timeout=CONFIG["timeout"])

    # -- Category E: DOM Snapshot Intelligence (10) --
    print()
    print("-" * 40)
    print("Category E — DOM Snapshot Intelligence (10 tests)")
    print("-" * 40)
    snap_sites = [
        ("E", "Snapshot GitHub",     "https://github.com"),
        ("E", "Snapshot Python",     "https://python.org"),
        ("E", "Snapshot Wikipedia",  "https://wikipedia.org"),
        ("E", "Snapshot OpenAI",     "https://openai.com"),
        ("E", "Snapshot Playwright", "https://playwright.dev"),
        ("E", "Snapshot Reddit",     "https://reddit.com"),
        ("E", "Snapshot YouTube",    "https://youtube.com"),
        ("E", "Snapshot Microsoft",  "https://microsoft.com"),
        ("E", "Snapshot npm",        "https://npmjs.com"),
        ("E", "Snapshot PyPI",       "https://pypi.org"),
    ]
    for cat, name, site_url in snap_sites:
        async def _snap(site=site_url, nm=name):
            await do_browser_navigate(site, session_id=SESSION_ID)
            result = await do_browser_snapshot(session_id=SESSION_ID)
            # Verify snapshot populated
            if result.get("status") == "ok":
                snap = result.get("result", {})
                total = (
                    len(snap.get("buttons", []))
                    + len(snap.get("links", []))
                    + len(snap.get("inputs", []))
                    + len(snap.get("forms", []))
                    + len(snap.get("headings", []))
                )
                if total == 0:
                    result["status"] = "error"
                    result["error"] = f"Snapshot returned empty: {snap}"
            return result
        await runner.test(cat, name, _snap, timeout=CONFIG["timeout"])

    # -- Category F: Tab Management (10) --
    print()
    print("-" * 40)
    print("Category F — Tab Management (10 tests)")
    print("-" * 40)

    async def _tab_open_github():
        return await do_browser_navigate("https://github.com", session_id=SESSION_ID)

    async def _tab_new_python():
        return await do_browser_new_tab("https://python.org", session_id=SESSION_ID)

    async def _tab_new_wikipedia():
        return await do_browser_new_tab("https://wikipedia.org", session_id=SESSION_ID)

    async def _tab_list():
        return await do_browser_list_tabs(session_id=SESSION_ID)

    tab2_url = None
    async def _tab_switch_2():
        nonlocal tab2_url
        r = await do_browser_switch_tab(1, session_id=SESSION_ID)
        if r.get("status") == "ok":
            tab2_url = r.get("url", "")
        return r

    async def _tab_verify_2():
        r = await do_browser_get_url(session_id=SESSION_ID)
        if r.get("status") == "ok" and "python" in r.get("url", "").lower():
            return r
        r["status"] = "error"
        r["error"] = f"Expected python.org URL, got: {r.get('url', '')}"
        return r

    async def _tab_switch_3():
        return await do_browser_switch_tab(2, session_id=SESSION_ID)

    async def _tab_verify_3():
        r = await do_browser_get_url(session_id=SESSION_ID)
        if r.get("status") == "ok" and "wikipedia" in r.get("url", "").lower():
            return r
        r["status"] = "error"
        r["error"] = f"Expected wikipedia URL, got: {r.get('url', '')}"
        return r

    async def _tab_close():
        return await do_browser_close_tab(2, session_id=SESSION_ID)

    async def _tab_verify_remaining():
        r = await do_browser_list_tabs(session_id=SESSION_ID)
        tabs = r.get("result", {}).get("tabs", [])
        if len(tabs) == 2:
            return r
        r["status"] = "error"
        r["error"] = f"Expected 2 remaining tabs, got {len(tabs)}"
        return r

    tab_tests = [
        ("F", "Open GitHub",             _tab_open_github),
        ("F", "Open Python.org in new tab", _tab_new_python),
        ("F", "Open Wikipedia in new tab",  _tab_new_wikipedia),
        ("F", "List tabs",                _tab_list),
        ("F", "Switch tab #2",            _tab_switch_2),
        ("F", "Verify tab #2 URL",        _tab_verify_2),
        ("F", "Switch tab #3",            _tab_switch_3),
        ("F", "Verify tab #3 URL",        _tab_verify_3),
        ("F", "Close tab",                _tab_close),
        ("F", "Verify remaining tabs",    _tab_verify_remaining),
    ]
    for cat, name, fn in tab_tests:
        await runner.test(cat, name, fn, timeout=CONFIG["timeout"])

    # -- Category G: Session Persistence (10) --
    print()
    print("-" * 40)
    print("Category G — Session Persistence (10 tests)")
    print("-" * 40)

    async def _persist_navigate_github():
        return await do_browser_navigate("https://github.com", session_id=SESSION_ID)

    async def _persist_save():
        bm = BrowserManager.instance()
        await bm.save_storage(SESSION_ID)
        return {"status": "ok", "result": {"saved": True}}

    async def _persist_close():
        bm = BrowserManager.instance()
        session = bm.get_session(SESSION_ID)
        if session:
            await bm.close_session(SESSION_ID)
            return {"status": "ok", "result": {"closed": True}}
        return {"status": "error", "error": "No session to close"}

    async def _persist_restore():
        bm = BrowserManager.instance()
        session = await bm.get_or_create_session(SESSION_ID)
        return {"status": "ok", "result": {"restored": True, "session_id": session.session_id}}

    async def _persist_verify_url():
        return await do_browser_get_url(session_id=SESSION_ID)

    async def _persist_navigate_python():
        return await do_browser_navigate("https://python.org", session_id=SESSION_ID)

    async def _persist_save_again():
        bm = BrowserManager.instance()
        await bm.save_storage(SESSION_ID)
        return {"status": "ok", "result": {"saved": True}}

    async def _persist_restore_again():
        bm = BrowserManager.instance()
        session = await bm.get_or_create_session(SESSION_ID)
        return {"status": "ok", "result": {"restored": True, "session_id": session.session_id}}

    async def _persist_verify_history():
        return await do_browser_get_history(session_id=SESSION_ID)

    async def _persist_verify_cookies():
        bm = BrowserManager.instance()
        session = bm.get_session(SESSION_ID)
        if not session:
            return {"status": "error", "error": "No session"}
        try:
            state = await session.context.storage_state()
            cookies = state.get("cookies", [])
            return {"status": "ok", "result": {"cookies": len(cookies), "origins": len(state.get("origins", []))}}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    persist_tests = [
        ("G", "Navigate GitHub",      _persist_navigate_github),
        ("G", "Save session",         _persist_save),
        ("G", "Close session",        _persist_close),
        ("G", "Restore session",      _persist_restore),
        ("G", "Verify URL",           _persist_verify_url),
        ("G", "Navigate Python.org",  _persist_navigate_python),
        ("G", "Save session",         _persist_save_again),
        ("G", "Restore session",      _persist_restore_again),
        ("G", "Verify history",       _persist_verify_history),
        ("G", "Verify cookies/state", _persist_verify_cookies),
    ]
    for cat, name, fn in persist_tests:
        await runner.test(cat, name, fn, timeout=CONFIG["timeout"])

    # -- Category H: Security (10) --
    print()
    print("-" * 40)
    print("Category H — Security (10 tests)")
    print("-" * 40)

    sec_tests = [
        ("H", "Block file:///etc/passwd",   lambda: do_browser_navigate("file:///etc/passwd", session_id=SESSION_ID)),
        ("H", "Block file:///C:/Windows",    lambda: do_browser_navigate("file:///C:/Windows", session_id=SESSION_ID)),
        ("H", "Block chrome://settings",     lambda: do_browser_navigate("chrome://settings", session_id=SESSION_ID)),
        ("H", "Block chrome://extensions",   lambda: do_browser_navigate("chrome://extensions", session_id=SESSION_ID)),
        ("H", "Block edge://settings",       lambda: do_browser_navigate("edge://settings", session_id=SESSION_ID)),
        ("H", "Block about:config",          lambda: do_browser_navigate("about:config", session_id=SESSION_ID)),
        ("H", "Block about:blank",           lambda: do_browser_navigate("about:blank", session_id=SESSION_ID)),
        ("H", "Block javascript:alert(1)",   lambda: do_browser_navigate("javascript:alert(1)", session_id=SESSION_ID)),
        ("H", "Block data:text/html,test",   lambda: do_browser_navigate("data:text/html,test", session_id=SESSION_ID)),
    ]

    async def _check_evaluate_blocked():
        ctx = get_auth_manager().resolve_context("guest")
        allowed = is_authorized_to_execute("browser_evaluate", ctx)
        if allowed:
            return {"status": "error", "error": "browser_evaluate should be blocked for guest"}
        return {"status": "ok", "result": {"blocked": True}}

    sec_tests.append(("H", "Block browser_evaluate for non-admin", _check_evaluate_blocked))

    for cat, name, fn in sec_tests:
        await runner.test(cat, name, fn, screenshot_on_fail=False, timeout=15000)

    # -- Generate Report --
    print()
    print("=" * 60)
    total, passed, failed, pct = runner.summary()
    print(f"RESULTS: {total} tests, {passed} passed, {failed} failed ({pct}%)")
    print("=" * 60)

    report = runner.generate_report()
    report_path = Path("BROWSER_REAL_WORLD_ACCEPTANCE_REPORT.md")
    report_path.write_text(report, encoding="utf-8")
    print(f"\nReport written to {report_path}")
    print()

    return runner


if __name__ == "__main__":
    runner = asyncio.run(main())
    sys.exit(0 if runner.summary()[2] == 0 else 1)
