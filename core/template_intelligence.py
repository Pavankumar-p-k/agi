"""core/template_intelligence.py
Phase 4 (D4): Template Intelligence.
Smart template section-level composition: mix hero from A, features from B, footer from C.
Analyzes template structure and composes best sections.
"""
import os, re, json, logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path.home() / ".jarvis" / "templates" / "library"


@dataclass
class TemplateSection:
    name: str
    html: str
    source_template: str
    source_file: str
    word_count: int = 0
    has_forms: bool = False
    has_nav: bool = False
    has_footer: bool = False


@dataclass
class ComposedPlan:
    hero_template: str = ""
    features_template: str = ""
    footer_template: str = ""
    nav_template: str = ""
    reason: str = ""


SECTION_CLASSIFIERS = {
    "hero": [
        r'class="[^"]*hero[^"]*"', r'class="[^"]*banner[^"]*"', r'class="[^"]*header[^"]*"',
        r'id="[^"]*hero[^"]*"', r'id="[^"]*banner[^"]*"', r'<section[^>]*class="[^"]*top[^"]*"',
        r'class="[^"]*landing[^"]*"',
    ],
    "nav": [
        r'<nav[^>]*>', r'class="[^"]*navbar[^"]*"', r'class="[^"]*nav[^"]*"',
        r'class="[^"]*menu[^"]*"',
    ],
    "features": [
        r'class="[^"]*feature[^"]*"', r'class="[^"]*service[^"]*"', r'class="[^"]*card[^"]*"',
        r'class="[^"]*grid[^"]*"', r'class="[^"]*offer[^"]*"',
    ],
    "footer": [
        r'<footer[^>]*>', r'class="[^"]*footer[^"]*"', r'id="[^"]*footer[^"]*"',
    ],
    "cta": [
        r'class="[^"]*cta[^"]*"', r'class="[^"]*call-to-action[^"]*"',
        r'class="[^"]*signup[^"]*"',
    ],
    "testimonials": [
        r'class="[^"]*testimonial[^"]*"', r'class="[^"]*review[^"]*"',
    ],
    "contact": [
        r'class="[^"]*contact[^"]*"', r'id="[^"]*contact[^"]*"',
        r'<form[^>]*>',
    ],
}


class TemplateAnalyzer:
    def __init__(self):
        self._section_cache: dict[str, dict] = {}

    def analyze_template(self, template_name: str) -> dict[str, list[TemplateSection]]:
        if template_name in self._section_cache:
            return self._section_cache[template_name]

        tpl_dir = TEMPLATES_DIR / template_name
        if not tpl_dir.exists():
            return {}

        sections: dict[str, list[TemplateSection]] = {}
        for fp in sorted(tpl_dir.rglob("*.html")):
            try:
                content = fp.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                logger.exception("[TMPLINTEL] read error: %s", e)
                continue
            for section_type, patterns in SECTION_CLASSIFIERS.items():
                for pat in patterns:
                    matches = list(re.finditer(pat, content, re.IGNORECASE))
                    for m in matches:
                        start = max(0, m.start() - 200)
                        end = min(len(content), m.end() + 1000)
                        snippet = content[start:end]
                        sec = TemplateSection(
                            name=f"{section_type}_{len(sections.get(section_type, [])) + 1}",
                            html=snippet,
                            source_template=template_name,
                            source_file=str(fp),
                            word_count=len(snippet.split()),
                            has_forms="<form" in snippet,
                            has_nav="<nav" in snippet or "navbar" in snippet,
                            has_footer="<footer" in snippet or "footer" in snippet,
                        )
                        sections.setdefault(section_type, []).append(sec)
                        break

        self._section_cache[template_name] = sections
        return sections

    def rank_templates(self, goal: str, project_type: str) -> list[str]:
        if not TEMPLATES_DIR.exists():
            return []
        scored: list[tuple[float, str]] = []
        goal_lower = goal.lower()
        for d in sorted(TEMPLATES_DIR.iterdir()):
            if not d.is_dir():
                continue
            score = 0.0
            sections = self.analyze_template(d.name)
            if "hero" in sections:
                score += 2.0
            if "nav" in sections:
                score += 1.0
            if "features" in sections:
                score += 1.5
            if "footer" in sections:
                score += 0.5
            if "contact" in sections:
                score += 1.0
            if "testimonials" in sections and "testimonial" in goal_lower:
                score += 2.0
            if "cta" in sections:
                score += 1.0
            scored.append((score, d.name))
        scored.sort(reverse=True)
        return [s[1] for s in scored[:5]]

    def compose_best(self, goal: str, project_type: str) -> ComposedPlan:
        ranked = self.rank_templates(goal, project_type)
        if not ranked:
            return ComposedPlan()

        plan = ComposedPlan()
        for tpl in ranked:
            sections = self.analyze_template(tpl)
            if not plan.hero_template and "hero" in sections:
                plan.hero_template = tpl
            if not plan.nav_template and "nav" in sections:
                plan.nav_template = tpl
            if not plan.features_template and "features" in sections:
                plan.features_template = tpl
            if not plan.footer_template and "footer" in sections:
                plan.footer_template = tpl

        plan.reason = f"Composed from top {len(ranked)} templates: hero={plan.hero_template}, features={plan.features_template}, nav={plan.nav_template}, footer={plan.footer_template}"
        logger.info(f"[TMPLINTEL] {plan.reason}")
        return plan


template_analyzer = TemplateAnalyzer()
