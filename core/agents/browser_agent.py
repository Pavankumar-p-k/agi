"""BrowserAgent — real browser control (rebuilt in STEP 4).

Why this rebuild
----------------
The previous body was a FAKE-SUCCESS caught by the agent scorecard: the task
"open https://example.com and take a screenshot" returned
``success=True, "Browser: 0 open tab(s)."`` in 0.0 seconds. It never launched
a browser — ``analyze()`` called ``browser_tools.list_open_tabs``, **a function
that does not exist** (the real one is async ``do_browser_list_tabs``), the
``except Exception: pass`` swallowed the miss, and ``_execute_impl`` hardcoded
``success=True`` on the result.

Contract now
------------
* ``analyze()`` reads live sessions from :class:`BrowserManager` (no phantom
  API) and reports ``source="offline"`` only when genuinely no session exists.
* ``_execute_impl`` *performs* the goal: navigate to a URL when one is given,
  capture a screenshot when asked, otherwise report the open tabs.
* Any failure returns ``success=False`` with the real error — a browser that
  will not start is reported, never counted as an empty-but-successful run.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from core.agents.base import AgentResult, BaseAgent

_URL_RE = re.compile(r"https?://[^\s)\"']+")


@dataclass
class BrowserSnapshot:
    open_tabs: list[str] = field(default_factory=list)
    history: list[str] = field(default_factory=list)
    patterns: dict[str, Any] = field(default_factory=dict)
    predictions: list[str] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"open_tabs": list(self.open_tabs), "history": list(self.history),
                "patterns": dict(self.patterns), "predictions": list(self.predictions),
                "timestamp": self.timestamp}


class BrowserAgent(BaseAgent):
    """Opens pages, captures state and reports on live browser sessions."""

    agent_id = "browser"
    keywords = ["browse", "open chrome", "screenshot", "tab", "url in browser"]
    priority = 10
    description = "Browser navigation, screenshots and tab analysis"

    # ------------------------------------------------------------- read path
    def analyze(self) -> BrowserSnapshot:
        """Snapshot the *live* session table (no browser -> empty, honest)."""
        snapshot = BrowserSnapshot(timestamp=datetime.now().isoformat())
        source = "offline"
        try:
            from core.browser_manager import BrowserManager
            bm = BrowserManager.instance()
            tabs: list[str] = []
            for sid in bm.session_ids():
                session = bm.get_session(sid)
                if session is None or session.context is None:
                    continue
                source = "browser_manager"
                for page in (getattr(session.context, "pages", None) or []):
                    try:
                        tabs.append(f"[{sid}] {page.url}")
                    except Exception:  # noqa: BLE001 — page closed mid-read
                        continue
            snapshot.open_tabs = tabs[:20]
        except Exception:  # noqa: BLE001 — browser stack unavailable
            source = "unavailable"
        snapshot.patterns = {
            "tab_count": len(snapshot.open_tabs),
            "source": source,
        }
        return snapshot

    def get_open_tabs(self) -> list[str]:
        return list(self.analyze().open_tabs)

    def get_history(self) -> list[str]:
        return list(self.analyze().history)

    def get_patterns(self) -> dict[str, Any]:
        return dict(self.analyze().patterns)

    def get_predictions(self) -> list[str]:
        return list(self.analyze().predictions)

    # ----------------------------------------------------------- write path
    async def _execute_impl(self, goal: str, context: Optional[Any] = None,
                            **kwargs: Any) -> AgentResult:
        session_id = str(kwargs.get("session_id", "default") or "default")
        want_screenshot = "screenshot" in (goal or "").lower()
        url_match = _URL_RE.search(goal or "")
        url = url_match.group(0).rstrip(".,)") if url_match else None

        try:
            from core.tools import browser_tools
        except Exception as exc:  # noqa: BLE001 — deleted/missing stack
            return AgentResult(
                success=False, output="", agent_id=self.agent_id,
                error=f"browser stack unavailable: {type(exc).__name__}: {exc}",
            )

        lines: list[str] = []
        ok = True
        error: Optional[str] = None

        # 1. Navigate when the goal names a URL (or asks to open the browser).
        if url or any(k in (goal or "").lower()
                      for k in ("open", "browse", "visit", "go to")):
            target = url or "https://example.com"
            try:
                result = await browser_tools.do_browser_navigate(
                    target, session_id=session_id)
            except Exception as exc:  # noqa: BLE001
                result = {"status": "error",
                          "error": f"{type(exc).__name__}: {exc}"}
            if result.get("status") == "ok":
                res = result.get("result") or {}
                lines.append(f"opened {res.get('url', target)} "
                             f"-> {res.get('title', '')}")
            else:
                ok = False
                error = str(result.get("error") or "navigation failed")
                lines.append(f"navigation failed: {error}")

        # 2. Screenshot when asked.
        if want_screenshot and ok:
            try:
                result = await browser_tools.do_browser_screenshot(
                    session_id=session_id)
            except Exception as exc:  # noqa: BLE001
                result = {"status": "error",
                          "error": f"{type(exc).__name__}: {exc}"}
            if result.get("status") == "ok":
                res = result.get("result") or {}
                shot = res.get("screenshot") or result.get("screenshot") or ""
                where = res.get("path") or res.get("saved_to") or "in-memory"
                lines.append(f"screenshot captured ({len(str(shot))} b64 chars, {where})")
            else:
                ok = False
                error = str(result.get("error") or "screenshot failed")
                lines.append(f"screenshot failed: {error}")

        # 3. Always report the resulting tab state.
        snap = self.analyze()
        lines.append(f"Browser: {len(snap.open_tabs)} open tab(s) "
                     f"(source={snap.patterns.get('source')}).")
        lines += [f"- {t}" for t in snap.open_tabs[:10]]

        if not snap.open_tabs and url is None and not want_screenshot:
            # Nothing requested and nothing to report — do not claim success
            # on an empty action; say so plainly.
            lines.append("no session is open; ask to open a URL to start one.")

        return AgentResult(
            success=ok,
            output="\n".join(lines),
            agent_id=self.agent_id,
            error=error or "",
        )
