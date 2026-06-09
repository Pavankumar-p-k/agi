# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""tools/browser_tool.py
Playwright-based browser automation for JARVIS.
"""
import asyncio
from typing import Dict
from playwright.async_api import async_playwright
from core.ssrf import assert_safe_url


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
        try:
            assert_safe_url(url)
        except ValueError as e:
            return {"status": "error", "error": str(e)}
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
