"""Unit tests for BrowserPlanner (no browser required)."""
import sys, os, asyncio, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from core.tools.browser_planner import BrowserPlanner, extract_query, detect_loop

def has_search_form(text):
    """Re-implemented from legacy benchmarks.browser_planner."""
    indicators = [
        "search", "input", "textbox", "find", "look up",
        "type here", "ask anything", "what are you looking for",
    ]
    return any(ind in text.lower() for ind in indicators)


def test_extract_query():
    assert extract_query('Search Google for "Python requests"') == "Python requests"
    assert extract_query("Search for 'hello world'") == "hello world"
    assert extract_query("find the meaning of life") == "the meaning of life"
    assert extract_query("Open Wikipedia") is None
    assert extract_query("search YouTube for cat videos") == "YouTube for cat videos"


def test_has_search_form():
    assert has_search_form("Enter your search term here")
    assert has_search_form("Type here to search")
    assert not has_search_form("Welcome to my homepage")
    assert has_search_form("What are you looking for?")


def test_detect_loop():
    assert detect_loop(["nav","find","nav","find","nav","find"])
    assert detect_loop(["nav","snap","nav","snap","nav","snap"])
    assert not detect_loop(["nav","snap","fill","press"])
    assert not detect_loop(["nav"])
    assert not detect_loop([])


def test_pre_plan_injects_snapshot():
    p = BrowserPlanner("test", 'Search for "cats"')
    calls = [{"name": "browser_navigate", "arguments": {"url": "http://example.com"}}]
    planned = p.pre_plan(calls)
    assert len(planned) == 2
    assert planned[0]["name"] == "browser_navigate"
    assert planned[1]["name"] == "browser_snapshot"
    assert p.decisions[0]["rule"] == "auto_snapshot"


def test_pre_plan_skips_snapshot_when_no_navigate():
    p = BrowserPlanner("test", 'Search for "cats"')
    calls = [{"name": "browser_fill", "arguments": {"selector": "input", "text": "test"}}]
    planned = p.pre_plan(calls)
    assert len(planned) == 1
    assert planned[0]["name"] == "browser_fill"


def test_pre_plan_injects_multiple_snapshots():
    p = BrowserPlanner("test", "task")
    calls = [
        {"name": "browser_navigate", "arguments": {"url": "http://a.com"}},
        {"name": "browser_click", "arguments": {}},
        {"name": "browser_navigate", "arguments": {"url": "http://b.com"}},
    ]
    planned = p.pre_plan(calls)
    assert len(planned) == 5
    assert planned[1]["name"] == "browser_snapshot"
    assert planned[4]["name"] == "browser_snapshot"


def test_post_plan_no_query():
    p = BrowserPlanner("test", "Just look at this page")
    extra = asyncio.run(p.post_plan([], None, None, None, None))
    assert extra == []
    assert p.decisions[-1]["rule"] == "search_fill"
    assert not p.decisions[-1]["triggered"]


def test_post_plan_result_detection_via_url():
    p = BrowserPlanner("test", 'Search for "cats"')
    p._pending_search = True

    async def mock_get_url():
        return {"status": "ok", "url": "https://www.google.com/search?q=cats"}
    async def mock_evaluate(js):
        return {"status": "ok", "result": ""}
    async def mock_snapshot():
        return {"status": "ok", "result": "page content"}

    extra = asyncio.run(p.post_plan([], None, None, None, None, mock_get_url, mock_snapshot))
    assert len(extra) == 1
    assert extra[0]["name"] == "browser_snapshot"
    assert p.decisions[-1]["rule"] == "result_detection"
    assert p.decisions[-1]["triggered"]
    assert not p._pending_search


def test_post_plan_result_detection_via_dom():
    p = BrowserPlanner("test", 'Search for "cats"')
    p._pending_search = True

    async def mock_get_url():
        return {"status": "ok", "url": "https://www.google.com/webhp"}
    async def mock_evaluate(js):
        return {"status": "ok", "result": "3:.g"}
    async def mock_snapshot():
        return {"status": "ok", "result": "results page"}

    extra = asyncio.run(p.post_plan([], None, None, None, mock_evaluate, mock_get_url, mock_snapshot))
    assert len(extra) == 1
    assert extra[0]["name"] == "browser_snapshot"
    assert p.decisions[-1]["rule"] == "result_detection"
    assert p.decisions[-1]["triggered"]


def test_post_plan_result_detection_fallback():
    p = BrowserPlanner("test", 'Search for "cats"')
    p._pending_search = True

    async def mock_get_url():
        return {"status": "ok", "url": "https://www.google.com/"}
    async def mock_evaluate(js):
        return {"status": "ok", "result": ""}
    async def mock_snapshot():
        return {"status": "ok", "result": "diagnostic snapshot"}

    extra = asyncio.run(p.post_plan([], None, None, None, mock_evaluate, mock_get_url, mock_snapshot))
    assert len(extra) == 1
    assert extra[0]["name"] == "browser_snapshot"
    assert not p.decisions[-1]["triggered"]


def test_post_plan_loop_breaker():
    p = BrowserPlanner("test", 'Search for "cats"')
    history = [
        {"name": "browser_navigate"}, {"name": "browser_find"},
        {"name": "browser_navigate"}, {"name": "browser_find"},
        {"name": "browser_navigate"}, {"name": "browser_find"},
    ]
    extra = asyncio.run(p.post_plan(history, None, None, None, None))
    assert len(extra) == 1
    assert extra[0]["name"] == "browser_snapshot"
    assert p.decisions[-1]["rule"] == "loop_breaker"


def test_pending_search_cleared_after_result_detection():
    p = BrowserPlanner("test", 'Search for "cats"')
    p._pending_search = True
    assert p._pending_search

    async def mock_get_url():
        return {"status": "ok", "url": "https://www.google.com/search?q=cats"}
    async def mock_evaluate(js):
        return {"status": "ok", "result": ""}
    async def mock_snapshot():
        return {"status": "ok", "result": "page"}

    asyncio.run(p.post_plan([], None, None, None, mock_evaluate, mock_get_url, mock_snapshot))
    assert not p._pending_search


def test_multiple_decisions_tracked():
    p = BrowserPlanner("test", 'Search for "cats"')
    calls = [{"name": "browser_navigate", "arguments": {"url": "http://x.com"}}]
    p.pre_plan(calls)
    assert len(p.decisions) == 1
    assert p.decisions[0]["rule"] == "auto_snapshot"
    assert p.decisions[0]["triggered"]
