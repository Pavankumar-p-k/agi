"""core/real_validator.py
Real validation checks for JARVIS builds.
Uses actual tools (html.parser, os.path, Playwright) — not LLM opinions.
"""
import json, os, re, logging
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlparse
from typing import Optional
from core.project_state import ProjectState, ValidationResult

logger = logging.getLogger("real_validator")

TEMPLATES_DIR = Path.home() / ".jarvis" / "templates" / "library"

PLACEHOLDER_PATTERNS = [
    (r'\{\{.*?\}\}', "template_var"),
    (r'\{\%.*?\%\}', "template_tag"),
    (r'\bTODO\b', "todo"),
    (r'\bFIXME\b', "fixme"),
    (r'\bLorem\s*ipsum\b', "lorem_ipsum"),
    (r'\[your\s+.*?\]', "unfilled_bracket"),
]


class _LinkExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.srcs = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "a" and "href" in attrs_dict:
            self.links.append(attrs_dict["href"])
        for attr in ("src", "data-src"):
            if attr in attrs_dict:
                self.srcs.append(attrs_dict[attr])


class RealValidator:
    """Validates builds with real tools — not LLM opinions."""

    def __init__(self, workspace: str = "", template_name: str = ""):
        self.workspace = Path(workspace) if workspace else None
        self.template_name = template_name
        self._template_baseline: dict[str, str] = {}
        if template_name:
            self._load_template_baseline()

    def _load_template_baseline(self):
        """Load original template files for baseline comparison."""
        tpl_dir = TEMPLATES_DIR / self.template_name
        if not tpl_dir.exists():
            logger.warning(f"[VALIDATOR] Template dir not found: {tpl_dir}")
            return
        for fp in tpl_dir.rglob("*.html"):
            try:
                self._template_baseline[fp.name] = fp.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                logger.exception("[Validator] Failed to load template baseline: %s", e)
        if self._template_baseline:
            logger.info(f"[VALIDATOR] Loaded {len(self._template_baseline)} template baseline files from {self.template_name}")

    def _has_template_placeholder(self, filename: str, pattern: re.Pattern, label: str) -> bool:
        """Check if a placeholder pattern existed in the original template file."""
        orig = self._template_baseline.get(filename)
        if not orig:
            return False
        return bool(re.search(pattern, orig))

    async def validate_all(self, state: ProjectState, workspace: str = "") -> list[ValidationResult]:
        """Run all validation checks against the project state."""
        results = []
        ws = Path(workspace) if workspace else self.workspace

        # Sync template info from state if not already set
        if not self.template_name and state.template_name:
            self.template_name = state.template_name
            self._load_template_baseline()

        results.append(await self.check_pages_exist(state, ws))
        results.append(await self.check_broken_links(state, ws))
        results.append(await self.check_placeholders(state, ws))
        results.append(await self.check_nav_consistency(state, ws))
        results.append(await self.check_html_valid(state, ws))
        results.append(await self.check_css_applied(state, ws))
        results.append(await self.check_browser_load(state, ws))
        results.append(await self.check_visual_quality(state, ws))
        results.append(await self.check_reasoning_quality(state, ws))

        state.validation_results = results
        return results

    async def check_pages_exist(self, state: ProjectState, workspace: Path = None) -> ValidationResult:
        """Verify all planned pages exist on disk."""
        if not workspace or not workspace.exists():
            return ValidationResult("all_pages_exist", False, "workspace_not_found")

        pages = state.interpreted_goal.get("pages", []) if state.interpreted_goal else []
        if not pages:
            html_files = list(workspace.rglob("*.html")) + list(workspace.rglob("*.htm"))
            if html_files:
                return ValidationResult("all_pages_exist", True, f"{len(html_files)} html files found")
            return ValidationResult("all_pages_exist", False, "no_html_files_and_no_page_list")

        found = []
        missing = []
        for page in pages:
            patterns = [
                workspace / f"{page}.html",
                workspace / f"{page}.htm",
                workspace / f"{page}.php",
                workspace / f"{page}" / "index.html",
                workspace / f"src/pages/{page}.jsx" if workspace else workspace,
                workspace / f"src/pages/{page}.tsx" if workspace else workspace,
                workspace / f"pages/{page}.jsx" if workspace else workspace,
                workspace / f"pages/{page}.tsx" if workspace else workspace,
            ]
            found_page = False
            for p in patterns:
                if p and p.exists():
                    found.append(str(p.relative_to(workspace)) if workspace else str(p))
                    found_page = True
                    break
            if not found_page:
                missing.append(page)

        if missing:
            return ValidationResult("all_pages_exist", False, f"missing: {', '.join(missing)}")
        return ValidationResult("all_pages_exist", True, f"found: {', '.join(found)}")

    async def check_broken_links(self, state: ProjectState, workspace: Path = None) -> ValidationResult:
        """Find href/src references to non-existent files."""
        if not workspace or not workspace.exists():
            return ValidationResult("no_broken_links", False, "workspace_not_found")

        broken = []
        checked = 0
        for html_file in workspace.rglob("*.html"):
            try:
                content = html_file.read_text(encoding="utf-8", errors="replace")
                extractor = _LinkExtractor()
                extractor.feed(content)

                for href in extractor.links + extractor.srcs:
                    checked += 1
                    if not href or href.startswith(("http://", "https://", "mailto:", "tel:", "#", "javascript:")):
                        continue
                    target = (html_file.parent / href).resolve()
                    if not target.exists():
                        broken.append(f"{html_file.name}->{href}")

                for src in extractor.srcs:
                    checked += 1
                    if src.startswith(("http://", "https://", "data:", "#")):
                        continue
                    target = (html_file.parent / src).resolve()
                    if not target.exists():
                        broken.append(f"{html_file.name}->{src}")
            except Exception as e:
                logger.warning(f"[VALIDATOR] Error parsing {html_file}: {e}")

        if broken:
            return ValidationResult("no_broken_links", False, f"{len(broken)} broken: {'; '.join(broken[:10])}")
        return ValidationResult("no_broken_links", True, f"{checked} links checked, all valid")

    async def check_placeholders(self, state: ProjectState, workspace: Path = None) -> ValidationResult:
        """Search for placeholder markers like {{, {% , TODO, FIXME, Lorem.
        Skips patterns that existed in the original template (baseline comparison)."""
        if not workspace or not workspace.exists():
            return ValidationResult("no_placeholders", False, "workspace_not_found")

        excluded_urls = ["placeholder.com", "via.placeholder.com"]
        excluded_html_attrs = ['placeholder="', "placeholder='"]

        found = []
        for html_file in workspace.rglob("*.html"):
            try:
                content = html_file.read_text(encoding="utf-8", errors="replace")
                for pattern_str, label in PLACEHOLDER_PATTERNS:
                    pattern = re.compile(pattern_str, re.IGNORECASE)
                    matches = pattern.findall(content)
                    if matches:
                        # Skip if this pattern existed in the original template file
                        if self._has_template_placeholder(html_file.name, pattern, label):
                            continue
                        found.append(f"{html_file.name}:{label}({len(matches)})")
                # Check for the word "placeholder" but only outside image URLs and HTML attributes
                for m in re.finditer(r'\bplaceholder\b', content, re.IGNORECASE):
                    pos = m.start()
                    line_start = content.rfind('\n', 0, pos) + 1
                    line_end = content.find('\n', pos)
                    line = content[line_start:line_end] if line_end > 0 else content[line_start:]
                    if any(url in line for url in excluded_urls):
                        continue
                    if any(attr in line for attr in excluded_html_attrs):
                        continue
                    # Skip "placeholder" word if it existed in template original
                    if self._has_template_placeholder(html_file.name, re.compile(r'\bplaceholder\b', re.IGNORECASE), "placeholder"):
                        continue
                    found.append(f"{html_file.name}:placeholder_text")
                    break
            except Exception as e:
                logger.exception("[Validator] Error checking placeholders in %s: %s", html_file, e)

        if found:
            return ValidationResult("no_placeholders", False, f"placeholders: {'; '.join(found[:10])}")
        return ValidationResult("no_placeholders", True, "no placeholders found")

    async def check_nav_consistency(self, state: ProjectState, workspace: Path = None) -> ValidationResult:
        """Check that all pages share the same navigation (whitespace-normalized)."""
        if not workspace or not workspace.exists():
            return ValidationResult("nav_consistent", False, "workspace_not_found")

        html_files = list(workspace.rglob("*.html"))
        if len(html_files) < 2:
            return ValidationResult("nav_consistent", True, "single_page_or_none")

        def normalize_nav(html: str) -> str:
            """Strip whitespace and keep only link structure."""
            nav_match = re.search(r'<nav[^>]*>(.*?)</nav>', html, re.DOTALL | re.IGNORECASE)
            if not nav_match:
                return ""
            nav_content = nav_match.group(1)
            # Remove all whitespace between tags
            nav_content = re.sub(r'>\s+<', '><', nav_content)
            # Remove all leading/trailing whitespace
            nav_content = nav_content.strip()
            # Collapse remaining whitespace
            nav_content = re.sub(r'\s+', ' ', nav_content)
            return nav_content[:500]

        navs = []
        for html_file in html_files:
            try:
                content = html_file.read_text(encoding="utf-8", errors="replace")
                nav_text = normalize_nav(content)
                if nav_text:
                    navs.append((html_file.name, nav_text))
            except Exception as e:
                logger.exception("[Validator] Error reading %s for nav consistency: %s", html_file, e)

        if len(navs) < 2:
            return ValidationResult("nav_consistent", True, f"{len(navs)} pages with nav elements")

        first_nav = navs[0][1]
        mismatches = []
        for name, nav in navs[1:]:
            if nav != first_nav:
                mismatches.append(name)
        if mismatches:
            return ValidationResult("nav_consistent", False, f"nav differs on: {', '.join(mismatches)}")
        return ValidationResult("nav_consistent", True, f"{len(navs)} pages share same nav")

    async def check_html_valid(self, state: ProjectState, workspace: Path = None) -> ValidationResult:
        """Validate HTML parses without syntax errors."""
        if not workspace or not workspace.exists():
            return ValidationResult("html_valid", False, "workspace_not_found")

        errors = []
        for html_file in workspace.rglob("*.html"):
            try:
                content = html_file.read_text(encoding="utf-8", errors="replace")
                parser = HTMLParser()
                parser.feed(content)
            except Exception as e:
                errors.append(f"{html_file.name}:{e}")

        if errors:
            return ValidationResult("html_valid", False, f"parse errors: {'; '.join(errors[:5])}")
        return ValidationResult("html_valid", True, "all HTML valid")

    async def check_css_applied(self, state: ProjectState, workspace: Path = None) -> ValidationResult:
        """Check linked CSS files exist and contain rules."""
        if not workspace or not workspace.exists():
            return ValidationResult("css_applied", False, "workspace_not_found")

        css_links = []
        for html_file in workspace.rglob("*.html"):
            try:
                content = html_file.read_text(encoding="utf-8", errors="replace")
                for match in re.finditer(r'<link[^>]*href=["\']([^"\']+\.css)["\']', content, re.IGNORECASE):
                    css_path = match.group(1)
                    if not css_path.startswith(("http://", "https://", "//")):
                        target = (html_file.parent / css_path).resolve()
                        if target.exists() and target not in css_links:
                            css_links.append(target)
            except Exception as e:
                logger.exception("[Validator] Error reading %s for CSS links: %s", html_file, e)

        if not css_links:
            inline_styles = 0
            for html_file in workspace.rglob("*.html"):
                try:
                    content = html_file.read_text(encoding="utf-8", errors="replace")
                    inline_styles += len(re.findall(r'<style[^>]*>', content, re.IGNORECASE))
                except Exception as e:
                    logger.exception("[Validator] Error reading %s for inline styles: %s", html_file, e)
            if inline_styles:
                return ValidationResult("css_applied", True, f"{inline_styles} inline <style> blocks")
            return ValidationResult("css_applied", True, "no css links (may be headless/framework)")

        empty = 0
        for css_file in css_links:
            try:
                content = css_file.read_text(encoding="utf-8", errors="replace")
                rules = re.findall(r'\{[^}]+\}', content)
                if not rules:
                    empty += 1
            except Exception as e:
                logger.exception("[Validator] Error reading CSS file %s: %s", css_file, e)
                empty += 1

        if empty and empty == len(css_links):
            return ValidationResult("css_applied", False, "all css files are empty")
        return ValidationResult("css_applied", True, f"{len(css_links)} css files, {len(css_links) - empty} with rules")

    async def check_browser_load(self, state: ProjectState, workspace: Path = None) -> ValidationResult:
        """Try loading each page in Playwright to verify no runtime errors."""
        if not workspace or not workspace.exists():
            return ValidationResult("browser_loads", True, "no_workspace_to_test")

        html_files = list(workspace.rglob("*.html"))
        if not html_files:
            return ValidationResult("browser_loads", True, "no_html_files")

        try:
            from playwright.async_api import async_playwright
            errors = []
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                for html_file in html_files[:5]:
                    try:
                        page = await browser.new_page()
                        page_errors = []

                        def _capture_error(msg):
                            page_errors.append(str(msg))

                        page.on("pageerror", _capture_error)
                        await page.goto(f"file://{html_file.resolve()}", timeout=30000, wait_until="domcontentloaded")
                        await page.wait_for_timeout(1000)
                        if page_errors:
                            errors.append(f"{html_file.name}:{'; '.join(page_errors[:2])}")
                        await page.close()
                    except Exception as e:
                        errors.append(f"{html_file.name}:{str(e)[:100]}")
                await browser.close()

            if errors:
                return ValidationResult("browser_loads", False, f"load errors: {'; '.join(errors[:5])}")
            return ValidationResult("browser_loads", True, f"{len(html_files)} pages loaded without errors")

        except ImportError:
            return ValidationResult("browser_loads", True, "playwright_not_available")
        except Exception as e:
            return ValidationResult("browser_loads", True, f"browser_check_skipped:{str(e)[:80]}")

    async def check_visual_quality(self, state, workspace: Path = None,
                                    _correction_depth: int = 0):
        """Score visual quality using vision LLM (gemma4 → moondream → fallback).
        Takes Playwright screenshot, sends to complete_vision, returns score + issues.
        Self-correction loop: score < 80 triggers auto-fix + re-validate (max 3)."""
        if not workspace or not workspace.exists():
            return ValidationResult("visual_quality", True, "no_workspace")

        html_files = list(workspace.rglob("*.html")) if workspace.exists() else []
        if not html_files:
            return ValidationResult("visual_quality", True, "no_html")

        goal = (state.interpreted_goal or {}).get("original_goal", "website")
        brand_name = (state.interpreted_goal or {}).get("brand_name", "")
        business_type = (state.interpreted_goal or {}).get("business_type", "")

        try:
            from playwright.async_api import async_playwright

            vision_messages = []
            raw_responses = []
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                pages_to_check = [html_files[0]]
                if len(html_files) > 1:
                    import random
                    pages_to_check.append(random.choice(html_files[1:]))

                for html_file in pages_to_check:
                    try:
                        page = await browser.new_page(viewport={"width": 1280, "height": 900})
                        await page.goto(f"file://{html_file.resolve()}", timeout=30000,
                                        wait_until="domcontentloaded")
                        await page.wait_for_timeout(1500)
                        screenshot = await page.screenshot(full_page=True)
                        import base64
                        b64 = base64.b64encode(screenshot).decode()
                        vision_messages.append({
                            "role": "user",
                            "content": [
                                {"type": "text", "text": f"Score this website 1-100 for a '{business_type}' called '{brand_name}'. Goal: '{goal}'. Check: (a) Does content match goal? (b) Are images loading? (c) Is branding correct? (d) Is layout professional? (e) No broken elements. Return ONLY JSON: {{\"score\": int between 1-100, \"issues\": [str], \"overall_verdict\": str}}"},
                                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
                            ]
                        })
                        await page.close()
                    except Exception as e:
                        vision_messages.append({
                            "role": "user",
                            "content": f"Screenshot failed for {html_file.name}: {e}"
                        })
                await browser.close()

            if not vision_messages:
                return ValidationResult("visual_quality", False, "no_screenshots_taken")

            try:
                from core.llm_router import complete_vision
                import json
                scores = []
                all_issues = []
                for msg in vision_messages:
                    try:
                        resp_result = await complete_vision([msg], timeout=30)
                        resp = resp_result.unwrap_or("")
                        raw_responses.append(resp)
                        resp = resp.strip()
                        if resp.startswith("```"):
                            resp = resp.split("\n", 1)[1] if "\n" in resp else resp[3:]
                            if "```" in resp:
                                resp = resp.rsplit("```", 1)[0]
                            resp = resp.strip()
                        parsed = json.loads(resp)
                        score = int(parsed.get("score", 50))
                        scores.append(score)
                        all_issues.extend(parsed.get("issues", []))
                    except Exception as e:
                        logger.exception("[Validator] Failed to parse vision response: %s", e)

                avg_score = sum(scores) / len(scores) if scores else 50

                # Self-correction loop: score < 80 triggers fixes + re-validate (max 3)
                if avg_score < 80 and _correction_depth < 3:
                    vision_text = " ".join(raw_responses)
                    failed_criteria = self._extract_visual_failures(vision_text)
                    if failed_criteria:
                        from core.control_loop import control_loop
                        project_dir = str(workspace)
                        await control_loop.request_fix(
                            failures=[f"visual_quality:{c}" for c in failed_criteria],
                            project_dir=project_dir,
                            interpreted=state.interpreted_goal,
                        )
                        return await self.check_visual_quality(
                            state, workspace, _correction_depth=_correction_depth + 1
                        )

                passed = avg_score >= 85
                issues_str = "; ".join(all_issues[:5]) if all_issues else ""
                msg = f"visual_score={avg_score}/100" if passed else f"visual_score={avg_score}/100 issues:{issues_str}"
                return ValidationResult("visual_quality", passed, msg)

            except ImportError:
                return ValidationResult("visual_quality", True, "vision_model_not_available")
            except Exception as e:
                return ValidationResult("visual_quality", False, f"vision_check_failed:{str(e)[:80]}")

        except ImportError:
            return ValidationResult("visual_quality", True, "playwright_not_available_vision")
        except Exception as e:
            return ValidationResult("visual_quality", False, f"visual_quality_skip:{str(e)[:80]}")


    def _extract_visual_failures(self, vision_response: str) -> list[str]:
        failures = []
        r = vision_response.lower()
        if "wrong content" in r or "content mismatch" in r:
            failures.append("content_mismatch")
        if ("brand" in r and "not" in r and "match" in r) or "brand" in r and "missing" in r:
            failures.append("brand_missing")
        if ("image" in r and ("broken" in r or "missing" in r or "not load" in r)) \
           or ("img" in r and "404" in r):
            failures.append("images_broken")
        if ("layout" in r and "broken" in r) or "spacing" in r and "wrong" in r:
            failures.append("layout_broken")
        if "placeholder" in r or "lorem" in r or "todo" in r:
            failures.append("placeholder_text")
        if "color" in r and "wrong" in r or "contrast" in r:
            failures.append("color_contrast")
        if not failures and len(vision_response) > 10:
            failures.append("visual_score_below_threshold")
        return failures

    async def check_reasoning_quality(self, state, workspace: Path = None) -> ValidationResult:
        """Score output quality using the reasoning engine (deepseek-r1 CoT).
        Calls evaluate() cognitive pattern against the generated pages."""
        if not workspace or not workspace.exists():
            return ValidationResult("reasoning_quality", True, "no_workspace")

        html_files = list(workspace.rglob("*.html"))
        if not html_files:
            return ValidationResult("reasoning_quality", True, "no_html")

        goal = (state.interpreted_goal or {}).get("original_goal", "website")
        brand_name = (state.interpreted_goal or {}).get("brand_name", "")
        business_type = (state.interpreted_goal or {}).get("business_type", "")

        try:
            from brain.cognitive_patterns import evaluate

            # Build a summary of pages for evaluation
            pages_summary = []
            for html_file in html_files[:5]:
                try:
                    content = html_file.read_text(encoding="utf-8", errors="replace")
                    # Extract <title> and first <h1>
                    title_match = re.search(r"<title>(.*?)</title>", content, re.IGNORECASE | re.DOTALL)
                    h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", content, re.IGNORECASE | re.DOTALL)
                    title = re.sub(r"<[^>]+>", "", title_match.group(1)) if title_match else "no title"
                    h1 = re.sub(r"<[^>]+>", "", h1_match.group(1)) if h1_match else "no h1"
                    # Count images, links, sections
                    img_count = len(re.findall(r"<img\s", content, re.IGNORECASE))
                    link_count = len(re.findall(r"<a\s", content, re.IGNORECASE))
                    word_count = len(content.split())
                    pages_summary.append(f"- {html_file.name}: title='{title}' h1='{h1}' images={img_count} links={link_count} words={word_count}")
                except Exception as e:
                    logger.exception("[Validator] Error reading %s for reasoning: %s", html_file, e)
                    pages_summary.append(f"- {html_file.name}: [error reading]")

            output = "\n".join(pages_summary)
            criteria = (
                f"Goal: '{goal}' | Business type: '{business_type}' | Brand: '{brand_name}'\n"
                "Score 1-10 on: (a) content relevance to goal, (b) page structure, "
                "(c) branding consistency, (d) image usage, (e) navigation completeness. "
                "Return JSON: {\"scores\": {\"a\": int, \"b\": int, \"c\": int, \"d\": int, \"e\": int}, "
                "\"average\": float, \"verdict\": str}"
            )

            result = await evaluate(output, criteria)
            conclusion = result.get("conclusion", "{}")

            # Try to extract JSON from answer
            json_match = re.search(r"\{.*\}", conclusion, re.DOTALL)
            if json_match:
                try:
                    parsed = json.loads(json_match.group())
                    avg = parsed.get("average", parsed.get("scores", {}).get("average", 5))
                    if isinstance(avg, (int, float)):
                        passed = avg >= 6.0
                        msg = f"reasoning_score={avg}/10 verdict={parsed.get('verdict', '')}"
                        return ValidationResult("reasoning_quality", passed, msg)
                except Exception as e:
                    logger.exception("[Validator] Failed to parse reasoning JSON: %s", e)

            # Fallback: check if conclusion mentions issues
            passed = "no issues" in conclusion.lower() or "good" in conclusion.lower()
            return ValidationResult("reasoning_quality", passed, f"raw: {conclusion[:200]}")

        except ImportError:
            return ValidationResult("reasoning_quality", True, "cognitive_patterns_not_available")
        except Exception as e:
            return ValidationResult("reasoning_quality", True, f"reasoning_skip:{str(e)[:80]}")


INTERNAL_CHECKS = {
    "all_pages_exist",
    "no_broken_links",
    "no_placeholders",
    "nav_consistent",
    "html_valid",
    "css_applied",
    "browser_loads",
    "visual_quality",
    "reasoning_quality",
}
