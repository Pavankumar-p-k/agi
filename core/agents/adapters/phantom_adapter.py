from __future__ import annotations

from core.agents._sub_agent_base import AgentResult, SubAgent
from core.agents.adapters.base_adapter import SubAgentAdapter
from core.agents.capabilities import CAPABILITIES

PHANTOM_PROMPTS = {
    "scrape": (
        "You are PHANTOM, a web intelligence sub-agent inside Jarvis — Pavan's personal AI OS. "
        "You have just received raw scraped content from a webpage. "
        "Your role: extract the most valuable structured information. "
        "Output: Title, URL, Key Facts (numbered), Important Data/Numbers, "
        "Quotes worth keeping, Action items if any. Remove all noise. "
        "Think like an intelligence analyst processing raw SIGINT."
    ),
    "extract": (
        "You are PHANTOM in Data Extraction Mode inside Jarvis — Pavan's personal AI OS. "
        "You receive webpage content and an extraction goal. "
        "Output ONLY the extracted data in clean JSON format. "
        "No explanation, no prose — just the JSON object with the requested fields. "
        "If a field cannot be found, set it to null."
    ),
    "summarize": (
        "You are PHANTOM in Web Summarize Mode inside Jarvis — Pavan's personal AI OS. "
        "You receive raw webpage content. Produce a 5-bullet summary. "
        "Each bullet: max 25 words, high information density. "
        "Add one line: 'Source credibility: High/Medium/Low' with one-word reason."
    ),
    "monitor": (
        "You are PHANTOM in Monitor Mode inside Jarvis — Pavan's personal AI OS. "
        "You receive new and previous versions of a webpage. "
        "Output: What changed (list), What was removed, What was added, "
        "Significance of changes (Critical/Major/Minor), Recommended action. "
        "Think like a competitive intelligence analyst."
    ),
}

class PhantomAgent(SubAgent):
    NAME = "PHANTOM"
    DESCRIPTION = "Web scraping, content extraction, summarization, and page monitoring"
    DEFAULT_MODE = "scrape"
    AVAILABLE_MODES = ["scrape", "extract", "summarize", "monitor"]
    MAX_TOKENS = 2000

    def get_system_prompt(self, mode: str) -> str:
        return PHANTOM_PROMPTS.get(mode, PHANTOM_PROMPTS["scrape"])

    async def run(self, task: str, mode: str | None = None, **kwargs) -> AgentResult:
        mode = mode or self.DEFAULT_MODE
        url = kwargs.get("url")
        content = kwargs.get("content")

        if not content and (task.startswith("http") or url):
            target = url or task
            content = await self._scrape(target)
            if content:
                task = f"URL: {target}\n\nCONTENT:\n{content[:4000]}"

        return await super().run(task, mode=mode, **kwargs)

    async def _scrape(self, url: str) -> str:
        try:
            import importlib.util
            spec = importlib.util.find_spec("tools.crawl4ai_tool")
            if spec:
                from tools.crawl4ai_tool import get_crawler
                crawler = get_crawler()
                result = await crawler.scrape(url)
                return result.get("markdown") or result.get("content") or ""
            else:
                return f"[Scrape tool tools.crawl4ai_tool not found for {url}]"
        except Exception as e:
            return f"[Scrape failed: {e}]"


class PhantomAdapter(SubAgentAdapter):
    agent_id = "phantom"
    capabilities = CAPABILITIES["phantom"]
    sub_agent_class = PhantomAgent
    default_mode = "scrape"
