from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class BrowserTabInfo:
    url: str
    title: str
    index: int


@dataclass
class BrowserState:
    url: str
    title: str
    tabs: list[BrowserTabInfo]
    tab_count: int
    has_browser: bool
    error: str = ""


class BrowserContextAwareness:
    async def get_active_state(self, session_id: str = "") -> BrowserState:
        try:
            from core.tools import browser_tools as bt

            url_result = await bt.do_browser_get_url(session_id=session_id)
            title_result = await bt.do_browser_get_title(session_id=session_id)
            list_result = await bt.do_browser_list_tabs(session_id=session_id)

            url_ok = url_result.get("status") == "ok" if isinstance(url_result, dict) else False
            title_ok = title_result.get("status") == "ok" if isinstance(title_result, dict) else False
            list_ok = list_result.get("status") == "ok" if isinstance(list_result, dict) else False

            url = url_result.get("result", {}).get("url", "") if url_ok else ""
            title = title_result.get("result", {}).get("title", "") if title_ok else ""
            tabs_data = list_result.get("result", {}).get("tabs", []) if list_ok else []

            tabs = []
            for i, t in enumerate(tabs_data):
                if isinstance(t, dict):
                    tabs.append(BrowserTabInfo(
                        url=t.get("url", ""),
                        title=t.get("title", ""),
                        index=t.get("index", i),
                    ))
                elif isinstance(t, str):
                    tabs.append(BrowserTabInfo(url=t, title="", index=i))

            return BrowserState(
                url=url,
                title=title,
                tabs=tabs,
                tab_count=len(tabs),
                has_browser=bool(url),
                error="",
            )
        except Exception as e:
            logger.debug("BrowserContextAwareness.get_active_state failed: %s", e)
            return BrowserState(
                url="", title="", tabs=[], tab_count=0,
                has_browser=False, error=str(e),
            )

    async def is_browser_active(self, session_id: str = "") -> bool:
        state = await self.get_active_state(session_id)
        return state.has_browser
