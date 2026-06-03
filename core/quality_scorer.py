"""core/quality_scorer.py
Scores build output quality on design, responsiveness, content, nav, and code.
Enables ranking across runs for best-of-N selection.
"""
import os, re, logging
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

SCORE_RANGES = {
    "design_consistency": (0, 10),
    "responsiveness": (0, 10),
    "content_quality": (0, 10),
    "navigation_quality": (0, 10),
    "code_quality": (0, 10),
}


@dataclass
class ScoreBreakdown:
    design_consistency: float = 0.0
    responsiveness: float = 0.0
    content_quality: float = 0.0
    navigation_quality: float = 0.0
    code_quality: float = 0.0

    @property
    def total(self) -> float:
        return sum([self.design_consistency, self.responsiveness, self.content_quality,
                    self.navigation_quality, self.code_quality])

    @property
    def average(self) -> float:
        return self.total / 5.0

    def to_dict(self) -> dict:
        return {
            "design_consistency": self.design_consistency,
            "responsiveness": self.responsiveness,
            "content_quality": self.content_quality,
            "navigation_quality": self.navigation_quality,
            "code_quality": self.code_quality,
            "total": round(self.total, 1),
            "average": round(self.average, 1),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ScoreBreakdown":
        return cls(
            design_consistency=d.get("design_consistency", 0.0),
            responsiveness=d.get("responsiveness", 0.0),
            content_quality=d.get("content_quality", 0.0),
            navigation_quality=d.get("navigation_quality", 0.0),
            code_quality=d.get("code_quality", 0.0),
        )


class QualityScorer:
    def __init__(self, workspace: str = ""):
        self.workspace = Path(workspace) if workspace else None

    def score_all(self, project_name: str = "") -> ScoreBreakdown:
        ws = self.workspace
        if not ws or not ws.exists():
            return ScoreBreakdown()

        return ScoreBreakdown(
            design_consistency=self._score_design(ws),
            responsiveness=self._score_responsiveness(ws),
            content_quality=self._score_content(ws),
            navigation_quality=self._score_navigation(ws),
            code_quality=self._score_code(ws),
        )

    def _score_design(self, ws: Path) -> float:
        html_files = list(ws.rglob("*.html"))
        if not html_files:
            return 0.0

        css_link_count = 0
        style_block_count = 0
        has_color_vars = False
        has_font_imports = False

        for fp in html_files:
            try:
                content = fp.read_text(encoding="utf-8", errors="replace")
                css_link_count += len(re.findall(r'<link[^>]*href=["\'][^"\']+\.css', content))
                style_block_count += len(re.findall(r'<style[^>]*>', content))
                if re.search(r'--[\w-]+:', content):
                    has_color_vars = True
                if re.search(r'@import\s+url|@font-face|fonts\.googleapis', content):
                    has_font_imports = True
            except Exception as e:
                logger.exception("[Quality] error reading design file: %s", e)

        score = 3.0
        if css_link_count > 0 or style_block_count > 0:
            score += 2.0
        if has_color_vars:
            score += 2.5
        if has_font_imports:
            score += 1.5
        if css_link_count > 2 or style_block_count > 2:
            score += 1.0

        return min(score, 10.0)

    def _score_responsiveness(self, ws: Path) -> float:
        html_files = list(ws.rglob("*.html"))
        if not html_files:
            return 0.0

        has_viewport = False
        has_media_queries = False
        has_flex_or_grid = False
        has_responsive_images = False

        for fp in html_files:
            try:
                content = fp.read_text(encoding="utf-8", errors="replace")
                if re.search(r'<meta\s+[^>]*name=["\']viewport["\']', content, re.IGNORECASE):
                    has_viewport = True
                if re.search(r'@media\s*\(', content):
                    has_media_queries = True
                if re.search(r'display\s*:\s*(flex|grid)', content):
                    has_flex_or_grid = True
                if re.search(r'max-width:\s*100%|width:\s*100%\s*[;}]', content):
                    has_responsive_images = True
            except Exception as e:
                logger.exception("[Quality] error reading responsiveness file: %s", e)

        score = 2.0
        if has_viewport:
            score += 2.5
        if has_media_queries:
            score += 2.5
        if has_flex_or_grid:
            score += 1.5
        if has_responsive_images:
            score += 1.5

        return min(score, 10.0)

    def _score_content(self, ws: Path) -> float:
        html_files = list(ws.rglob("*.html"))
        if not html_files:
            return 0.0

        total_words = 0
        has_placeholder = False
        has_meaningful_headings = False
        heading_count = 0

        for fp in html_files:
            try:
                content = fp.read_text(encoding="utf-8", errors="replace")
                text = re.sub(r'<[^>]+>', ' ', content)
                total_words += len(text.split())
                if re.search(r'\bLorem\s*ipsum\b', content, re.IGNORECASE):
                    has_placeholder = True
                headings = re.findall(r'<h[1-3][^>]*>(.*?)</h[1-3]>', content, re.DOTALL | re.IGNORECASE)
                for h in headings:
                    h_clean = re.sub(r'<[^>]+>', '', h).strip()
                    if len(h_clean) > 3 and h_clean.lower() not in ("home", "about", "contact"):
                        has_meaningful_headings = True
                        heading_count += 1
            except Exception as e:
                logger.exception("[Quality] error reading content file: %s", e)

        score = 2.0
        if total_words > 200:
            score += 2.0
        if total_words > 500:
            score += 1.5
        if has_meaningful_headings:
            score += 2.5
        if heading_count > 3:
            score += 1.0
        if not has_placeholder:
            score += 1.0

        return min(score, 10.0)

    def _score_navigation(self, ws: Path) -> float:
        html_files = list(ws.rglob("*.html"))
        if not html_files:
            return 0.0

        nav_links = set()
        has_nav_tag = False
        total_links = 0

        for fp in html_files:
            try:
                content = fp.read_text(encoding="utf-8", errors="replace")
                if re.search(r'<nav[^>]*>', content, re.IGNORECASE):
                    has_nav_tag = True
                for m in re.finditer(r'<a[^>]*href=["\']([^"\']+)["\']', content, re.IGNORECASE):
                    href = m.group(1)
                    if not href.startswith(("#", "http", "mailto", "tel", "javascript:")):
                        nav_links.add(href)
                        total_links += 1
            except Exception as e:
                logger.exception("[Quality] error reading navigation file: %s", e)

        score = 2.0
        if has_nav_tag:
            score += 2.5
        if total_links >= len(html_files):
            score += 2.5
        if len(nav_links) >= 3:
            score += 2.0
        if total_links > 10:
            score += 1.0

        return min(score, 10.0)

    def _score_code(self, ws: Path) -> float:
        html_files = list(ws.rglob("*.html"))
        if not html_files:
            return 0.0

        valid_html_count = 0
        has_doctype = False
        has_lang = False
        has_charset = False
        total_size = 0

        for fp in html_files:
            try:
                content = fp.read_text(encoding="utf-8", errors="replace")
                total_size += len(content)
                if re.match(r'<!DOCTYPE\s+html', content, re.IGNORECASE):
                    has_doctype = True
                    valid_html_count += 1
                if re.search(r'<html[^>]*lang=["\']', content, re.IGNORECASE):
                    has_lang = True
                if re.search(r'<meta[^>]*charset=["\']?utf-?8', content, re.IGNORECASE):
                    has_charset = True
            except Exception as e:
                logger.exception("[Quality] error reading code file: %s", e)

        score = 2.0
        if has_doctype:
            score += 2.5
        if has_lang:
            score += 1.5
        if has_charset:
            score += 1.5
        if valid_html_count == len(html_files):
            score += 1.5
        if total_size > 5000:
            score += 1.0

        return min(score, 10.0)


quality_scorer = QualityScorer()
