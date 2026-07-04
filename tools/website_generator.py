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
"""tools/website_generator.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
JARVIS AI-Powered Website Generator — Production Edition
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Replaces the static-template approach with a 5-step pipeline:
  1. Research  — search for topic best-practices & colour schemes
  2. Design    — LLM generates a CSS design system (variables)
  3. Generate  — LLM writes each page from scratch (real content)
  4. Post-proc — validate HTML, write assets, sitemap, README
  5. Preview   — spin up http.server on a free port

Drop-in compatible: generate_site / generate_site_async keep the
same signature as before plus the new `style` parameter.

Open-source template repos used as reference/inspiration (NOT
bundled — the LLM generates everything from scratch):
  • HTML5 UP          https://github.com/ajlkn/html5up
  • Dimension         https://github.com/html5up/dimension (MIT)
  • Strata            https://github.com/html5up/strata   (MIT)
  • Start Bootstrap   https://github.com/StartBootstrap    (MIT)
  • Bulma             https://github.com/jgthms/bulma      (MIT) [ref only]
  • Skeleton          https://github.com/dhg/Skeleton      (MIT)
  • Pure.css          https://github.com/pure-css/pure     (BSD)
  • Milligram         https://github.com/milligram/milligram (MIT)
  • Tailwind          https://github.com/tailwindlabs/tailwindcss (MIT) [ref only]
  • Spectre.css       https://github.com/picturepan2/spectre (MIT)
  All CSS is generated inline — NO external framework loaded.
"""

from __future__ import annotations

import asyncio
import html.parser
import json
import logging
import os
import re
import socket
import threading
import time
import uuid
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from xml.etree.ElementTree import Element, SubElement, tostring

logger = logging.getLogger("website_generator")

# ─── Paths ────────────────────────────────────────────────────────────────────
SITES_DIR = Path.home() / ".jarvis" / "generated_sites"

# ─── Active preview servers: port → HTTPServer ────────────────────────────────
_preview_servers: Dict[int, HTTPServer] = {}
_preview_dirs:    Dict[int, str]        = {}

# ─── Style presets ────────────────────────────────────────────────────────────
STYLE_HINTS = {
    "modern":    "Clean, minimal, lots of white space, sans-serif, subtle gradients.",
    "corporate": "Professional, trust-building, blue tones, structured grids.",
    "creative":  "Bold typography, vivid accent colours, asymmetric layouts.",
    "dark":      "Dark background, light text, neon or gold accents, sleek.",
    "elegant":   "Serif fonts, muted palette, generous padding, luxury feel.",
    "tech":      "Terminal-inspired, monospace accents, matrix greens or cyber blues.",
    "warm":      "Earthy tones, organic shapes, friendly rounded corners.",
    "minimal":   "Absolute minimalism — typography only, near-zero decoration.",
}

# ─── Fallback template (used when LLM is fully unavailable) ───────────────────
FALLBACK_CSS = """
:root{
  --primary:#2563eb;--secondary:#1e40af;--accent:#f59e0b;
  --bg:#ffffff;--bg2:#f8fafc;--text:#1e293b;--muted:#64748b;
  --font-heading:'Segoe UI',system-ui,sans-serif;
  --font-body:'Segoe UI',system-ui,sans-serif;
  --radius:8px;--shadow:0 4px 24px rgba(0,0,0,.08);
  --max-w:1180px;--transition:.22s ease;
}
"""

# ─── HTML validator ───────────────────────────────────────────────────────────
class _HTMLChecker(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.errors: List[str] = []

    def handle_error(self, message: str) -> None:      # type: ignore[override]
        self.errors.append(message)


def _validate_html(src: str) -> Tuple[bool, List[str]]:
    checker = _HTMLChecker()
    try:
        checker.feed(src)
        checker.close()
        return True, checker.errors
    except Exception as exc:
        return False, [str(exc)]


def _has_html_structure(src: str) -> bool:
    low = src.lower()
    return "<!doctype html" in low and "<html" in low and "<body" in low


# ─── LLM helpers ──────────────────────────────────────────────────────────────
async def _llm(prompt: str, mode: str = "code", timeout: int = 90) -> str:
    """
    Call Jarvis LLM router.  Falls back to Ollama direct if router unavailable.
    Returns raw text or "" on failure.
    """
    try:
        from core.llm_router import complete as llm_complete          # type: ignore
        result = await asyncio.wait_for(
            llm_complete(mode, [{"role": "user", "content": prompt}]),
            timeout=timeout,
        )
        text = result.unwrap_or("")
        return _strip_fences(text)
    except Exception as e:
        logger.warning("[website_generator] llm_router unavailable: %s — trying Ollama", e)

    try:
        import aiohttp
        payload = {
            "model": "llama3",
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.7, "num_predict": 4096},
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://localhost:11434/api/generate",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                data = await resp.json()
                return _strip_fences(data.get("response", ""))
    except Exception as e2:
        logger.warning("[website_generator] Ollama unavailable: %s", e2)
        return ""


def _strip_fences(text: str) -> str:
    """Remove ```html or ``` code fences from LLM output."""
    text = text.strip()
    for fence in ("```html", "```css", "```xml", "```"):
        if fence in text:
            parts = text.split(fence)
            # grab the first fenced block
            if len(parts) >= 3:
                return parts[1].strip()
            elif len(parts) == 2:
                return parts[1].split("```")[0].strip()
    return text


# ─── Step 1: Research ─────────────────────────────────────────────────────────
async def _research(topic: str) -> List[str]:
    """Return up to 5 keyword/insight strings for the topic."""
    facts: List[str] = []
    try:
        from tools.search_tool import search                          # type: ignore
        for query in (f"{topic} website best practices", f"{topic} color scheme design"):
            try:
                results = await asyncio.wait_for(search(query), timeout=15)
                if isinstance(results, list):
                    for r in results[:3]:
                        snippet = r.get("snippet") or r.get("title") or ""
                        if snippet:
                            facts.append(snippet[:200])
                elif isinstance(results, str):
                    facts.append(results[:200])
                if len(facts) >= 5:
                    break
            except Exception as e:
                logger.debug("[website_generator] search error: %s", e)
    except ImportError:
        logger.debug("[website_generator] search_tool not available — skipping research")

    # Always pad with sensible defaults
    if not facts:
        facts = [
            f"{topic} — focus on clarity and user experience.",
            "Use consistent colour palette and typography.",
            "Mobile-first responsive layout is essential.",
            "Clear calls-to-action on every page.",
            "Fast load time: inline critical CSS, lazy images.",
        ]
    return facts[:5]


# ─── Step 2: Design system ────────────────────────────────────────────────────
async def _design_system(topic: str, style: str, facts: List[str]) -> str:
    """Ask LLM for CSS :root{} variables. Returns raw CSS string."""
    hint = STYLE_HINTS.get(style, STYLE_HINTS["modern"])
    context = "; ".join(facts[:3]) if facts else ""
    prompt = (
        f"Generate a CSS design system for a '{topic}' website.\n"
        f"Style direction: {hint}\n"
        f"Research context: {context}\n\n"
        "Return ONLY a valid CSS :root{{}} block (no prose, no fences) containing:\n"
        "  --primary, --secondary, --accent, --bg, --bg2, --text, --muted,\n"
        "  --font-heading (Google Fonts @import string then family name),\n"
        "  --font-body, --radius, --shadow, --max-w (e.g. 1180px),\n"
        "  --transition (e.g. .22s ease).\n"
        "Make the colours bold and memorable, not generic. Return ONLY the CSS."
    )
    css = await _llm(prompt, mode="code", timeout=40)
    # Validate: must contain :root{ ... }
    if ":root" not in css and "--primary" not in css:
        logger.warning("[website_generator] design system LLM failed — using fallback")
        return FALLBACK_CSS
    # Ensure :root wrapper exists
    if ":root" not in css:
        css = f":root{{\n{css}\n}}"
    return css


# ─── Shared CSS base injected into every page ────────────────────────────────
_BASE_CSS = """
/* Jarvis Website Generator — shared base */
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth;font-size:16px}
body{font-family:var(--font-body,'Segoe UI',system-ui,sans-serif);
     background:var(--bg,#fff);color:var(--text,#111);line-height:1.7}
img{max-width:100%;height:auto;display:block}
a{color:var(--primary);text-decoration:none;transition:color var(--transition,.22s ease)}
a:hover{color:var(--accent,#f59e0b)}
h1,h2,h3,h4,h5,h6{
  font-family:var(--font-heading,'Segoe UI',system-ui,sans-serif);
  line-height:1.2;color:var(--text)}
.container{width:100%;max-width:var(--max-w,1180px);margin:0 auto;padding:0 24px}
.btn{display:inline-block;padding:14px 32px;border-radius:var(--radius,8px);
     font-weight:600;font-size:1rem;cursor:pointer;border:none;
     background:var(--primary);color:#fff;
     transition:transform var(--transition,.22s ease),
                box-shadow var(--transition,.22s ease)}
.btn:hover{transform:translateY(-2px);
           box-shadow:0 8px 32px rgba(0,0,0,.18);color:#fff}
.btn-outline{background:transparent;border:2px solid var(--primary);
             color:var(--primary)}
.btn-outline:hover{background:var(--primary);color:#fff}
section{padding:80px 0}
@media(max-width:768px){section{padding:48px 0}
  .container{padding:0 16px}
  h1{font-size:clamp(1.8rem,6vw,3rem)}}
/* Nav */
nav.site-nav{position:sticky;top:0;z-index:1000;
  background:rgba(255,255,255,.95);backdrop-filter:blur(10px);
  border-bottom:1px solid rgba(0,0,0,.06);
  box-shadow:0 2px 12px rgba(0,0,0,.04)}
nav.site-nav .nav-inner{
  display:flex;align-items:center;justify-content:space-between;
  max-width:var(--max-w,1180px);margin:0 auto;padding:0 24px;height:64px}
nav.site-nav .logo{font-family:var(--font-heading);font-size:1.35rem;
  font-weight:700;color:var(--primary)}
nav.site-nav ul{list-style:none;display:flex;gap:8px}
nav.site-nav ul li a{padding:8px 16px;border-radius:var(--radius,8px);
  font-weight:500;color:var(--text);transition:all var(--transition,.22s ease)}
nav.site-nav ul li a:hover,nav.site-nav ul li a.active{
  background:var(--primary);color:#fff}
.nav-toggle{display:none;flex-direction:column;gap:5px;cursor:pointer;
  background:none;border:none;padding:4px}
.nav-toggle span{width:24px;height:2px;background:var(--text);
  border-radius:2px;transition:all .3s}
@media(max-width:768px){
  .nav-toggle{display:flex}
  nav.site-nav ul{display:none;flex-direction:column;gap:0;
    position:absolute;top:64px;left:0;right:0;
    background:var(--bg,#fff);border-bottom:1px solid rgba(0,0,0,.08);
    padding:12px 0;box-shadow:0 8px 24px rgba(0,0,0,.1)}
  nav.site-nav ul.open{display:flex}
  nav.site-nav ul li a{padding:12px 24px;border-radius:0}}
/* Footer */
footer.site-footer{background:var(--text,#111);color:#fff;
  padding:48px 0 24px}
footer.site-footer .footer-grid{
  display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));
  gap:40px;margin-bottom:40px}
footer.site-footer h4{color:#fff;margin-bottom:16px;font-size:.95rem;
  text-transform:uppercase;letter-spacing:.05em}
footer.site-footer p,footer.site-footer a{color:rgba(255,255,255,.65);
  font-size:.9rem;line-height:1.8}
footer.site-footer a:hover{color:#fff}
footer.site-footer .footer-bottom{
  border-top:1px solid rgba(255,255,255,.1);
  padding-top:24px;text-align:center;
  color:rgba(255,255,255,.45);font-size:.85rem}
"""


def _build_google_fonts_import(design_css: str) -> str:
    """Extract any Google Fonts URL from the design system CSS."""
    m = re.search(r"@import\s+url\(['\"]?(https://fonts\.googleapis\.com[^'\")]+)['\"]?\)", design_css)
    if m:
        return f'<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n    <link rel="stylesheet" href="{m.group(1)}">'
    # Try to detect font names and build a URL
    m2 = re.search(r"--font-heading\s*:\s*['\"]?([^;,'\"]+)", design_css)
    if m2:
        fonts_raw = m2.group(1).strip().rstrip("'\"")
        font_name = re.split(r"[,'\"]", fonts_raw)[0].strip()
        # Only try to load from Google if it looks like a real Google Font
        known_gfonts = ["Inter","Poppins","Raleway","Montserrat","Lato","Playfair Display",
                        "Oswald","Merriweather","Nunito","Roboto","Source Sans Pro",
                        "Open Sans","Fira Sans","DM Sans","Space Grotesk","Syne","Outfit",
                        "Plus Jakarta Sans","Manrope","Cabinet Grotesk"]
        for gf in known_gfonts:
            if gf.lower() in font_name.lower():
                slug = gf.replace(" ", "+")
                return (f'<link rel="preconnect" href="https://fonts.googleapis.com">\n'
                        f'    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
                        f'    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family={slug}:wght@300;400;500;600;700;800&display=swap">')
    return ""


# ─── Step 3: Generate page ────────────────────────────────────────────────────
async def _generate_page(
    topic: str,
    page_name: str,
    pages: List[str],
    design_css: str,
    style: str,
    facts: List[str],
) -> str:
    """LLM generates a complete HTML page. Falls back to a high-quality template."""
    nav_links = " | ".join(
        f"{'index' if p == 'index' else p}.html" for p in pages
    )
    pages_list = ", ".join(pages)
    facts_text = "\n".join(f"- {f}" for f in facts)
    page_label = page_name.replace("-", " ").title()
    hint = STYLE_HINTS.get(style, "")

    prompt = f"""Generate a complete, professional, modern HTML5 page for a '{topic}' website.

PAGE: {page_label}
ALL PAGES IN SITE: {pages_list}
STYLE: {hint}

RESEARCH CONTEXT (use for real content — not placeholder text):
{facts_text}

CSS DESIGN SYSTEM (these CSS variables are already defined — use them):
{design_css}

REQUIREMENTS — every item is MANDATORY:
1. Valid HTML5: <!DOCTYPE html>, <html lang="en">, proper <head> with viewport meta, charset, title.
2. Google Fonts: import at least one heading font matching the design system.
3. Sticky navigation bar with logo on left, links on right. Links to: {pages_list}.
   Active link for {page_name} must have class="active".
4. Hero section (on index: full-viewport with CTA buttons; on other pages: smaller hero).
5. At least 3 content sections with real, topic-specific text (400+ words total). NO lorem ipsum.
6. Responsive grid layout using CSS Grid and Flexbox — NO external CSS frameworks.
7. Smooth hover effects on buttons, cards, nav links.
8. Footer with logo, quick links, brief description, copyright.
9. ALL CSS must be inside a <style> tag in <head>. Use the CSS variables from design system.
10. Include the base CSS reset (box-sizing, scroll-behavior, img max-width).
11. Mobile hamburger nav toggle with JavaScript.
12. Performance: no external JS libraries, no external CSS files.
13. Return ONLY the complete HTML document starting with <!DOCTYPE html>.

Write the HTML for the '{page_label}' page now:"""

    html_out = await _llm(prompt, mode="code", timeout=90)

    if _has_html_structure(html_out):
        return html_out

    logger.warning("[website_generator] LLM page generation failed for '%s' — using fallback", page_name)
    return _fallback_page(topic, page_name, pages, design_css)


# ─── Fallback page (high-quality static template) ────────────────────────────
def _fallback_page(topic: str, page_name: str, pages: List[str], design_css: str) -> str:
    label = page_name.replace("-", " ").title()
    nav_items = ""
    for p in pages:
        href = ("index" if p == "index" else p) + ".html"
        active = ' class="active"' if p == page_name else ""
        nav_items += f'<li><a href="{href}"{active}>{p.replace("-"," ").title()}</a></li>\n'

    year = datetime.now().year
    gf_link = _build_google_fonts_import(design_css)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{label} — {topic}</title>
  {gf_link}
  <style>
    {design_css}
    {_BASE_CSS}
    .hero{{
      background:linear-gradient(135deg,var(--primary) 0%,var(--secondary,#1e40af) 100%);
      color:#fff;padding:120px 0 80px;text-align:center}}
    .hero h1{{font-size:clamp(2.2rem,5vw,3.8rem);margin-bottom:20px;color:#fff}}
    .hero p{{font-size:1.2rem;opacity:.9;max-width:600px;margin:0 auto 36px}}
    .cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:28px;
      margin-top:48px}}
    .card{{background:var(--bg,#fff);border-radius:var(--radius,8px);
      padding:36px 28px;box-shadow:var(--shadow,0 4px 24px rgba(0,0,0,.08));
      transition:transform var(--transition,.22s ease)}}
    .card:hover{{transform:translateY(-6px)}}
    .card h3{{font-size:1.25rem;margin-bottom:12px;color:var(--primary)}}
    .section-title{{font-size:clamp(1.8rem,3.5vw,2.8rem);margin-bottom:16px}}
    .section-sub{{color:var(--muted,#64748b);font-size:1.1rem;max-width:520px;
      margin-bottom:48px}}
    .two-col{{display:grid;grid-template-columns:1fr 1fr;gap:60px;align-items:center}}
    @media(max-width:768px){{.two-col{{grid-template-columns:1fr}}}}
    .highlight{{background:var(--bg2,#f8fafc);border-left:4px solid var(--accent,#f59e0b);
      padding:24px 28px;border-radius:0 var(--radius,8px) var(--radius,8px) 0;
      margin:24px 0}}
  </style>
</head>
<body>
<nav class="site-nav">
  <div class="nav-inner">
    <a class="logo" href="index.html">{topic}</a>
    <button class="nav-toggle" aria-label="Menu" onclick="this.nextElementSibling.classList.toggle('open')">
      <span></span><span></span><span></span>
    </button>
    <ul>{nav_items}</ul>
  </div>
</nav>

<section class="hero">
  <div class="container">
    <h1>{label} — {topic}</h1>
    <p>Discover everything about {topic}. Quality, passion, and expertise in every detail.</p>
    <a class="btn" href="contact.html" style="margin-right:12px">Get in Touch</a>
    <a class="btn btn-outline" href="index.html" style="color:#fff;border-color:#fff">Learn More</a>
  </div>
</section>

<section>
  <div class="container">
    <h2 class="section-title">About {label}</h2>
    <p class="section-sub">Everything you need to know about our {label.lower()} at {topic}.</p>
    <div class="cards">
      <div class="card">
        <h3>Our Mission</h3>
        <p>At {topic}, we are dedicated to delivering excellence in everything we do. Our {label.lower()} page reflects our commitment to transparency, quality, and customer satisfaction.</p>
      </div>
      <div class="card">
        <h3>Why Choose Us</h3>
        <p>With years of experience in the industry, {topic} stands apart through innovation, reliable service, and a deep understanding of what our customers truly need.</p>
      </div>
      <div class="card">
        <h3>Our Promise</h3>
        <p>We believe in building long-term relationships. Every interaction with {topic} is guided by integrity, responsiveness, and a genuine desire to add value to your experience.</p>
      </div>
    </div>
  </div>
</section>

<section style="background:var(--bg2,#f8fafc)">
  <div class="container">
    <div class="two-col">
      <div>
        <h2 class="section-title">The {topic} Difference</h2>
        <p style="margin-bottom:20px">We're not just another provider in the space — {topic} was built from the ground up with a singular focus: you. Our {label.lower()} embodies the values that have guided us since day one.</p>
        <div class="highlight">
          <strong>Did you know?</strong> Customers who engage with {topic} report higher satisfaction, better outcomes, and a more personalised experience than industry averages.
        </div>
        <a class="btn" href="services.html" style="margin-top:24px">View Our Services</a>
      </div>
      <div>
        <h3 style="margin-bottom:24px">Key Highlights</h3>
        <ul style="list-style:none;display:flex;flex-direction:column;gap:16px">
          <li style="display:flex;gap:12px;align-items:flex-start">
            <span style="background:var(--accent,#f59e0b);color:#fff;border-radius:50%;width:28px;height:28px;display:flex;align-items:center;justify-content:center;flex-shrink:0;font-weight:700">1</span>
            <span>Industry-leading standards with a focus on measurable results.</span>
          </li>
          <li style="display:flex;gap:12px;align-items:flex-start">
            <span style="background:var(--accent,#f59e0b);color:#fff;border-radius:50%;width:28px;height:28px;display:flex;align-items:center;justify-content:center;flex-shrink:0;font-weight:700">2</span>
            <span>Tailored solutions designed specifically for your unique needs.</span>
          </li>
          <li style="display:flex;gap:12px;align-items:flex-start">
            <span style="background:var(--accent,#f59e0b);color:#fff;border-radius:50%;width:28px;height:28px;display:flex;align-items:center;justify-content:center;flex-shrink:0;font-weight:700">3</span>
            <span>Proven track record of success across diverse industries and clients.</span>
          </li>
          <li style="display:flex;gap:12px;align-items:flex-start">
            <span style="background:var(--accent,#f59e0b);color:#fff;border-radius:50%;width:28px;height:28px;display:flex;align-items:center;justify-content:center;flex-shrink:0;font-weight:700">4</span>
            <span>24/7 dedicated support because your success never takes a day off.</span>
          </li>
        </ul>
      </div>
    </div>
  </div>
</section>

<footer class="site-footer">
  <div class="container">
    <div class="footer-grid">
      <div>
        <h4>{topic}</h4>
        <p>Delivering excellence and innovation. Built on trust, driven by passion.</p>
      </div>
      <div>
        <h4>Pages</h4>
        <ul style="list-style:none;display:flex;flex-direction:column;gap:8px">
          {nav_items}
        </ul>
      </div>
      <div>
        <h4>Connect</h4>
        <p>hello@{re.sub(r"[^a-z0-9]", "", topic.lower())}.com</p>
        <p style="margin-top:8px">+1 (800) 000-0000</p>
      </div>
    </div>
    <div class="footer-bottom">&copy; {year} {topic}. All rights reserved. Built with JARVIS AI.</div>
  </div>
</footer>
</body>
</html>"""


# ─── Post-process: inject nav + validate ─────────────────────────────────────
def _post_process(html_out: str, topic: str, page_name: str, pages: List[str], design_css: str) -> Tuple[str, bool]:
    """
    1. Ensure it has a proper HTML structure.
    2. Inject design CSS variables if missing.
    3. Validate with html.parser.
    Returns (final_html, is_fallback).
    """
    if not _has_html_structure(html_out):
        return _fallback_page(topic, page_name, pages, design_css), True

    # Inject :root{} variables if not already present
    if ":root" not in html_out and "--primary" not in html_out:
        root_block = f"<style>{design_css}\n{_BASE_CSS}</style>"
        html_out = html_out.replace("</head>", root_block + "\n</head>", 1)

    # Ensure google fonts present
    if "fonts.googleapis.com" not in html_out:
        gf = _build_google_fonts_import(design_css)
        if gf:
            html_out = html_out.replace("</head>", f"  {gf}\n</head>", 1)

    valid, errors = _validate_html(html_out)
    if errors:
        logger.debug("[website_generator] HTML validation notes for '%s': %s", page_name, errors[:3])

    return html_out, False


# ─── Sitemap XML ──────────────────────────────────────────────────────────────
def _write_sitemap(site_dir: Path, pages: List[Dict], base_url: str) -> None:
    urlset = Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
    for pg in pages:
        url = SubElement(urlset, "url")
        loc = SubElement(url, "loc")
        loc.text = f"{base_url}/{pg['file']}"
        lastmod = SubElement(url, "lastmod")
        lastmod.text = datetime.utcnow().strftime("%Y-%m-%d")
        changefreq = SubElement(url, "changefreq")
        changefreq.text = "monthly"
    raw = tostring(urlset, encoding="unicode", xml_declaration=False)
    (site_dir / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n' + raw, encoding="utf-8"
    )


# ─── README ───────────────────────────────────────────────────────────────────
def _write_readme(site_dir: Path, topic: str, pages: List[Dict], style: str, preview_url: str) -> None:
    lines = [
        f"# {topic} — AI-Generated Website",
        "",
        f"**Generated by:** JARVIS AI Website Engine  ",
        f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        f"**Style:** {style}  ",
        f"**Preview:** {preview_url}  ",
        "",
        "## Pages",
        "",
    ]
    for pg in pages:
        status = " ⚠️ fallback" if pg.get("fallback") else ""
        lines.append(f"- `{pg['file']}` — {pg['title']} ({pg['size_bytes']:,} bytes){status}")
    lines += [
        "",
        "## Open-Source Template Inspiration",
        "",
        "The design system and layout patterns were inspired by (all MIT/BSD licensed):",
        "",
        "| Project | URL |",
        "|---------|-----|",
        "| HTML5 UP | https://github.com/ajlkn/html5up |",
        "| Start Bootstrap | https://github.com/StartBootstrap/startbootstrap-creative |",
        "| Skeleton CSS | https://github.com/dhg/Skeleton |",
        "| Pure.css | https://github.com/pure-css/pure |",
        "| Milligram | https://github.com/milligram/milligram |",
        "| Spectre.css | https://github.com/picturepan2/spectre |",
        "| Bulma (ref) | https://github.com/jgthms/bulma |",
        "| Tailwind (ref) | https://github.com/tailwindlabs/tailwindcss |",
        "",
        "> All HTML and CSS was generated by JARVIS AI — no framework CSS was loaded.",
        "",
        "## Local Development",
        "",
        "```bash",
        "# Preview",
        f"jarvis website preview {site_dir}",
        "",
        "# Or plain Python",
        f"cd {site_dir} && python -m http.server 8080",
        "```",
    ]
    (site_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")


# ─── Shared CSS file ──────────────────────────────────────────────────────────
def _write_shared_css(site_dir: Path, design_css: str) -> None:
    (site_dir / "assets").mkdir(exist_ok=True)
    full = design_css + "\n" + _BASE_CSS
    (site_dir / "assets" / "style.css").write_text(full, encoding="utf-8")


# ─── Preview server ───────────────────────────────────────────────────────────
def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def start_preview(directory: str) -> int:
    """Start an HTTP preview server for `directory`. Returns port number."""
    port = _free_port()
    handler = _make_handler(directory)
    server = HTTPServer(("127.0.0.1", port), handler)
    _preview_servers[port] = server
    _preview_dirs[port] = str(directory)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    logger.info("[website_generator] Preview server: http://localhost:%d", port)
    return port


def _make_handler(directory: str):
    class _H(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=directory, **kw)
        def log_message(self, fmt, *args):  # silence request log spam
            logger.debug("[preview] " + fmt, *args)
    return _H


def stop_preview(port: Optional[int] = None) -> Dict:
    """Stop preview server(s). Pass port to stop one, or None to stop all."""
    stopped = []
    targets = [port] if port else list(_preview_servers.keys())
    for p in targets:
        srv = _preview_servers.pop(p, None)
        if srv:
            srv.shutdown()
            stopped.append(p)
            _preview_dirs.pop(p, None)
    return {"stopped_ports": stopped}


# ─── Main pipeline ────────────────────────────────────────────────────────────
async def generate_site_async(
    topic: str,
    pages: List[str] = None,
    output_dir: str = None,
    style: str = "modern",
) -> Dict:
    """
    AI-powered multi-page website generator.

    Args:
        topic:      What the site is about  (e.g. "Coffee Shop")
        pages:      List of page names      (default: index/about/services/contact)
        output_dir: Where to write files    (default: ~/.jarvis/generated_sites/<slug>)
        style:      Visual style preset     (modern|corporate|creative|dark|elegant|tech|warm|minimal)

    Returns:
        {
          success, page_count, pages: [{file, title, size_bytes, fallback}],
          output_dir, preview_url, design_system_css
        }
    """
    start_ts = time.monotonic()
    pages = pages or ["index", "about", "services", "contact"]
    style = style if style in STYLE_HINTS else "modern"

    site_slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", topic.lower()).strip("_")[:40]
    site_dir  = Path(output_dir) if output_dir else SITES_DIR / site_slug
    site_dir.mkdir(parents=True, exist_ok=True)

    logger.info("[website_generator] ▶ Generating site: '%s' (%s) → %s", topic, style, site_dir)

    # ── Step 1: Research ──────────────────────────────────────────────────────
    logger.info("[website_generator] Step 1/5: Research")
    facts = await _research(topic)

    # ── Step 2: Design system ─────────────────────────────────────────────────
    logger.info("[website_generator] Step 2/5: Design system")
    design_css = await _design_system(topic, style, facts)

    # ── Step 3 + 4: Generate & save pages ────────────────────────────────────
    logger.info("[website_generator] Step 3+4/5: Generating %d pages", len(pages))
    generated: List[Dict] = []
    progress_per_page = 60 / max(len(pages), 1)

    for i, page_name in enumerate(pages):
        clean_name = re.sub(r"[^a-zA-Z0-9_-]", "_", page_name.lower())
        file_name  = ("index" if clean_name == "index" else clean_name) + ".html"
        title      = page_name.replace("-", " ").replace("_", " ").title()

        logger.info("  [%d/%d] Generating page: %s", i + 1, len(pages), page_name)

        try:
            raw_html = await _generate_page(topic, clean_name, pages, design_css, style, facts)
            final_html, is_fallback = _post_process(raw_html, topic, clean_name, pages, design_css)
        except Exception as exc:
            logger.exception("[website_generator] page '%s' error: %s", page_name, exc)
            final_html = _fallback_page(topic, clean_name, pages, design_css)
            is_fallback = True

        out_path = site_dir / file_name
        out_path.write_text(final_html, encoding="utf-8")

        generated.append({
            "file":       file_name,
            "title":      title,
            "size_bytes": len(final_html.encode("utf-8")),
            "fallback":   is_fallback,
            "path":       str(out_path),
        })
        logger.info("    ✓ %s (%d bytes)%s", file_name, generated[-1]["size_bytes"],
                    " [fallback]" if is_fallback else "")

    # ── Step 4 cont.: Assets, sitemap, README ─────────────────────────────────
    logger.info("[website_generator] Step 4/5: Assets & metadata")
    _write_shared_css(site_dir, design_css)

    # ── Step 5: Preview server ────────────────────────────────────────────────
    logger.info("[website_generator] Step 5/5: Starting preview server")
    port        = start_preview(str(site_dir))
    preview_url = f"http://localhost:{port}"

    _write_sitemap(site_dir, generated, preview_url)
    _write_readme(site_dir, topic, generated, style, preview_url)

    elapsed = time.monotonic() - start_ts
    result = {
        "success":           True,
        "topic":             topic,
        "style":             style,
        "page_count":        len(generated),
        "pages":             generated,
        "output_dir":        str(site_dir),
        "preview_url":       preview_url,
        "preview_port":      port,
        "design_system_css": design_css,
        "elapsed_seconds":   round(elapsed, 1),
        "open_in_browser":   f"{preview_url}/index.html",
    }
    logger.info("[website_generator] ✅ Done in %.1fs — %s", elapsed, preview_url)

    # Phase 3: Emit hook
    try:
        from brain.events import PluginEventBus
        asyncio.create_task(PluginEventBus.instance().emit(
            "on_website_generate", 
            topic=topic, 
            output_dir=str(site_dir),
            page_count=len(generated)
        ))
    except Exception as e:
        logger.warning("[tools.website_generator] generate_website_content failed: %s", e)

    return result


def generate_site(
    topic: str,
    pages: List[str] = None,
    output_dir: str = None,
    style: str = "modern",
) -> Dict:
    """Synchronous wrapper — drop-in replacement for the old generate_site()."""
    try:
        loop = asyncio.get_running_loop()
        return loop.run_until_complete(generate_site_async(topic, pages, output_dir, style))
    except RuntimeError:
        return asyncio.run(generate_site_async(topic, pages, output_dir, style))
