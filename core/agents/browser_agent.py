"""BrowserAgent — Chrome usage pattern analyzer (read-only)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from core.agents.base import AgentResult, BaseAgent


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
    """Analyzes browser usage patterns without controlling the browser."""

    agent_id = "browser"
    keywords = ["browse", "open chrome", "screenshot", "tab", "url in browser"]
    priority = 10
    description = "Browser usage analysis (read-only)"

    def analyze(self) -> BrowserSnapshot:
        """Read-only browser snapshot (empty when browser not running)."""
        snapshot = BrowserSnapshot(timestamp=datetime.now().isoformat())
        try:
            from core.tools import browser_tools
            get_tabs = getattr(browser_tools, "list_open_tabs", None)
            if callable(get_tabs):
                tabs = get_tabs() or []
                snapshot.open_tabs = [str(t) for t in tabs][:20]
        except Exception:  # noqa: BLE001 — browser not available is normal
            pass
        snapshot.patterns = {
            "tab_count": len(snapshot.open_tabs),
            "source": "browser_tools" if snapshot.open_tabs else "offline",
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

    async def _execute_impl(self, goal: str, context: Optional[Any] = None, **kwargs: Any) -> AgentResult:
        snap = self.analyze()
        lines = [f"Browser: {len(snap.open_tabs)} open tab(s)."]
        lines += [f"- {t}" for t in snap.open_tabs[:10]]
        return AgentResult(success=True, output="\n".join(lines), agent_id=self.agent_id)
