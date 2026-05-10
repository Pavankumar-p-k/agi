"""Links Manager - Phase 7 Mythos Omega."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class Link:
    def __init__(self, name: str, url: str):
        self.name = name
        self.url = url


class LinksManager:
    """Manages resource links."""

    def __init__(self, config_dir: str):
        self.config_dir = config_dir
        self.links: Dict[str, Link] = {}
        self._load_links()

    def _load_links(self):
        """Load links from config file."""
        links_file = os.path.join(self.config_dir, "links.json")
        if os.path.exists(links_file):
            try:
                with open(links_file, "r") as f:
                    data = json.load(f)
                    for name, url in data.get("links", {}).items():
                        self.links[name] = Link(name=name, url=url)
            except Exception as e:
                logger.error("Failed to load links: %s", e)

    def _save_links(self):
        """Save links to config file."""
        links_file = os.path.join(self.config_dir, "links.json")
        data = {"links": {name: link.url for name, link in self.links.items()}}
        try:
            with open(links_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error("Failed to save links: %s", e)

    def list_links(self) -> List[Dict[str, Any]]:
        """List all resource links."""
        return [
            {"name": link.name, "url": link.url}
            for link in self.links.values()
        ]

    def add_link(self, name: str, url: str) -> Dict[str, Any]:
        """Add a named resource link."""
        self.links[name] = Link(name=name, url=url)
        self._save_links()
        return {"ok": True, "name": name, "url": url}

    def remove_link(self, name: str) -> Dict[str, Any]:
        """Remove a resource link."""
        if name not in self.links:
            return {"ok": False, "error": f"Link '{name}' not found"}
        del self.links[name]
        self._save_links()
        return {"ok": True, "message": f"Link '{name}' removed"}

    def open_link(self, name: str) -> Dict[str, Any]:
        """Open a resource link."""
        if name not in self.links:
            return {"ok": False, "error": f"Link '{name}' not found"}
        link = self.links[name]
        return {"ok": True, "name": link.name, "url": link.url, "action": "open"}
