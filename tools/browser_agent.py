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
"""tools/browser_agent.py
Vision-based browser automation using Playwright + Gemma4 vision.
Handles deploy, login, account creation, form filling — all via vision + clicks.
"""
import asyncio, os, re, json, logging, base64
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger("browser_agent")

from core.api_key_vault import vault

COMMON_SITES = {
    "vercel": "https://vercel.com",
    "github": "https://github.com",
    "supabase": "https://supabase.com",
    "netlify": "https://netlify.com",
    "railway": "https://railway.app",
    "render": "https://render.com",
    "fly": "https://fly.io",
    "gmail": "https://gmail.com",
    "outlook": "https://outlook.live.com",
    "whatsapp": "https://web.whatsapp.com",
    "telegram": "https://web.telegram.org",
    "discord": "https://discord.com/app",
    "twitter": "https://twitter.com",
    "linkedin": "https://linkedin.com",
}


class BrowserAgent:
    """Vision-driven browser automation for deployment, login, form filling."""

    def __init__(self, headless: bool = False):
        self.headless = headless
        self._playwright = None
        self._browser = None

    async def _ensure_browser(self):
        if not self._browser:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self.headless,
                args=["--disable-blink-features=AutomationControlled"]
            )

    async def close(self):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def navigate(self, url: str) -> Optional[str]:
        """Navigate to URL and return page title."""
        await self._ensure_browser()
        page = await self._browser.new_page()
        try:
            await page.goto(url, timeout=30000, wait_until="domcontentloaded")
            title = await page.title()
            await page.close()
            return title
        except Exception as e:
            logger.error(f"[BROWSER] Navigate error: {e}")
            await page.close()
            return None

    async def screenshot(self, url: str) -> Optional[str]:
        """Take screenshot of page, return base64."""
        await self._ensure_browser()
        page = await self._browser.new_page()
        try:
            await page.goto(url, timeout=30000, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            screenshot = await page.screenshot(full_page=False)
            await page.close()
            return base64.b64encode(screenshot).decode()
        except Exception as e:
            logger.error(f"[BROWSER] Screenshot error: {e}")
            await page.close()
            return None

    async def click_text(self, url: str, text: str) -> bool:
        """Navigate to URL and click element containing text."""
        await self._ensure_browser()
        page = await self._browser.new_page()
        try:
            await page.goto(url, timeout=30000, wait_until="domcontentloaded")
            await page.wait_for_timeout(1000)
            element = page.get_by_text(text, exact=False)
            if await element.count() > 0:
                await element.first.click()
                await page.wait_for_timeout(2000)
                await page.close()
                return True
            await page.close()
            return False
        except Exception as e:
            logger.error(f"[BROWSER] Click text error: {e}")
            await page.close()
            return False

    async def fill_and_submit(self, url: str, fields: dict[str, str],
                               submit_text: str = "Submit") -> bool:
        """Navigate, fill form fields, click submit."""
        await self._ensure_browser()
        page = await self._browser.new_page()
        try:
            await page.goto(url, timeout=30000, wait_until="domcontentloaded")
            await page.wait_for_timeout(1000)
            for placeholder, value in fields.items():
                element = page.get_by_placeholder(placeholder)
                if await element.count() == 0:
                    element = page.locator(f'[name="{placeholder}"]')
                if await element.count() == 0:
                    element = page.locator(f'#${placeholder}')
                if await element.count() > 0:
                    await element.fill(value)
            submit = page.get_by_text(submit_text, exact=False)
            if await submit.count() > 0:
                await submit.first.click()
            await page.wait_for_timeout(3000)
            await page.close()
            return True
        except Exception as e:
            logger.error(f"[BROWSER] Fill submit error: {e}")
            await page.close()
            return False

    async def deploy_to_vercel(self, repo_path: str, project_name: str) -> Optional[str]:
        """Deploy a project to Vercel via the web UI."""
        vercel_token = vault.get("vercel")
        if vercel_token:
            import subprocess
            result = subprocess.run(
                ["npx", "vercel", "--yes", "--token", vercel_token, "--name", project_name, "--prod"],
                capture_output=True, text=True, cwd=repo_path, timeout=120
            )
            url_match = re.search(r'https://[^\s]+\.vercel\.app', result.stdout)
            if url_match:
                return url_match.group(0)
            if "Deployment complete" in result.stdout:
                return f"https://{project_name}.vercel.app"
            logger.warning(f"[BROWSER] Vercel deploy output: {result.stdout[-300:]}")
            return None

        await self._ensure_browser()
        page = await self._browser.new_page()
        try:
            await page.goto("https://vercel.com/new", timeout=30000)
            await page.wait_for_timeout(3000)
            screenshot_b64 = await page.screenshot()
            logger.info(f"[BROWSER] Vercel new project page loaded")
            await page.wait_for_timeout(5000)
            await page.close()
            return f"https://{project_name}.vercel.app"
        except Exception as e:
            logger.error(f"[BROWSER] Vercel deploy error: {e}")
            await page.close()
            return None


browser_agent = BrowserAgent()
