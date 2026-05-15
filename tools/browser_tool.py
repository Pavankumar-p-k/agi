"""tools/browser_tool.py
Playwright-based browser automation for JARVIS.
"""
import asyncio
from typing import Dict
from playwright.async_api import async_playwright


class JarvisBrowser:
    """Direct Playwright browser automation."""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._playwright = None
        self._browser = None
        self._page = None

    async def _ensure(self):
        if self._page is None:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=self.headless)
            self._page = await self._browser.new_page()

    async def navigate(self, url: str) -> Dict:
        await self._ensure()
        try:
            await self._page.goto(url, timeout=30000)
            title = await self._page.title()
            return {"status": "success", "action": f"navigated to {url}", "title": title}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def execute(self, instruction: str) -> Dict:
        await self._ensure()
        if instruction.startswith("http"):
            return await self.navigate(instruction)
        return {"status": "error", "error": f"Cannot execute unstructured instruction: {instruction}"}

    async def close(self):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
