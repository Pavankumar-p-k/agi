from __future__ import annotations

import xml.etree.ElementTree as ET
from urllib import parse, request

from ..contracts import ToolSpec


def _controller(registry):
    return getattr(registry, "browser_controller", None)


def register_browser_tools(registry) -> None:
    registry.register(
        ToolSpec("open_browser", "Open the default browser.", ["target"], parameters={"target": {"type": "string", "required": False, "default": "https://www.google.com"}}, category="browser", keywords=["open", "browser", "launch"], examples=["open browser", "open chrome"]),
        lambda target="https://www.google.com", **_: _open_target(registry, target),
    )
    registry.register(
        ToolSpec("open_url", "Open a URL in the default browser.", ["url"], parameters={"url": {"type": "string", "required": True}}, category="browser", keywords=["open", "url", "website"], examples=["open https://example.com"]),
        lambda url, **_: _open_target(registry, url),
    )
    registry.register(
        ToolSpec("search_google", "Search Google for a query.", ["query"], parameters={"query": {"type": "string", "required": True}}, category="browser", read_only=True, keywords=["search", "google", "web"], examples=["search python tutorials"]),
        lambda query, **_: _search(registry, query, site="google"),
    )
    registry.register(
        ToolSpec("search_and_summarize_google", "Search Google for a query and summarize the result page.", ["query"], parameters={"query": {"type": "string", "required": True}}, category="browser", read_only=True, keywords=["search", "summary", "google"], examples=["search bahubali and summarize"]),
        lambda query, **_: _search_and_summarize_google(registry, query),
    )
    registry.register(
        ToolSpec("search_news", "Fetch top news headlines for a query.", ["query"], parameters={"query": {"type": "string", "required": True}}, category="browser", read_only=True, keywords=["news", "latest", "headlines"], examples=["latest web3 news"]),
        lambda query, **_: _search_news(query),
    )
    registry.register(
        ToolSpec("scrape_page", "Fetch and clean readable text from a page.", ["url"], parameters={"url": {"type": "string", "required": False, "default": ""}, "max_chars": {"type": "integer", "required": False, "default": 4000}}, category="browser", read_only=True, keywords=["scrape", "extract", "page"]),
        lambda url="", max_chars=4000, **_: _scrape_page(registry, url, max_chars=max_chars),
    )
    registry.register(
        ToolSpec("summarize_page", "Summarize a web page.", ["url"], parameters={"url": {"type": "string", "required": False, "default": ""}}, category="browser", read_only=True, keywords=["summarize", "page", "website"]),
        lambda url="", **_: _summarize_page(registry, url),
    )
    registry.register(
        ToolSpec("browser_status", "Return the local browser controller status.", [], category="browser", read_only=True, keywords=["browser", "status", "session"]),
        lambda **_: _browser_status(registry),
    )
    registry.register(
        ToolSpec("browser_click_text", "Click visible text on the current browser page.", ["text"], parameters={"text": {"type": "string", "required": True}}, category="browser", permission="elevated", keywords=["browser", "click", "dom"]),
        lambda text, **_: _click_text(registry, text),
    )
    registry.register(
        ToolSpec("browser_type_text", "Fill a field on the current browser page.", ["selector", "text"], parameters={"selector": {"type": "string", "required": True}, "text": {"type": "string", "required": True}, "submit": {"type": "boolean", "required": False, "default": False}}, category="browser", permission="elevated", keywords=["browser", "type", "fill"]),
        lambda selector, text, submit=False, **_: _type_text(registry, selector, text, submit=submit),
    )


def _open_target(registry, target: str) -> dict:
    controller = _controller(registry)
    if controller is None:
        return {"success": False, "error": "Browser controller unavailable.", "target": target}
    return controller.open(target)


def _search(registry, query: str, site: str = "google") -> dict:
    controller = _controller(registry)
    if controller is None:
        return {"success": False, "error": "Browser controller unavailable.", "query": query}
    return controller.search(query, site=site)


def _search_news(query: str) -> dict:
    rss_url = "https://news.google.com/rss/search?q=" + parse.quote_plus(query)
    rss_url += "&hl=en-US&gl=US&ceid=US:en"
    with request.urlopen(rss_url, timeout=10) as response:
        payload = response.read()
    root = ET.fromstring(payload)
    headlines = []
    for item in root.findall(".//item")[:5]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if title:
            headlines.append({"title": title, "link": link})
    return {"query": query, "headlines": headlines, "summary": " | ".join(item["title"] for item in headlines[:3])}


def _scrape_page(registry, url: str, max_chars: int = 4000) -> dict:
    controller = _controller(registry)
    if controller is None:
        return {"success": False, "error": "Browser controller unavailable.", "url": url}
    page = controller.scrape_page(url, max_chars=max_chars)
    if page.get("success", True):
        page["summary"] = page.get("text", "")[:300]
    return page


def _summarize_page(registry, url: str) -> dict:
    page = _scrape_page(registry, url)
    if page.get("success") is False:
        return page
    ai = registry.invoke("summarize_text", text=page.get("text", ""))
    return {
        "success": True,
        "url": page.get("url", url),
        "title": page.get("title", ""),
        "summary": ai.get("summary", page.get("summary", "")),
    }


def _search_and_summarize_google(registry, query: str) -> dict:
    opened = _search(registry, query, site="google")
    summary = _summarize_page(registry, opened.get("url", ""))
    return {
        "success": opened.get("success", True) and summary.get("success", True),
        "query": query,
        "url": opened.get("url", ""),
        "title": summary.get("title", ""),
        "summary": summary.get("summary", ""),
        "mode": opened.get("mode", ""),
    }


def _browser_status(registry) -> dict:
    controller = _controller(registry)
    if controller is None:
        return {"success": False, "error": "Browser controller unavailable."}
    payload = controller.status()
    payload["success"] = True
    return payload


def _click_text(registry, text: str) -> dict:
    controller = _controller(registry)
    if controller is None:
        return {"success": False, "error": "Browser controller unavailable.", "text": text}
    return controller.click_text(text)


def _type_text(registry, selector: str, text: str, submit: bool = False) -> dict:
    controller = _controller(registry)
    if controller is None:
        return {"success": False, "error": "Browser controller unavailable.", "selector": selector}
    return controller.type_text(selector, text, submit=submit)
