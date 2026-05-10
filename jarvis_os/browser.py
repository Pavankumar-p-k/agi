from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

class LocalBrowserController:
    def __init__(self, config: dict):
        self.config = config
        logger.info("LocalBrowserController initialized (Stub)")

    def open(self, target: str):
        return {"success": True, "target": target}

    def search(self, query: str, site: str = "google"):
        return {"success": True, "query": query, "site": site}

    def scrape_page(self, url: str, max_chars: int = 4000):
        return {"success": True, "url": url, "text": "Stubbed page content."}

    def status(self):
        return {"status": "running", "controller": "stub"}

    def click_text(self, text: str):
        return {"success": True, "clicked": text}

    def type_text(self, selector: str, text: str, submit: bool = False):
        return {"success": True, "typed": text, "selector": selector}
