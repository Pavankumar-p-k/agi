"""PhantomAdapter — web content extraction specialist."""
from __future__ import annotations

import re
from typing import Any, Optional

from core.agents._sub_agent_base import AgentResult, SubAgent
from core.agents.base import AgentResult as _ToolResult

_URL_RE = re.compile(r"https?://[^\s\"']+")


class PhantomAgent(SubAgent):
    """Extracts and summarizes web page content."""

    NAME = "PHANTOM"
    DEFAULT_MODE = "extract"
    MODES = {
        "extract": "You are PHANTOM. Extract the key content from the provided page text verbatim where possible.",
        "summarize": "You are PHANTOM summarizing a page. Give the 5 most important points.",
        "monitor": "You are PHANTOM monitoring a page. Report what changed vs the prior snapshot.",
    }

    @staticmethod
    def _fetch_text(url: str, max_chars: int = 4000) -> str:
        """Fetch page text via core SSRF-guarded fetcher, fallback to raw text."""
        from core.ssrf import assert_safe_url
        assert_safe_url(url)
        try:
            from tools.search_fallback import _extract_page_content
            text = _extract_page_content(url, max_chars=max_chars)
            if text:
                return text
        except Exception:  # noqa: BLE001
            pass
        import asyncio

        import httpx
        try:
            resp = httpx.get(url, timeout=15, follow_redirects=True)
            text = re.sub(r"<[^>]+>", " ", resp.text)
            return re.sub(r"\s+", " ", text)[:max_chars]
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"phantom fetch failed: {exc}") from exc

    async def run(self, task: str, mode: str = "", **kwargs: Any) -> AgentResult:
        urls = _URL_RE.findall(task or "")
        if urls:
            page_text = self._fetch_text(urls[0])
            task = f"{task}\n\n--- PAGE CONTENT ---\n{page_text}"
        return await super().run(task, mode=mode, **kwargs)


class PhantomAdapter:
    agent_id = "phantom"
    priority = 50
    keywords = ["scrape", "extract page", "extract text from url", "crawl",
                "pull content", "website content"]

    def __init__(self, **kwargs: Any):
        self._agent = PhantomAgent(**kwargs)

    @property
    def agent(self) -> PhantomAgent:
        return self._agent

    def can_handle(self, goal: str) -> bool:
        text = (goal or "").lower()
        return any(kw.lower() in text for kw in self.keywords)

    def info(self) -> dict[str, Any]:
        return {**self._agent.info(), "agent_id": self.agent_id, "priority": self.priority}

    async def run(self, task: str, mode: str = "", **kwargs: Any) -> Any:
        return await self._agent.run(task, mode=mode, **kwargs)

    async def execute(self, goal: str, context: Optional[Any] = None, **kwargs: Any) -> _ToolResult:
        result = await self._agent.run(goal, **kwargs)
        return _ToolResult(success=result.success, output=result.output,
                           agent_id=self.agent_id, error=result.error,
                           duration=result.duration_s, metadata={"mode": result.mode})
