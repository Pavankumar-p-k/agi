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
"""tools/template_library.py
Template registry & library — downloads thousands of free web templates from GitHub
and other open-source sources. Caches locally at ~/.jarvis/templates/.

Usage:
  from tools.template_library import TemplateLibrary
  tl = TemplateLibrary()
  tl.sync()              # Build registry + download ALL templates
  tl.find_template("modern analytics dashboard with dark mode")  # Returns best match
  tl.generate_ui("login page with animations")  # Full pipeline: find → customize → write
"""

import os
import re
import json
import httpx
import shutil
import zipfile
import tarfile
import logging
import tempfile
import functools
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger("template_library")

TEMPLATE_DIR = Path.home() / ".jarvis" / "templates"
REGISTRY_PATH = TEMPLATE_DIR / "registry.json"
LIBRARY_DIR = TEMPLATE_DIR / "library"
CACHE_DIR = TEMPLATE_DIR / ".cache"

# GitHub: anonymous search has rate limits (~60/hr). We use a conservative approach.
GITHUB_SEARCH = "https://api.github.com/search/repositories"
GITHUB_TOPIC_SEARCH = "https://api.github.com/search/repositories?q=topic:{topic}+language:html&sort=stars&order=desc&per_page=100"

# Known curated sources
KNOWN_SOURCES = [
    {
        "name": "html5up",
        "url": "https://html5up.net",
        "type": "scrape",
    },
    {
        "name": "startbootstrap",
        "url": "https://startbootstrap.com",
        "type": "scrape",
    },
]

# GitHub topics that yield thousands of free templates
GITHUB_TOPICS = [
    "html-template", "bootstrap-template", "tailwind-ui",
    "free-template", "landing-page", "dashboard-template",
    "admin-template", "website-template", "responsive-template",
]


class TemplateLibrary:
    def __init__(self):
        self.registry: List[Dict] = []
        self._loaded = False

    # ─── Public API ──────────────────────────────────────────────

    def sync(self, force: bool = False):
        """Download ALL templates. Run once. Takes 5-15 minutes."""
        TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
        LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        if REGISTRY_PATH.exists() and not force:
            logger.info("Registry already exists. Use force=True to re-download.")
            self._load_registry()
            return

        logger.info("Building template registry from GitHub + curated sources...")
        self.registry = []

        # Step 1: Scrape GitHub by topic
        for topic in GITHUB_TOPICS:
            repos = self._search_github_by_topic(topic)
            self.registry.extend(repos)
            logger.info(f"  GitHub topic '{topic}': {len(repos)} repos found")

        # Step 2: Add curated sources
        for source in KNOWN_SOURCES:
            templates = self._scrape_source(source)
            self.registry.extend(templates)
            logger.info(f"  Curated '{source['name']}': {len(templates)} templates")

        # Step 3: Deduplicate by URL
        self._deduplicate_registry()

        # Step 4: Save registry
        REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
        REGISTRY_PATH.write_text(
            json.dumps(self.registry, indent=2, default=str),
            encoding="utf-8",
        )
        logger.info(f"Registry saved: {len(self.registry)} entries → {REGISTRY_PATH}")

        # Step 5: Download everything
        self._download_all()

        # Step 6: Build search index
        self._build_search_index()
        logger.info("Sync complete!")

    def find_template(self, query: str, top_n: int = 5) -> List[Dict]:
        """Find the best matching templates by keyword + category matching."""
        if not self._loaded:
            self._load_registry()

        query_lower = query.lower()
        query_words = set(query_lower.split())
        scored = []

        for tpl in self.registry:
            score = 0
            name = (tpl.get("name") or "").lower()
            desc = (tpl.get("description") or "").lower()
            tags = " ".join(tpl.get("tags", []) or []).lower()
            cats = " ".join(tpl.get("category", []) or []).lower()
            haystack = f"{name} {desc} {tags} {cats}"

            for word in query_words:
                if word in haystack:
                    score += 1

            # Bonus for exact phrase matches
            if query_lower in name:
                score += 3
            if query_lower in desc:
                score += 2
            if query_lower in tags:
                score += 2

            if score > 0:
                scored.append((score, tpl))

        scored.sort(key=lambda x: -x[0])
        return [t for _, t in scored[:top_n]]

    async def generate_ui(self, description: str, output_path: Optional[str] = None) -> Dict:
        """Full pipeline: find template → LLM fills content → write file."""
        matches = self.find_template(description, top_n=3)
        if not matches:
            return {"error": "No matching template found", "file_path": None}

        best = matches[0]
        template_html = self._read_template(best)

        if not template_html:
            return {"error": f"Template file not found for {best.get('name')}", "file_path": None}

        # LLM content fill
        from core.llm_router import complete as llm_complete
        prompt = (
            f"You are customizing a professional HTML template.\n"
            f"Template: {best.get('name')} ({best.get('description', '')})\n"
            f"User request: {description}\n\n"
            f"--- TEMPLATE HTML ---\n{template_html[:3000]}\n---\n\n"
            f"Fill in the {{variables}} in the template with appropriate content matching the user request. "
            f"DO NOT change HTML structure, class names, or CSS. "
            f"Only replace {{variable}} placeholders with real content. "
            f"Return the COMPLETE modified HTML."
        )
        try:
            filled_result = await llm_complete("code", [{"role": "user", "content": prompt}])
            filled_html = filled_result.unwrap_or(template_html)
        except Exception as e:
            filled_html = template_html  # fallback to raw template

        # Clean LLM output
        if "```html" in filled_html:
            filled_html = filled_html.split("```html")[1].split("```")[0].strip()
        elif "```" in filled_html:
            filled_html = filled_html.split("```")[1].split("```")[0].strip()

        file_path = output_path or str(TEMPLATE_DIR / "generated" / f"ui_{len(os.listdir(str(TEMPLATE_DIR / 'generated'))):04d}.html")
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        Path(file_path).write_text(filled_html, encoding="utf-8")

        return {
            "file_path": file_path,
            "template_name": best.get("name"),
            "template_category": best.get("category", []),
            "size": len(filled_html),
        }

    # ─── Internal: Registry building ─────────────────────────────

    def _search_github_by_topic(self, topic: str) -> List[Dict]:
        """Search GitHub for repos with a given topic. Returns list of template dicts."""
        results = []
        url = GITHUB_TOPIC_SEARCH.format(topic=topic)
        try:
            resp = httpx.get(url, headers={"Accept": "application/vnd.github.v3+json"}, timeout=30)
            if resp.status_code != 200:
                logger.warning(f"GitHub API error (topic={topic}): {resp.status_code}")
                return results
            data = resp.json()
            for item in data.get("items", []):
                # Only include repos with a license and recent update
                if not item.get("license"):
                    continue
                results.append({
                    "source": "github",
                    "name": item.get("name", ""),
                    "description": (item.get("description") or "")[:200],
                    "category": self._classify_template(item.get("name", ""), item.get("description", ""), item.get("topics", [])),
                    "tags": item.get("topics", [])[:10],
                    "stars": item.get("stargazers_count", 0),
                    "download_url": item.get("html_url", ""),
                    "license": (item.get("license") or {}).get("spdx_id", "MIT"),
                    "local_path": "",
                })
        except httpx.TimeoutException:
            logger.warning(f"GitHub API timeout (topic={topic})")
        except Exception as e:
            logger.warning(f"GitHub API error (topic={topic}): {e}")
        return results

    def _scrape_source(self, source: Dict) -> List[Dict]:
        """Scrape a known template source. Stub for now — extend per source."""
        if source["name"] == "html5up":
            return self._scrape_html5up()
        return []

    def _scrape_html5up(self) -> List[Dict]:
        """Scrape html5up.net for template list."""
        results = []
        try:
            resp = httpx.get("https://html5up.net", timeout=30)
            if resp.status_code != 200:
                return results
            # Parse template cards from HTML5UP
            html = resp.text
            # Find template blocks (h2 with template names)
            blocks = re.findall(r'<h2>(.*?)</h2>.*?<a href="(.*?)".*?class="button"', html, re.DOTALL)
            for name, url in blocks[:50]:
                clean_name = re.sub(r'<[^>]+>', '', name).strip()
                results.append({
                    "source": "html5up",
                    "name": clean_name,
                    "description": f"HTML5 UP template: {clean_name}",
                    "category": ["landing-page", "portfolio"],
                    "tags": ["html5up", "creative-commons", "responsive"],
                    "stars": 100,
                    "download_url": url if url.startswith("http") else f"https://html5up.net{url}",
                    "license": "Creative Commons",
                    "local_path": "",
                })
        except Exception as e:
            logger.warning(f"html5up scrape error: {e}")
        return results

    def _classify_template(self, name: str, desc: str, topics: List[str]) -> List[str]:
        """Classify a template into categories based on name/description/keywords."""
        text = f"{name} {desc} {' '.join(topics)}".lower()
        categories = []
        if any(w in text for w in ("dashboard", "admin", "analytics", "stats")):
            categories.append("dashboard")
        if any(w in text for w in ("landing", "startup", "saas", "product")):
            categories.append("landing-page")
        if any(w in text for w in ("portfolio", "resume", "cv")):
            categories.append("portfolio")
        if any(w in text for w in ("blog", "article", "post", "magazine")):
            categories.append("blog")
        if any(w in text for w in ("ecommerce", "shop", "store", "product", "cart")):
            categories.append("ecommerce")
        if any(w in text for w in ("login", "signup", "auth", "register")):
            categories.append("auth")
        if any(w in text for w in ("form", "contact")):
            categories.append("form")
        if any(w in text for w in ("app", "application", "webapp", "tool")):
            categories.append("app-ui")
        if any(w in text for w in ("component", "ui-kit", "element")):
            categories.append("components")
        if not categories:
            categories.append("general")
        return categories

    def _deduplicate_registry(self):
        seen_urls = set()
        unique = []
        for tpl in self.registry:
            url = tpl.get("download_url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique.append(tpl)
        self.registry = unique

    # ─── Internal: Download ──────────────────────────────────────

    def _download_all(self):
        """Download and extract all templates in the registry."""
        REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
        total = len(self.registry)
        logger.info(f"Downloading {total} templates to {LIBRARY_DIR}...")

        for i, tpl in enumerate(self.registry):
            name = tpl.get("name", f"tpl_{i:04d}")
            dest = LIBRARY_DIR / self._safe_dirname(name)
            if dest.exists() and any(dest.iterdir()):
                tpl["local_path"] = str(dest)
                continue  # already downloaded

            try:
                self._download_and_extract(tpl, dest, i, total)
                tpl["local_path"] = str(dest)
            except Exception as e:
                logger.warning(f"  [{i+1}/{total}] Failed {name}: {e}")

        # Update registry with local paths
        REGISTRY_PATH.write_text(
            json.dumps(self.registry, indent=2, default=str),
            encoding="utf-8",
        )

    def _download_and_extract(self, tpl: Dict, dest: Path, i: int, total: int):
        """Download a single template (zip or git clone) and extract."""
        download_url = tpl.get("download_url", "")
        name = tpl.get("name", f"tpl_{i:04d}")

        if not download_url:
            return

        logger.info(f"  [{i+1}/{total}] Downloading {name}...")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            if "github.com" in download_url:
                # Download GitHub repo as archive
                archive_url = f"{download_url.rstrip('/')}/archive/refs/heads/main.zip"
                resp = httpx.get(archive_url, timeout=60, follow_redirects=True)
                if resp.status_code != 200:
                    archive_url = f"{download_url.rstrip('/')}/archive/refs/heads/master.zip"
                    resp = httpx.get(archive_url, timeout=60, follow_redirects=True)
                if resp.status_code != 200:
                    logger.warning(f"    Could not download {name} (HTTP {resp.status_code})")
                    return

                zip_path = tmp_path / "repo.zip"
                zip_path.write_bytes(resp.content)
                try:
                    with zipfile.ZipFile(zip_path, "r") as zf:
                        # GitHub wraps in a top-level dir; extract contents directly
                        members = zf.namelist()
                        top_dir = os.path.commonprefix(members) if members else ""
                        for member in members:
                            relpath = os.path.relpath(member, top_dir)
                            if relpath and relpath != ".":
                                target = dest / relpath
                                if member.endswith("/"):
                                    target.mkdir(parents=True, exist_ok=True)
                                else:
                                    target.parent.mkdir(parents=True, exist_ok=True)
                                    target.write_bytes(zf.read(member))
                except zipfile.BadZipFile:
                    logger.warning(f"    Bad zip for {name}")
                    return
            else:
                # Direct file download
                resp = httpx.get(download_url, timeout=60, follow_redirects=True)
                if resp.status_code != 200:
                    return
                dest.mkdir(parents=True, exist_ok=True)
                (dest / "index.html").write_bytes(resp.content)

    def _read_template(self, tpl: Dict) -> Optional[str]:
        """Read the main HTML file from a downloaded template."""
        local_path = tpl.get("local_path", "")
        if not local_path or not os.path.isdir(local_path):
            return None
        # Find main HTML file
        for f in sorted(os.listdir(local_path)):
            if f.endswith(".html"):
                try:
                    return Path(local_path, f).read_text(encoding="utf-8", errors="replace")
                except Exception as e:
                    logger.exception("[template_library] read template (shallow): %s", e)
        # Try recursive search
        for root, _dirs, files in os.walk(local_path):
            for f in files:
                if f.endswith(".html"):
                    try:
                        return Path(root, f).read_text(encoding="utf-8", errors="replace")
                    except Exception as e:
                        logger.exception("[template_library] read template (deep): %s", e)
        return None

    # ─── Internal: Search index ──────────────────────────────────

    def _build_search_index(self):
        """Build a keyword→template lookup for fast matching."""
        index = {}
        for tpl in self.registry:
            name = (tpl.get("name") or "").lower()
            desc = (tpl.get("description") or "").lower()
            cats = " ".join(tpl.get("category", []) or []).lower()
            tags = " ".join(tpl.get("tags", []) or []).lower()
            text = f"{name} {desc} {cats} {tags}"
            for word in set(re.findall(r'\w+', text)):
                if word not in index:
                    index[word] = []
                index[word].append(tpl.get("name", ""))

        idx_path = TEMPLATE_DIR / "search_index.json"
        idx_path.write_text(json.dumps(index, default=str), encoding="utf-8")
        logger.info(f"Search index built: {len(index)} keywords")

    def _load_registry(self):
        if REGISTRY_PATH.exists():
            self.registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
            self._loaded = True

    @staticmethod
    def _safe_dirname(name: str) -> str:
        return re.sub(r'[^a-zA-Z0-9_-]', '_', name)[:80].strip("_") or "template"


# ─── CLI entry point ──────────────────────────────────────────────

def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    tl = TemplateLibrary()
    tl.sync(force="--force" in sys.argv)


if __name__ == "__main__":
    import sys
    main()
