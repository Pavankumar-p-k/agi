"""core/tools/browser_fsm.py
Browser Execution State Machine — deterministic browser workflow control.

Replaces the rule-based BrowserPlanner post_plan with a state machine.
The LLM decides WHAT to do; the FSM decides HOW.

States:
  START         — initial state, awaiting first navigation
  NAVIGATE      — navigating to URL
  SEARCH_PAGE   — on a page with a search form
  SEARCH_RESULTS — on a search results page
  ARTICLE       — on a content/article page
  FORM          — on a page with a non-search form
  LOGIN         — on a login/sign-in page
  EXTRACT       — extracting information from current page
  COMPLETE      — task completed
  FAIL          — unrecoverable error

Each state:
  - allowed_tools: which tools the LLM may call
  - exit_conditions: when to auto-transition
  - failure_conditions: when to fail or escalate
  - max_actions: max allowed tool calls in this state
  - wait_conditions: what to wait for before proceeding
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class BrowserState(Enum):
    START = "START"
    NAVIGATE = "NAVIGATE"
    SEARCH_PAGE = "SEARCH_PAGE"
    SEARCH_RESULTS = "SEARCH_RESULTS"
    ARTICLE = "ARTICLE"
    FORM = "FORM"
    LOGIN = "LOGIN"
    EXTRACT = "EXTRACT"
    COMPLETE = "COMPLETE"
    FAIL = "FAIL"


# ── State definitions ──────────────────────────────────────────

@staticmethod
def _always(_tool: str) -> bool:
    return True


STATE_DEFS: dict[BrowserState, dict[str, Any]] = {
    BrowserState.START: {
        "allowed_tools": {"browser_navigate", "browser_new_tab"},
        "exit_tools": {"browser_navigate"},
        "max_actions": 1,
        "on_exit": BrowserState.NAVIGATE,
        "on_timeout": BrowserState.FAIL,
        "prompt": "Starting browser session. Navigate to the initial URL.",
    },
    BrowserState.NAVIGATE: {
        "allowed_tools": {"browser_navigate", "browser_snapshot", "browser_get_url", "browser_get_title"},
        "exit_tools": {"browser_snapshot"},
        "max_actions": 2,
        "on_exit": None,  # determined by page recognition
        "on_timeout": BrowserState.FAIL,
        "wait_for": "network_idle",
        "prompt": "Navigating. Wait for page to load, then snapshot.",
    },
    BrowserState.SEARCH_PAGE: {
        "allowed_tools": {"browser_fill", "browser_press", "browser_snapshot", "browser_evaluate", "browser_get_url"},
        "exit_tools": {"browser_press"},
        "max_actions": 4,
        "on_exit": BrowserState.SEARCH_RESULTS,
        "on_timeout": BrowserState.FAIL,
        "prompt": "Search page. Fill the search box and press Enter.",
    },
    BrowserState.SEARCH_RESULTS: {
        "allowed_tools": {"browser_snapshot", "browser_click", "browser_evaluate", "browser_get_url", "browser_navigate"},
        "exit_tools": {"browser_click", "browser_navigate"},
        "max_actions": 3,
        "on_exit": None,  # determined by what we clicked
        "on_timeout": BrowserState.FAIL,
        "wait_for": "dom_stable",
        "prompt": "Search results loaded. Click a result link to view details.",
    },
    BrowserState.ARTICLE: {
        "allowed_tools": {"browser_snapshot", "browser_evaluate", "browser_get_url", "browser_get_title", "browser_navigate", "browser_click"},
        "exit_tools": {"browser_snapshot"},
        "max_actions": 5,
        "on_exit": BrowserState.EXTRACT,
        "on_timeout": BrowserState.COMPLETE,
        "wait_for": "dom_stable",
        "prompt": "Article page. Read the content. Snapshot when ready to extract.",
    },
    BrowserState.FORM: {
        "allowed_tools": {"browser_fill", "browser_press", "browser_click", "browser_snapshot", "browser_evaluate"},
        "exit_tools": {"browser_press", "browser_click"},
        "max_actions": 6,
        "on_exit": None,
        "on_timeout": BrowserState.FAIL,
        "prompt": "Form page. Fill in the form fields.",
    },
    BrowserState.LOGIN: {
        "allowed_tools": {"browser_snapshot", "browser_get_url"},
        "exit_tools": set(),
        "max_actions": 1,
        "on_exit": BrowserState.FAIL,
        "on_timeout": BrowserState.FAIL,
        "prompt": "Login page detected. Cannot auto-fill credentials. Task may need manual intervention.",
    },
    BrowserState.EXTRACT: {
        "allowed_tools": {"browser_snapshot", "browser_evaluate", "browser_get_url", "browser_get_title", "browser_navigate", "browser_click"},
        "exit_tools": {"browser_snapshot"},
        "max_actions": 4,
        "on_exit": BrowserState.COMPLETE,
        "on_timeout": BrowserState.COMPLETE,
        "prompt": "Extracting information. Snapshot the page to capture data.",
    },
    BrowserState.COMPLETE: {
        "allowed_tools": set(),
        "exit_tools": set(),
        "max_actions": 0,
        "on_exit": None,
        "on_timeout": None,
        "prompt": "Task complete.",
    },
    BrowserState.FAIL: {
        "allowed_tools": {"browser_snapshot"},
        "exit_tools": set(),
        "max_actions": 1,
        "on_exit": None,
        "on_timeout": None,
        "prompt": "Task failed. Taking final snapshot.",
    },
}


# ── Page Recognition (deterministic, no LLM) ────────────────────

# Indicators for page type classification
_SEARCH_PAGE_INDICATORS = [
    "search", "find", "look up", "what are you looking for",
    "ask anything", "type here", "search query",
]
_RESULTS_PAGE_INDICATORS = [
    "result", "found", "matches", "showing", "page",
    "next", "previous", "sorted by",
]
_ARTICLE_INDICATORS = [
    "article", "blog post", "read more", "published", "author",
    "comments", "share on", "related stories",
]
_LOGIN_INDICATORS = [
    "sign in", "log in", "login", "username", "password",
    "email address", "create account", "register",
]
_FORM_INDICATORS = [
    "submit", "form", "first name", "last name", "phone",
    "address line", "city", "state", "zip", "country",
]


def recognize_page(snapshot: dict | str | None, url: str = "") -> BrowserState:
    """Deterministic page classification from snapshot DOM data.
    Returns the most likely BrowserState for the current page.
    """
    if not snapshot:
        return BrowserState.NAVIGATE

    if isinstance(snapshot, str):
        text = snapshot.lower()
    elif isinstance(snapshot, dict):
        parts = []
        for key in ("title", "headings", "paragraphs", "buttons", "forms"):
            val = snapshot.get(key)
            if isinstance(val, str):
                parts.append(val)
            elif isinstance(val, list):
                for item in val:
                    if isinstance(item, dict):
                        parts.append(str(item.get("text", "")))
                    elif isinstance(item, str):
                        parts.append(item)
        text = " ".join(parts).lower()
    else:
        return BrowserState.NAVIGATE

    # Check for login forms first (security-sensitive)
    if any(ind in text for ind in _LOGIN_INDICATORS):
        # Must have password field to confirm
        if "password" in text or "pass" in text:
            return BrowserState.LOGIN

    # Check for non-search forms
    if any(ind in text for ind in _FORM_INDICATORS):
        if "search" not in text and "query" not in text:
            return BrowserState.FORM

    # Check for search page (has search input, no results)
    has_search = any(ind in text for ind in _SEARCH_PAGE_INDICATORS)
    has_results = any(ind in text for ind in _RESULTS_PAGE_INDICATORS)
    has_article = any(ind in text for ind in _ARTICLE_INDICATORS)

    if has_results:
        return BrowserState.SEARCH_RESULTS
    if has_article:
        return BrowserState.ARTICLE
    if has_search:
        return BrowserState.SEARCH_PAGE

    # Check URL patterns
    if url:
        url_lower = url.lower()
        if "/search" in url_lower or "?q=" in url_lower or "query=" in url_lower:
            return BrowserState.SEARCH_RESULTS
        if any(p in url_lower for p in ("/article/", "/post/", "/blog/", "/doc/", "/wiki/")):
            return BrowserState.ARTICLE

    return BrowserState.ARTICLE  # default to article


# ── Snapshot helpers ────────────────────────────────────────────

def _extract_snapshot_text(executed_results: list[dict]) -> str | None:
    """Extract readable text from browser_snapshot results."""
    for r in executed_results:
        inner = r.get("result", r)
        if isinstance(inner, dict):
            parts = []
            t = inner.get("title", "") or ""
            if t:
                parts.append(t)
            for h in inner.get("headings", []):
                if isinstance(h, dict):
                    txt = h.get("text", "") or ""
                    if txt:
                        parts.append(txt)
            for p in inner.get("paragraphs", []):
                if isinstance(p, dict):
                    txt = p.get("text", "") or ""
                    if txt:
                        parts.append(txt)
            for b in inner.get("buttons", []):
                if isinstance(b, dict):
                    txt = b.get("text", "") or ""
                    if txt:
                        parts.append(txt)
            for f in inner.get("forms", []):
                if isinstance(f, dict):
                    parts.append(f.get("action", "") or "")
            combined = " | ".join(parts)
            if len(combined) > 50:
                return combined
    return None


def _extract_snapshot_dict(executed_results: list[dict]) -> dict | None:
    """Extract the structured snapshot dict from results."""
    for r in executed_results:
        inner = r.get("result", r)
        if isinstance(inner, dict) and ("headings" in inner or "title" in inner or "forms" in inner or "inputs" in inner):
            return inner
    return None


# ── Browser Execution State Machine ─────────────────────────────

class BrowserFSM:
    """Deterministic state machine for browser workflow execution.

    Tracks current state, action count, history, and auto-transitions.
    Metrics are collected for benchmarking.
    """

    def __init__(self):
        self.state: BrowserState = BrowserState.START
        self.previous_state: BrowserState | None = None
        self.actions_in_state: int = 0
        self.total_actions: int = 0
        self.transitions: list[dict[str, Any]] = []
        self.forced_transitions: int = 0
        self.loops_prevented: int = 0
        self.page_recognitions: int = 0
        self.timeouts: int = 0
        self.recoveries: int = 0
        self.history: list[dict[str, Any]] = []
        self.visited_urls: list[str] = []
        self.state_entry_time: float = time.time()
        self.consecutive_same_tool: int = 0
        self.last_tool: str = ""

    def get_def(self) -> dict[str, Any]:
        """Get the definition for the current state."""
        return STATE_DEFS.get(self.state, STATE_DEFS[BrowserState.FAIL])

    def is_terminal(self) -> bool:
        """Check if FSM is in a terminal state."""
        return self.state in (BrowserState.COMPLETE, BrowserState.FAIL)

    def is_tool_allowed(self, tool_name: str) -> bool:
        """Check if a tool is allowed in the current state."""
        if self.is_terminal():
            return False
        allowed = self.get_def().get("allowed_tools", set())
        # Always allow snapshot and navigation for flexibility
        if tool_name in ("browser_snapshot", "browser_get_url", "browser_get_title"):
            return True
        return tool_name in allowed

    def is_exit_tool(self, tool_name: str) -> bool:
        """Check if a tool triggers an exit transition."""
        return tool_name in self.get_def().get("exit_tools", set())

    def record_action(self, tool_name: str, result: dict | None = None) -> None:
        """Record a tool action and update state tracking."""
        # Auto-transition: START → NAVIGATE on first browser_navigate
        if self.state == BrowserState.START and tool_name == "browser_navigate":
            self.transition_to(BrowserState.NAVIGATE)

        self.actions_in_state += 1
        self.total_actions += 1
        self.history.append({
            "tool": tool_name,
            "state": self.state.value,
            "time": time.time(),
            "result": "success" if result and not result.get("error") else "error" if result else "unknown",
        })

        # Track consecutive same tool
        if tool_name == self.last_tool:
            self.consecutive_same_tool += 1
        else:
            self.consecutive_same_tool = 1
            self.last_tool = tool_name

        # Track visited URLs
        if tool_name == "browser_navigate" and result:
            url = result.get("url", "") if isinstance(result, dict) else str(result)
            if url and url not in self.visited_urls:
                self.visited_urls.append(url)

    def check_loop(self) -> bool:
        """Detect tool looping: same tool 3+ consecutive times."""
        if self.consecutive_same_tool >= 3:
            self.loops_prevented += 1
            return True
        return False

    def check_timeout(self) -> bool:
        """Check if max actions exceeded for current state.
        Terminal states (COMPLETE, FAIL) never timeout.
        """
        if self.is_terminal():
            return False
        max_actions = self.get_def().get("max_actions", 10)
        if self.actions_in_state >= max_actions:
            self.timeouts += 1
            return True
        return False

    def transition_to(self, new_state: BrowserState, forced: bool = False) -> None:
        """Transition to a new state and reset action counter."""
        if new_state == self.state:
            return
        self.transitions.append({
            "from": self.state.value,
            "to": new_state.value,
            "forced": forced,
            "time": time.time(),
            "actions_in_state": self.actions_in_state,
        })
        self.previous_state = self.state
        self.state = new_state
        self.actions_in_state = 0
        self.consecutive_same_tool = 0
        self.last_tool = ""
        self.state_entry_time = time.time()
        if forced:
            self.forced_transitions += 1
        logger.debug("FSM: %s -> %s%s", self.previous_state.value, new_state.value,
                     " (forced)" if forced else "")

    def process_snapshot(self, executed_results: list[dict], url: str = "") -> BrowserState | None:
        """Process snapshot results and auto-transition based on page recognition.
        Returns the new state if auto-transitioned, None otherwise.
        """
        snapshot = _extract_snapshot_dict(executed_results)
        if snapshot:
            self.page_recognitions += 1
            recognized = recognize_page(snapshot, url)
            if recognized != self.state and recognized != BrowserState.NAVIGATE:
                self.transition_to(recognized)
                return recognized
        return None

    def handle_exit_tool(self, tool_name: str) -> BrowserState | None:
        """Handle exit tool execution — returns target state if auto-transition applies."""
        if not self.is_exit_tool(tool_name):
            return None
        on_exit = self.get_def().get("on_exit")
        if on_exit:
            self.transition_to(on_exit)
            return on_exit
        return None

    def handle_timeout(self) -> BrowserState | None:
        """Handle state timeout — returns fallback state, or None if terminal."""
        if self.is_terminal():
            return None
        on_timeout = self.get_def().get("on_timeout", BrowserState.FAIL)
        if on_timeout is None:
            return None
        self.transition_to(on_timeout, forced=True)
        return on_timeout

    def get_prompt(self) -> str:
        """Get the guidance prompt for the current state."""
        return self.get_def().get("prompt", "")

    def get_metrics(self) -> dict[str, Any]:
        """Get FSM metrics for benchmarking."""
        return {
            "fsm_final_state": self.state.value,
            "fsm_transitions": len(self.transitions),
            "fsm_forced_transitions": self.forced_transitions,
            "fsm_loops_prevented": self.loops_prevented,
            "fsm_page_recognitions": self.page_recognitions,
            "fsm_timeouts": self.timeouts,
            "fsm_recoveries": self.recoveries,
            "fsm_total_actions": self.total_actions,
            "fsm_visited_urls": len(self.visited_urls),
            "fsm_transition_log": self.transitions,
        }
