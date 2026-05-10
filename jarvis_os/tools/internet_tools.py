from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib import parse, request

from ..contracts import ToolSpec


def register_internet_tools(registry) -> None:
    registry.register(
        ToolSpec("fetch_url", "Fetch raw text content from a URL.", ["url"], parameters={"url": {"type": "string", "required": True}}, category="research", read_only=True, keywords=["fetch", "url", "download"]),
        lambda url="", **_: _fetch_url(url),
    )
    registry.register(
        ToolSpec("download_file", "Download a remote file to disk.", ["url", "destination"], parameters={"url": {"type": "string", "required": True}, "destination": {"type": "string", "required": True}}, category="research", permission="elevated", keywords=["download", "file", "save"]),
        lambda url, destination, **_: _download_file(url, destination),
    )
    registry.register(
        ToolSpec("web_search", "Do a lightweight web search.", ["query"], parameters={"query": {"type": "string", "required": True}}, category="research", read_only=True, keywords=["search", "web", "lookup"]),
        lambda query="", **_: _web_search(query),
    )
    registry.register(
        ToolSpec("rss_news_fetch", "Read headlines from Google News RSS.", ["query"], parameters={"query": {"type": "string", "required": True}}, category="research", read_only=True, keywords=["rss", "news", "headlines"]),
        lambda query="", **_: _rss_news_fetch(query),
    )


def _fetch_url(url: str) -> dict:
    with request.urlopen(url, timeout=10) as response:
        body = response.read().decode("utf-8", errors="replace")
    return {"url": url, "content": body[:5000], "length": len(body)}


def _download_file(url: str, destination: str) -> dict:
    target = Path(destination).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with request.urlopen(url, timeout=20) as response:
        target.write_bytes(response.read())
    return {"url": url, "destination": str(target), "bytes": target.stat().st_size}


def _web_search(query: str) -> dict:
    url = "https://api.duckduckgo.com/?" + parse.urlencode(
        {"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"}
    )
    with request.urlopen(url, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    abstract = (payload.get("AbstractText") or "").strip()
    heading = (payload.get("Heading") or "").strip()
    related = payload.get("RelatedTopics") or []
    fallback = ""
    for item in related:
        if isinstance(item, dict) and item.get("Text"):
            fallback = item["Text"]
            break
    summary = abstract or fallback or "No direct answer returned."
    return {"query": query, "heading": heading, "summary": summary}


def _rss_news_fetch(query: str) -> dict:
    rss_url = "https://news.google.com/rss/search?q=" + parse.quote_plus(query)
    rss_url += "&hl=en-US&gl=US&ceid=US:en"
    with request.urlopen(rss_url, timeout=10) as response:
        payload = response.read()
    root = ET.fromstring(payload)
    items = []
    for item in root.findall(".//item")[:5]:
        items.append(
            {
                "title": (item.findtext("title") or "").strip(),
                "link": (item.findtext("link") or "").strip(),
            }
        )
    return {"query": query, "items": items, "summary": " | ".join(entry["title"] for entry in items[:3])}
