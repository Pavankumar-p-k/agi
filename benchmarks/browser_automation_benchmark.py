"""Browser Automation Benchmark — measures tool selection + planner enforcement.

Tests 3 configurations across 15 browser tasks in 5 categories:

  raw     — LLM with tool schemas, NO planner enforcement
  planner — LLM + BrowserPlanner pre_plan/post_plan enforcement
  full    — LLM + BrowserPlanner + full system (memory/scheduler prompts)

Metrics:
  - tool_selection_accuracy: fraction of required tools selected
  - planner_injection_rate: fraction of missing tools the planner added
  - task_success: all required tools selected (or injected by planner)
  - turns, duration, unique_tools

Usage:
    python benchmarks/browser_automation_benchmark.py
    python benchmarks/browser_automation_benchmark.py --smoke
    python benchmarks/browser_automation_benchmark.py --model llama3.1:8b

Environment:
    OLLAMA_URL   (default: http://localhost:11434)
    AGENT_MODEL  (default: qwen2.5:7b)
    MAX_TURNS    (default: 12)
    REPORT_DIR   (default: benchmark_reports)
"""

import argparse
import asyncio
import httpx
import json
import logging
import os
import shutil
import sys
import tempfile
import time
import traceback
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
logger = logging.getLogger("browser_bench")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("AGENT_MODEL", "qwen2.5:7b")
MAX_TURNS = int(os.environ.get("MAX_TURNS", "4"))
TASK_TIMEOUT = int(os.environ.get("TASK_TIMEOUT", "60"))
REPORT_DIR = os.environ.get("REPORT_DIR", "benchmark_reports")
os.makedirs(REPORT_DIR, exist_ok=True)

SNAPSHOT_TEMPLATE = {
    "title": "Mock Page",
    "url": "https://example.com",
    "headings": [{"tag": "h1", "text": "Mock Heading"}],
    "links": [{"text": "Example Link", "href": "https://example.com/page2"}],
    "inputs": [{"placeholder": "search", "name": "q", "type": "text", "label": "Search"}],
    "buttons": [{"text": "Search"}],
    "forms": [{"action": "/search", "method": "GET"}],
}

# Track page state across mock calls
_mock_state = {
    "current_url": "",
    "page_loaded": False,
    "search_filled": False,
    "search_submitted": False,
    "result_clicked": False,
    "snapshot_count": 0,
}


@dataclass
class BrowserTask:
    id: str
    category: str
    prompt: str
    required_tools: list[str]
    min_correct: int = 1
    mock_responses: dict[str, Any] = field(default_factory=dict)
    validation_fn: str = ""


@dataclass
class TaskResult:
    task_id: str
    category: str
    config_name: str
    success: bool = False
    turns: int = 0
    tool_calls: list[str] = field(default_factory=list)
    unique_tools: set[str] = field(default_factory=set)
    planner_injected: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    error: str = ""
    final_output: str = ""
    fsm_metrics: dict[str, Any] = field(default_factory=dict)


TASKS: list[BrowserTask] = [
    # ── Category 1: Search & Extract ──────────────────────────
    BrowserTask(
        id="search_extract_1",
        category="search_extract",
        prompt="Search Google for 'qwen2.5 coder benchmark results' and tell me what the first result title is.",
        required_tools=["browser_navigate", "browser_snapshot", "browser_fill", "browser_press"],
        min_correct=3,
    ),
    BrowserTask(
        id="search_extract_2",
        category="search_extract",
        prompt="Search Wikipedia for 'Transformer architecture' and summarize the first paragraph.",
        required_tools=["browser_navigate", "browser_fill", "browser_press", "browser_snapshot"],
        min_correct=3,
    ),
    BrowserTask(
        id="search_extract_3",
        category="search_extract",
        prompt="Look up the current price of NVIDIA stock on a financial site.",
        required_tools=["browser_navigate", "browser_snapshot"],
        min_correct=2,
    ),
    BrowserTask(
        id="search_extract_4",
        category="search_extract",
        prompt="Search for 'Python 3.13 release date' on DuckDuckGo and read the result snippet.",
        required_tools=["browser_navigate", "browser_fill", "browser_press", "browser_snapshot"],
        min_correct=3,
    ),

    # ── Category 2: Multi-page Navigation ────────────────────
    BrowserTask(
        id="multi_page_1",
        category="multi_page",
        prompt="Go to Hacker News, open the top post, and summarize what it is about.",
        required_tools=["browser_navigate", "browser_snapshot", "browser_click"],
        min_correct=2,
    ),
    BrowserTask(
        id="multi_page_2",
        category="multi_page",
        prompt="Browse GitHub trending repositories and list the top 3 projects with descriptions.",
        required_tools=["browser_navigate", "browser_snapshot"],
        min_correct=2,
    ),
    BrowserTask(
        id="multi_page_3",
        category="multi_page",
        prompt="Go to the FastAPI documentation, find the tutorial section, and read the first guide.",
        required_tools=["browser_navigate", "browser_snapshot", "browser_click"],
        min_correct=2,
    ),

    # ── Category 3: Form Filling ─────────────────────────────
    BrowserTask(
        id="form_fill_1",
        category="form_fill",
        prompt="Search Amazon for 'wireless mouse' and find the price of the first result.",
        required_tools=["browser_navigate", "browser_fill", "browser_press", "browser_snapshot"],
        min_correct=3,
    ),
    BrowserTask(
        id="form_fill_2",
        category="form_fill",
        prompt="Go to Reddit, search for 'machine learning beginner', and read the top post.",
        required_tools=["browser_navigate", "browser_fill", "browser_press", "browser_snapshot", "browser_click"],
        min_correct=3,
    ),
    BrowserTask(
        id="form_fill_3",
        category="form_fill",
        prompt="Search YouTube for 'Python tutorial 2025' and get the title of the first video.",
        required_tools=["browser_navigate", "browser_fill", "browser_press", "browser_snapshot"],
        min_correct=3,
    ),

    # ── Category 4: Login-free Workflows ─────────────────────
    BrowserTask(
        id="workflow_1",
        category="workflow",
        prompt="Go to Wikipedia, search for 'Artificial Intelligence', read the article, and extract 3 key facts.",
        required_tools=["browser_navigate", "browser_snapshot", "browser_fill", "browser_press"],
        min_correct=3,
    ),
    BrowserTask(
        id="workflow_2",
        category="workflow",
        prompt="Search DuckDuckGo for 'climate change solutions', open the first non-ad result, and summarize it.",
        required_tools=["browser_navigate", "browser_fill", "browser_press", "browser_snapshot", "browser_click"],
        min_correct=3,
    ),

    # ── Category 5: Data Collection ──────────────────────────
    BrowserTask(
        id="data_collect_1",
        category="data_collect",
        prompt="Collect the top 5 AI/ML conferences in 2025 with dates and locations. Search and compile results.",
        required_tools=["browser_navigate", "browser_fill", "browser_press", "browser_snapshot"],
        min_correct=3,
    ),
    BrowserTask(
        id="data_collect_2",
        category="data_collect",
        prompt="Find 3 Python libraries for data visualization and list their GitHub star counts.",
        required_tools=["browser_navigate", "browser_snapshot"],
        min_correct=2,
    ),
    BrowserTask(
        id="data_collect_3",
        category="data_collect",
        prompt="Compare prices of the iPhone 16 and Samsung Galaxy S25 from a tech comparison search.",
        required_tools=["browser_navigate", "browser_fill", "browser_press", "browser_snapshot"],
        min_correct=3,
    ),
]


# ── Tool schemas ────────────────────────────────────────────────

def _build_tool_schemas():
    from core.tools.schemas_browser import FUNCTION_TOOL_SCHEMAS as BROWSER_SCHEMAS
    from core.tools.schemas import FUNCTION_TOOL_SCHEMAS
    seen = set()
    combined = []
    for s in FUNCTION_TOOL_SCHEMAS:
        name = s.get("function", {}).get("name", "")
        if name not in seen:
            seen.add(name)
            combined.append(s)
    for s in BROWSER_SCHEMAS:
        name = s.get("function", {}).get("name", "")
        if name not in seen:
            seen.add(name)
            combined.append(s)
    return combined

TOOL_SCHEMAS = _build_tool_schemas()


# ── Prompts ─────────────────────────────────────────────────────

BASE_PROMPT = (
    "You are a browser automation agent with access to web browsing tools.\n\n"
    "Available tools: browser_navigate, browser_snapshot, browser_fill, "
    "browser_click, browser_press, browser_evaluate, web_search, web_fetch.\n\n"
    "Use tools to accomplish the task. Navigate to pages, read their content, "
    "and keep using tools until you have enough information. "
    "Do NOT stop after one tool call."
)

FULL_PROMPT = (
    "You are a browser automation agent with access to web browsing tools.\n\n"
    "Available tools: browser_navigate, browser_snapshot, browser_fill, "
    "browser_click, browser_press, browser_evaluate, web_search, web_fetch.\n\n"
    "Use tools to accomplish the task. Navigate to pages, read their content, "
    "and keep using tools until you have enough information. "
    "Do NOT stop after one tool call.\n\n"
    "MEMORY GUIDANCE:\n"
    "- For search: navigate to a search engine, fill the form, press Enter, then snapshot results\n"
    "- For multi-page: snapshot the list page, click a result link, snapshot the detail page\n"
    "- Never stop after one tool call — always follow up\n\n"
    "PLANNER RULES:\n"
    "1. After browser_navigate, always call browser_snapshot\n"
    "2. When you see a search form, fill it and press Enter\n"
    "3. After search, check the results with browser_snapshot\n"
    "4. For multi-page tasks, navigate between pages using browser_click\n\n"
    "WORKFLOW GUIDANCE:\n"
    "Phase 1: Navigate to the relevant page\n"
    "Phase 2: Fill in search terms if needed\n"
    "Phase 3: Read the results\n"
    "Phase 4: If more info needed, click through"
)


# ── Mock Browser Tools ──────────────────────────────────────────

_mock_snapshot_cache: dict[str, dict] = {}

def _make_snapshot(url: str, title: str = "Mock Page",
                   has_search: bool = False, has_login: bool = False,
                   has_results: bool = False, content_text: str = "") -> dict:
    snap = dict(SNAPSHOT_TEMPLATE)
    snap["url"] = url
    snap["title"] = title
    snap["headings"] = [{"tag": "h1", "text": title}]
    snap["links"] = [{"text": "Result Link 1", "href": "https://example.com/result1"},
                     {"text": "Result Link 2", "href": "https://example.com/result2"}]

    if has_search or "search" in url.lower() or "google" in url.lower() or "duckduckgo" in url.lower():
        snap["inputs"] = [{"type": "text", "name": "q", "placeholder": "search", "label": "Search"}]
        snap["forms"] = [{"action": "/search", "method": "GET"}]
    else:
        snap["inputs"] = []

    if has_login:
        snap["inputs"] = snap.get("inputs", []) + [
            {"type": "email", "name": "email", "placeholder": "Email"},
            {"type": "password", "name": "password", "placeholder": "Password"},
        ]

    if has_results or "result" in url.lower() or "search" in url.lower():
        snap["links"] = [
            {"text": "First Result — Important Topic", "href": "https://example.com/result1"},
            {"text": "Second Result — Another Topic", "href": "https://example.com/result2"},
            {"text": "Third Result — Related Content", "href": "https://example.com/result3"},
        ]

    if content_text:
        snap["paragraphs"] = [{"text": content_text}]
    else:
        snap["paragraphs"] = [{"text": f"This is sample content for {title}. It contains enough text to simulate a real page."}]

    return snap


_mock_page_store: dict[str, Any] = {
    "snapshots": 0, "url": "", "search_filled": False, "query": ""
}


def _make_navigate_result(url: str) -> dict:
    """Return a navigate result that clearly signals page is loaded and readable."""
    domain = "example.com"
    try:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc
    except Exception:
        pass

    has_search = any(d in domain for d in ["google", "duckduckgo", "bing", "yahoo",
                                            "wikipedia", "amazon", "youtube", "reddit", "github"])
    snap = _make_snapshot(url, title=f"Page at {domain}", has_search=has_search)
    _mock_snapshot_cache["last"] = snap
    _mock_page_store["url"] = url
    _mock_page_store["snapshots"] = 0
    _mock_page_store["search_filled"] = False
    _mock_page_store["query"] = ""

    summary = f"Loaded {url}. Title: {snap['title']}. "
    summary += "This page has a search form with an input field. " if has_search else ""
    summary += "Use browser_snapshot to read the full page content."

    return {
        "success": True,
        "url": url,
        "title": snap["title"],
        "status": "loaded",
        "summary": summary,
        "has_search_form": has_search,
        "result": snap,
    }


async def _mock_browser_navigate(url: str) -> dict:
    return _make_navigate_result(url)


async def _mock_browser_snapshot() -> dict:
    snap = _mock_snapshot_cache.get("last", _make_snapshot("https://example.com"))
    _mock_page_store["snapshots"] += 1

    has_form = len(snap.get("inputs", [])) > 0
    has_results = "result" in snap.get("url", "").lower() or "search" in snap.get("url", "").lower()

    summary_parts = [f"Page title: {snap['title']}"]
    if snap.get("headings"):
        summary_parts.append(f"Heading: {snap['headings'][0]['text']}")
    if snap.get("links"):
        summary_parts.append(f"Links: {', '.join(l['text'] for l in snap['links'][:3])}")
    if has_form:
        summary_parts.append("Search form detected: input field with placeholder 'search'")
    if snap.get("paragraphs"):
        summary_parts.append(f"Content: {snap['paragraphs'][0]['text'][:120]}...")
    if has_results:
        summary_parts.append("Search results are visible on this page.")
    summary_parts.append("Use browser_fill + browser_press to search, or browser_click to open a link.")

    return {
        "success": True,
        "url": snap["url"],
        "title": snap["title"],
        "summary": " | ".join(summary_parts),
        "inputs_detected": has_form,
        "results_detected": has_results,
        "result": snap,
    }


async def _mock_browser_fill(selector: str, text: str) -> dict:
    _mock_page_store["search_filled"] = True
    _mock_page_store["query"] = text
    return {
        "success": True,
        "action": "filled",
        "selector": selector,
        "text": text,
        "summary": f"Filled search input with: {text}. Now press Enter with browser_press.",
        "next_step": f"Call browser_press with selector={selector} and key=Enter to submit.",
    }


async def _mock_browser_press(selector: str, key: str) -> dict:
    query = _mock_page_store.get("query", "search query")
    result_snap = _make_snapshot(
        f"https://example.com/search?q={query.replace(' ', '+')}",
        title=f"Search results for {query}",
        has_search=True,
        has_results=True,
        content_text=f"Here are the search results for '{query}'. "
                     f"First result: Important Topic with full details. "
                     f"Second result: Another topic with more information. "
                     f"Third result: Related content worth reading."
    )
    _mock_snapshot_cache["last"] = result_snap
    _mock_page_store["url"] = result_snap["url"]
    return {
        "success": True,
        "action": "pressed",
        "key": key,
        "url": result_snap["url"],
        "title": result_snap["title"],
        "summary": f"Search submitted. Results page loaded. "
                   f"Use browser_snapshot to read search results, "
                   f"or browser_click to open a result link.",
        "result": result_snap,
    }


async def _mock_browser_click(selector: str) -> dict:
    detail_snap = _make_snapshot(
        "https://example.com/detail",
        title="Detail Page - Full Article",
        content_text="This is the full detailed content page. It contains all the "
                     "information you need to answer the user's question. "
                     "The page covers the topic thoroughly with multiple sections."
    )
    _mock_snapshot_cache["last"] = detail_snap
    _mock_page_store["url"] = detail_snap["url"]
    return {
        "success": True,
        "url": detail_snap["url"],
        "title": detail_snap["title"],
        "summary": f"Navigated to detail page: {detail_snap['title']}. "
                   f"Use browser_snapshot to read the full article content.",
        "result": detail_snap,
    }


async def _mock_browser_evaluate(js: str) -> dict:
    result = None
    js_lower = js.lower()
    if "search" in js_lower or "selector" in js_lower:
        result = "input[name='q']"
    elif "result" in js_lower or "findBestUrl" in js_lower:
        result = "https://example.com/result1"
    elif "login" in js_lower or "password" in js_lower:
        result = None
    elif "setTimeout" in js_lower or "promise" in js_lower:
        result = "waited"
    elif "scoreLink" in js_lower:
        result = "https://example.com/result1"
    elif "click" in js_lower:
        result = "clicked"
    elif "submit" in js_lower:
        result = "submitted"
    else:
        result = None

    return {
        "success": True,
        "result": json.dumps(result) if result else "null",
        "output": json.dumps(result) if result else "null",
    }


_mock_handlers: dict[str, Any] = {
    "browser_navigate": _mock_browser_navigate,
    "browser_snapshot": _mock_browser_snapshot,
    "browser_fill": _mock_browser_fill,
    "browser_press": _mock_browser_press,
    "browser_click": _mock_browser_click,
    "browser_evaluate": _mock_browser_evaluate,
    "browser_screenshot": lambda: {"success": True, "result": {"screenshot": "base64_fake"}},
    "browser_get_url": lambda: {"success": True, "url": "https://example.com"},
    "browser_get_title": lambda: {"success": True, "title": "Mock Page"},
    "browser_current_state": lambda: {"success": True, "result": SNAPSHOT_TEMPLATE},
    "browser_health": lambda: {"success": True, "status": "healthy"},
}

VALID_TOOLS = set(_mock_handlers.keys()) | {
    "web_search", "web_fetch", "read_file", "write_file",
    "python", "bash", "send_email",
}


async def execute_tool(tool_name: str, arguments: dict) -> dict:
    if tool_name not in VALID_TOOLS:
        return {"error": f"Unknown tool: {tool_name}"}

    handler = _mock_handlers.get(tool_name)
    if handler:
        try:
            if tool_name == "browser_navigate":
                return await handler(arguments.get("url", ""))
            elif tool_name == "browser_fill":
                return await handler(arguments.get("selector", ""), arguments.get("text", ""))
            elif tool_name == "browser_press":
                return await handler(arguments.get("selector", ""), arguments.get("key", ""))
            elif tool_name == "browser_click":
                return await handler(arguments.get("selector", ""))
            elif tool_name == "browser_evaluate":
                return await handler(arguments.get("code", arguments.get("script", "")))
            else:
                result = handler()
                if asyncio.iscoroutine(result):
                    return await result
                return result
        except Exception as e:
            logging.getLogger(__name__).error("Benchmark task failed: %s", e, exc_info=True)
            return {"error": "Benchmark task failed"}

    # Non-browser tools return a generic success
    return {"success": True, "result": f"{tool_name} completed"}


# ── BrowserPlanner Wrapper ────────────────────────────────────

def _run_browser_planner(tool_blocks, ctx: dict | None, task_prompt: str):
    """Run BrowserPlanner pre_plan + post_plan on tool blocks.
    
    Returns (final_tool_names, injected_tool_names, updated_ctx).
    """
    from core.tools._constants import ToolBlock
    from core.tools.browser_planner import BrowserPlanner

    if ctx is None:
        ctx = BrowserPlanner.init(task_prompt)

    # pre_plan
    planned, ctx = BrowserPlanner.pre_plan(tool_blocks, ctx)

    # Simulate execution for post_plan (use mock results)
    executed_blocks = list(planned)
    mock_results = []
    for tb in executed_blocks:
        name = tb.tool_type if hasattr(tb, 'tool_type') else (isinstance(tb, dict) and tb.get("name", ""))
        if not name:
            name = tb.tool_type
        tool_name = name if isinstance(name, str) else ""
        args = {}
        try:
            args = json.loads(tb.content) if hasattr(tb, 'content') else {}
        except Exception:
            args = {}
        result = asyncio.run(execute_tool(tool_name, args))
        mock_results.append({"result": result, "block_type": tool_name})

    # post_plan (up to 5 iterations like tool_call_node)
    injected = []
    for _ in range(5):
        extra, ctx = BrowserPlanner.post_plan(mock_results, executed_blocks, ctx)
        if not extra:
            break
        for eb in extra:
            injected.append(eb.tool_type)
            executed_blocks.append(eb)
            tool_name = eb.tool_type
            args = {}
            try:
                args = json.loads(eb.content) if hasattr(eb, 'content') else {}
            except Exception:
                args = {}
            result = asyncio.run(execute_tool(tool_name, args))
            mock_results.append({"result": result, "block_type": tool_name})

    final_names = []
    for tb in executed_blocks:
        name = getattr(tb, 'tool_type', None) or (tb.get("name") if isinstance(tb, dict) else "")
        if name:
            final_names.append(name)

    return final_names, injected, ctx


# ── LLM Interface ─────────────────────────────────────────────

async def call_llm(messages, schemas=None):
    """Call Ollama with tool schemas."""
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "options": {"num_predict": 2048, "temperature": 0.1},
    }
    payload["tools"] = schemas or TOOL_SCHEMAS

    data = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=TASK_TIMEOUT) as client:
                resp = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
                if resp.status_code == 400:
                    logger.warning("LLM 400 (attempt %d/3): %s", attempt+1, resp.text[:200])
                    await asyncio.sleep(1)
                    continue
                resp.raise_for_status()
                data = resp.json()
                break
        except Exception as e:
            logger.error("LLM call failed (attempt %d/3): %s", attempt+1, e)
            if attempt == 2:
                return "", []
            await asyncio.sleep(1)

    if data is None:
        return "", []

    msg = data.get("message", {})
    content = msg.get("content", "")
    raw_tool_calls = msg.get("tool_calls", [])
    tool_calls = []
    for tc in raw_tool_calls:
        fn = tc.get("function", tc)
        name = fn.get("name", "")
        args_raw = fn.get("arguments", "{}")
        if isinstance(args_raw, str):
            try:
                args = json.loads(args_raw)
            except json.JSONDecodeError:
                args = {}
        else:
            args = args_raw
        tool_calls.append({"name": name, "arguments": args})
    return content, tool_calls


# ── Task Runner ───────────────────────────────────────────────

async def run_task(task: BrowserTask, config_name: str, enable_planner: bool) -> TaskResult:
    result = TaskResult(task_id=task.id, category=task.category, config_name=config_name)

    if config_name == "full":
        system_prompt = FULL_PROMPT
    else:
        system_prompt = BASE_PROMPT

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task.prompt},
    ]

    planner_ctx = None
    start = time.time()

    try:
        for turn in range(MAX_TURNS):
            content, tool_calls = await call_llm(messages)
            result.turns = turn + 1

            if not tool_calls:
                result.final_output = content
                result.success = True
                break

            # Record LLM-selected tools
            llm_tool_names = [tc.get("name", "") for tc in tool_calls]
            result.tool_calls.extend(llm_tool_names)
            result.unique_tools.update(llm_tool_names)

            # Convert to ToolBlocks for planner
            from core.tools._constants import ToolBlock
            llm_blocks = []
            for tc in tool_calls:
                name = tc.get("name", "")
                args = tc.get("arguments", {})
                llm_blocks.append(ToolBlock(tool_type=name, content=json.dumps(args)))

            # Detect loop: LLM called same tool 3+ times consecutively
            from collections import Counter
            recent = result.tool_calls[-5:]
            if len(recent) >= 3 and len(set(recent[-3:])) == 1:
                result.error = f"loop_detected: {recent[-1]} called {len(recent)} times"
                break

            # Planner enforcement
            if enable_planner and llm_blocks:
                scheduled_blocks: list[tuple[Any, dict]] = []
                injected_names = []

                # pre_plan (auto-snapshot after navigate)
                planned_blocks, planner_ctx = _run_pre_plan(llm_blocks, planner_ctx, task.prompt)

                # Execute planned blocks
                for tb in planned_blocks:
                    tool_name = tb.tool_type
                    args = {}
                    try:
                        args = json.loads(tb.content) if hasattr(tb, 'content') else {}
                    except Exception:
                        args = {}
                    tool_result = await execute_tool(tool_name, args)
                    scheduled_blocks.append((tb, tool_result))
                    if tool_name not in llm_tool_names:
                        injected_names.append(tool_name)

                # post_plan loop
                # Match the real pipeline (nodes.py): pass ALL accumulated results
                # but only the CURRENT iteration's blocks as executed_blocks
                # (first iteration = all blocks, subsequent = injected blocks only).
                _pp_blocks = [tb for tb, _ in scheduled_blocks]
                for ppi in range(5):
                    executed_results = [{"result": tr, "block_type": tb.tool_type}
                                        for tb, tr in scheduled_blocks]
                    extra, planner_ctx = _run_post_plan(executed_results,
                                                        _pp_blocks,
                                                        planner_ctx)
                    if not extra:
                        break
                    logger.warning("  post_plan iter %d: injected %s", ppi,
                                   [eb.tool_type for eb in extra])
                    _pp_blocks = []
                    for eb in extra:
                        injected_names.append(eb.tool_type)
                        tool_name = eb.tool_type
                        args = {}
                        if hasattr(eb, 'content') and eb.content:
                            try:
                                args = json.loads(eb.content)
                            except (json.JSONDecodeError, TypeError):
                                # Non-JSON content (e.g. evaluate JS) — pass as raw value
                                args = {"code": eb.content} if tool_name in ("browser_evaluate",) else {"content": eb.content}
                        tool_result2 = await execute_tool(tool_name, args)
                        scheduled_blocks.append((eb, tool_result2))
                        _pp_blocks.append(eb)

                result.planner_injected.extend(injected_names)
                result.unique_tools.update(injected_names)

                # Capture FSM metrics from planner_ctx
                if planner_ctx and "fsm" in planner_ctx:
                    fsm = planner_ctx["fsm"]
                    result.fsm_metrics = {
                        "final_state": fsm.get("state", ""),
                        "transitions": fsm.get("transitions", 0),
                        "loops_prevented": fsm.get("loops_prevented", 0),
                        "page_recognitions": fsm.get("page_recognitions", 0),
                        "timeouts": fsm.get("timeouts", 0),
                        "forced_transitions": fsm.get("forced_transitions", 0),
                        "total_actions": fsm.get("total_actions", 0),
                        "actions_in_last_state": fsm.get("actions_in_state", 0),
                    }

                # Feed results back to LLM (real tool results)
                for tb, tr in scheduled_blocks:
                    tool_name = tb.tool_type
                    args = {}
                    try:
                        args = json.loads(tb.content) if hasattr(tb, 'content') else {}
                    except Exception:
                        args = {}
                    messages.append({
                        "role": "assistant",
                        "content": f"Calling {tool_name}",
                        "tool_calls": [{"function": {"name": tool_name, "arguments": args}}],
                    })
                    messages.append({
                        "role": "tool",
                        "content": json.dumps(tr),
                        "name": tool_name,
                    })

            else:
                # No planner: execute LLM's chosen tools directly
                for tc in tool_calls:
                    name = tc.get("name", "")
                    args = tc.get("arguments", {})
                    tool_result = await execute_tool(name, args)
                    messages.append({
                        "role": "assistant",
                        "content": content if content else f"Calling {name}",
                        "tool_calls": [{"function": {"name": name, "arguments": args}}],
                    })
                    messages.append({
                        "role": "tool",
                        "content": json.dumps(tool_result),
                        "name": name,
                    })
        else:
            result.error = f"max_turns ({MAX_TURNS}) exceeded"

    except asyncio.CancelledError:
        result.error = "cancelled"
    except Exception as e:
        result.error = f"{type(e).__name__}: {e}"
        traceback.print_exc()

    result.duration_seconds = round(time.time() - start, 2)
    return result


def _run_pre_plan(tool_blocks, ctx, task_prompt):
    from core.tools.browser_planner import BrowserPlanner
    if ctx is None:
        ctx = BrowserPlanner.init(task_prompt)
    planned, ctx = BrowserPlanner.pre_plan(tool_blocks, ctx)
    return planned, ctx


def _run_post_plan(executed_results, executed_blocks, ctx):
    from core.tools.browser_planner import BrowserPlanner
    return BrowserPlanner.post_plan(executed_results, executed_blocks, ctx)


# ── Success Criteria ──────────────────────────────────────────

def evaluate_tool_selection(task: BrowserTask, result: TaskResult) -> dict:
    """Evaluate which required tools were selected (by LLM or planner)."""
    all_tools = result.tool_calls + result.planner_injected
    selected = set(all_tools)
    required = set(task.required_tools)
    matched = selected & required
    missing = required - selected
    return {
        "required": task.required_tools,
        "selected_by_llm": list(set(result.tool_calls) & required),
        "injected_by_planner": list(set(result.planner_injected) & required),
        "matched_count": len(matched),
        "required_count": len(required),
        "missing": list(missing),
        "accuracy": len(matched) / max(len(required), 1),
    }


def evaluate_task_success(task: BrowserTask, result: TaskResult, tool_eval: dict) -> bool:
    if result.error and "max_turns" not in result.error:
        return False
    if result.turns == 0:
        return False
    if tool_eval["matched_count"] < task.min_correct:
        return False
    return True


# ── Benchmark Runner ──────────────────────────────────────────

@dataclass
class BrowserBenchmarkReport:
    timestamp: str
    model: str
    tasks: list[dict] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    per_task_details: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "model": self.model,
            "tasks": self.tasks,
            "per_task_details": self.per_task_details,
            "summary": self.summary,
        }

    def save(self, path: str) -> None:
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)
        logger.info("Report saved: %s", path)


CONFIGS = {
    "raw": {"planner": False, "prompt": "base"},
    "planner": {"planner": True, "prompt": "base"},
    "full": {"planner": True, "prompt": "full"},
}


def _compute_summary(all_results: list[TaskResult]) -> dict[str, Any]:
    by_config: dict[str, list[TaskResult]] = {}
    for r in all_results:
        by_config.setdefault(r.config_name, []).append(r)

    configs = {}
    for cname, tasks in by_config.items():
        total = len(tasks)
        task_ids = [t.task_id for t in tasks]
        tool_evals = []
        all_tools_llm = []
        all_tools_planner = []
        all_durations = []
        successes = 0
        matched_counts = []

        for t in tasks:
            task_obj = next(tk for tk in TASKS if tk.id == t.task_id)
            te = evaluate_tool_selection(task_obj, t)
            tool_evals.append(te)
            all_tools_llm.extend(t.tool_calls)
            all_tools_planner.extend(t.planner_injected)
            all_durations.append(t.duration_seconds)
            success = evaluate_task_success(task_obj, t, te)
            if success:
                successes += 1
            matched_counts.append(te["matched_count"])

        configs[cname] = {
            "total_tasks": total,
            "successes": successes,
            "success_rate": round(successes / max(total, 1), 3),
            "avg_turns": round(sum(t.turns for t in tasks) / max(total, 1), 1),
            "avg_duration_seconds": round(sum(all_durations) / max(total, 1), 2),
            "avg_tool_selection_accuracy": round(
                sum(te["accuracy"] for te in tool_evals) / max(len(tool_evals), 1), 3
            ),
            "avg_matched_tools": round(sum(matched_counts) / max(len(matched_counts), 1), 2),
            "total_tool_calls": len(all_tools_llm),
            "total_planner_injections": len(all_tools_planner),
            "unique_tools_count": len(set(all_tools_llm + all_tools_planner)),
            "tool_frequency": dict(sorted(
                Counter(all_tools_llm + all_tools_planner).items(), key=lambda x: -x[1]
            )[:10]),
            "errors": [t.error for t in tasks if t.error],
            "fsm_metrics": {
                "total_transitions": sum(len(t.fsm_metrics.get("transitions", [])) if isinstance(t.fsm_metrics.get("transitions"), list) else t.fsm_metrics.get("transitions", 0) for t in tasks if t.fsm_metrics),
                "total_loops_prevented": sum(t.fsm_metrics.get("loops_prevented", 0) for t in tasks if t.fsm_metrics),
                "total_page_recognitions": sum(t.fsm_metrics.get("page_recognitions", 0) for t in tasks if t.fsm_metrics),
                "total_timeouts": sum(t.fsm_metrics.get("timeouts", 0) for t in tasks if t.fsm_metrics),
                "total_forced_transitions": sum(t.fsm_metrics.get("forced_transitions", 0) for t in tasks if t.fsm_metrics),
                "final_states": dict(Counter(t.fsm_metrics.get("final_state", "") for t in tasks if t.fsm_metrics)),
            },
        }

    # Deltas vs raw
    baseline = configs.get("raw", {})
    deltas = {}
    for cname, stats in configs.items():
        if cname == "raw":
            continue
        delta_sr = stats["success_rate"] - baseline.get("success_rate", 0)
        delta_acc = stats["avg_tool_selection_accuracy"] - baseline.get("avg_tool_selection_accuracy", 0)
        delta_turns = baseline.get("avg_turns", 0) - stats.get("avg_turns", 0)
        deltas[cname] = {
            "delta_success_rate": round(delta_sr, 3),
            "delta_tool_selection_accuracy": round(delta_acc, 3),
            "delta_avg_turns": round(delta_turns, 1),
        }

    return {"by_config": configs, "deltas": deltas}


async def run_benchmark(max_tasks: int = 0, categories: list[str] | None = None,
                        smoke: bool = False) -> BrowserBenchmarkReport:
    report = BrowserBenchmarkReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        model=MODEL,
    )

    # Filter tasks
    tasks = TASKS
    if categories:
        tasks = [t for t in tasks if t.category in categories]
    if max_tasks > 0:
        tasks = tasks[:max_tasks]
    if smoke:
        tasks = tasks[:2]
        config_names = ["raw", "planner"]
    else:
        config_names = list(CONFIGS.keys())

    logger.info("Browser Automation Benchmark")
    logger.info("  Model: %s", MODEL)
    logger.info("  Tasks: %d (%s)", len(tasks), ", ".join(t.id for t in tasks))
    logger.info("  Configs: %s", ", ".join(config_names))

    # Warmup
    await _warmup_ollama()

    all_results: list[TaskResult] = []
    task_details: list[dict] = []

    for config_name in config_names:
        config = CONFIGS[config_name]
        enable_planner = config["planner"]

        logger.info("  Running config: %s (planner=%s)", config_name, enable_planner)

        for task in tasks:
            logger.info("    Task: %s [%s]", task.id, task.category)

            result = await run_task(task, config_name, enable_planner)
            all_results.append(result)

            tool_eval = evaluate_tool_selection(task, result)
            result.success = evaluate_task_success(task, result, tool_eval)

            detail = {
                "task_id": task.id,
                "category": task.category,
                "config": config_name,
                "success": result.success,
                "turns": result.turns,
                "tool_calls": result.tool_calls,
                "planner_injected": result.planner_injected,
                "unique_tools": list(result.unique_tools),
                "duration_seconds": result.duration_seconds,
                "tool_selection": tool_eval,
                "error": result.error,
            }
            task_details.append(detail)

            status = "PASS" if result.success else "FAIL"
            logger.info("      → %s | turns=%d tools=%d acc=%.0f%% inj=%d %.1fs",
                       status, result.turns, len(result.tool_calls),
                       tool_eval["accuracy"] * 100, len(result.planner_injected),
                       result.duration_seconds)

            await asyncio.sleep(0.3)

    report.tasks = [{
        "task_id": r.task_id,
        "category": r.category,
        "config": r.config_name,
        "success": r.success,
        "turns": r.turns,
        "tool_calls": r.tool_calls,
        "planner_injected": r.planner_injected,
        "unique_tools": list(r.unique_tools),
        "duration_seconds": r.duration_seconds,
        "error": r.error,
    } for r in all_results]

    report.per_task_details = task_details
    report.summary = _compute_summary(all_results)
    return report


async def _warmup_ollama():
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(f"{OLLAMA_URL}/api/chat", json={
                    "model": MODEL,
                    "messages": [{"role": "user", "content": "warmup"}],
                    "stream": False,
                })
                if resp.status_code == 200:
                    logger.info("Ollama warmup successful")
                    return
        except Exception as e:
            logger.warning("Warmup attempt %d/3: %s", attempt+1, e)
        await asyncio.sleep(2)
    logger.warning("Ollama warmup failed — continuing anyway")


def print_report(report: BrowserBenchmarkReport) -> None:
    print()
    print("=" * 72)
    print(f"  Browser Automation Benchmark")
    print(f"  Model: {report.model}")
    print(f"  Timestamp: {report.timestamp}")
    print("=" * 72)
    print()

    summary = report.summary
    by_config = summary.get("by_config", {})
    deltas = summary.get("deltas", {})

    # Config summary table
    header = f"{'Config':<12} {'Tasks':>5} {'Pass':>5} {'Rate':>7} {'Acc':>7} {'Turns':>6} {'Duration':>9} {'Inj':>5}  {'FSM Tr':>6} {'Loop':>5} {'Force':>6}"
    print(header)
    print("-" * 90)

    for cname in sorted(by_config.keys()):
        s = by_config[cname]
        fsm = s.get("fsm_metrics", {})
        fsm_tr = fsm.get("total_transitions", "-")
        fsm_lp = fsm.get("total_loops_prevented", "-")
        fsm_fo = fsm.get("total_forced_transitions", "-")
        print(f"{cname:<12} {s['total_tasks']:>5} {s['successes']:>5} "
              f"{s['success_rate']:>6.1%} {s['avg_tool_selection_accuracy']:>6.1%} "
              f"{s['avg_turns']:>6.1f} {s['avg_duration_seconds']:>7.1f}s "
              f"{s['total_planner_injections']:>5}  "
              f"{str(fsm_tr):>6} {str(fsm_lp):>5} {str(fsm_fo):>6}")

    # Deltas
    if deltas:
        print()
        print(f"{'Delta vs Raw':<20} {'dSuccess':>10} {'dAccuracy':>10} {'dTurns':>8}")
        print("-" * 48)
        for cname in sorted(deltas.keys()):
            d = deltas[cname]
            sr = d["delta_success_rate"]
            sr_s = f"+{sr:.1%}" if sr >= 0 else f"{sr:.1%}"
            ac = d["delta_tool_selection_accuracy"]
            ac_s = f"+{ac:.1%}" if ac >= 0 else f"{ac:.1%}"
            print(f"{cname:<20} {sr_s:>10} {ac_s:>10} {d['delta_avg_turns']:>+8.1f}")

    # Category breakdown
    print()
    print("  Category Breakdown (full config):")
    print(f"  {'Category':<22} {'Tasks':>5} {'Pass':>5} {'Rate':>7} {'Acc':>7}")
    print("  " + "-" * 50)

    if "full" in by_config:
        full_results = [t for t in report.tasks if t["config"] == "full"]
        from collections import defaultdict
        cat_stats = defaultdict(lambda: {"total": 0, "pass": 0, "acc": []})
        for t in full_results:
            cat = t["category"]
            cat_stats[cat]["total"] += 1
            if t["success"]:
                cat_stats[cat]["pass"] += 1
            for detail in report.per_task_details:
                if detail["task_id"] == t["task_id"] and detail["config"] == "full":
                    cat_stats[cat]["acc"].append(detail["tool_selection"]["accuracy"])
                    break

        for cat in sorted(cat_stats.keys()):
            s = cat_stats[cat]
            avg_acc = sum(s["acc"]) / max(len(s["acc"]), 1) if s["acc"] else 0
            print(f"  {cat:<22} {s['total']:>5} {s['pass']:>5} "
                  f"{s['pass']/max(s['total'],1):>6.1%} {avg_acc:>6.1%}")

    # Top tools per config
    print()
    print("  Tool Frequency (top 5 per config):")
    for cname in sorted(by_config.keys()):
        freq = by_config[cname].get("tool_frequency", {})
        top5 = list(freq.items())[:5]
        if top5:
            freq_str = ", ".join(f"{t}({c})" for t, c in top5)
            print(f"    {cname:<10} {freq_str}")
    print()


async def main():
    parser = argparse.ArgumentParser(description="Browser Automation Benchmark")
    parser.add_argument("--smoke", action="store_true", help="Quick test: 2 tasks, 2 configs")
    parser.add_argument("--model", default=None, help="Override model")
    parser.add_argument("--category", choices=["search_extract", "multi_page", "form_fill", "workflow", "data_collect"],
                        help="Filter by category")
    parser.add_argument("--max-tasks", type=int, default=0, help="Max tasks per config")
    parser.add_argument("--no-warmup", action="store_true", help="Skip model warmup")
    args = parser.parse_args()

    if args.model:
        global MODEL
        MODEL = args.model

    categories = [args.category] if args.category else None

    report = await run_benchmark(
        max_tasks=args.max_tasks,
        categories=categories,
        smoke=args.smoke,
    )

    print_report(report)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_name = MODEL.replace(":", "_")
    path = os.path.join(REPORT_DIR, f"browser_bench_{model_name}_{ts}.json")
    report.save(path)

    return report


if __name__ == "__main__":
    asyncio.run(main())
