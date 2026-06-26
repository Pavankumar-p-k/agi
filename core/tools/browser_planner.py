"""core/tools/browser_planner.py
Deterministic planning layer that augments LLM browser tool calls with rules.

Runs in two phases:
  pre_plan  — before execution (inject snapshot after navigate, intent routing)
  post_plan — after execution  (analyze results, inject fill/press/snapshot/loop-break)

State is stored externally (on AgentState.browser_planner_ctx) so the planner
remains a stateless computation — no serialisation issues across graph cycles.

Rules (v6):
  0. intent-router     — if task needs browse but LLM chose web_search, inject browser_navigate
  1. auto-snapshot     — inject browser_snapshot after every browser_navigate
  2. challenge-bypass  — detect bot-challenge pages (Amazon), click through
  3. loop-breaker      — detect repeating tool patterns, force snapshot
  4. search-fill       — detect search forms + fill with task query
  5. result-detection  — detect search results after fill+press
  6. result-click      — find first result link via evaluate, navigate + snapshot
  7. page-link-explore — explore links on non-search multi-page tasks
  8. login-detection   — detect username/password fields, report if unhandled
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

logger = logging.getLogger(__name__)

_BROWSER_TOOLS = frozenset({
    "browser_navigate", "browser_find", "browser_find_interactive",
    "browser_click", "browser_fill", "browser_press",
    "browser_snapshot", "browser_get_url", "browser_get_title",
    "browser_screenshot", "browser_current_state", "browser_health",
    "browser_get_history", "browser_get_facts", "browser_research",
    "browser_list_tabs", "browser_switch_tab",
    "browser_new_tab", "browser_close_tab",
    "browser_wait_visible", "browser_wait_text", "browser_wait_interactive",
    "browser_shadow_query", "browser_evaluate",
})

_BROWSER_INTENT_PATTERNS = [
    r"\bsearch\s+(?:for\s+|google\s+|duckduckgo\s+|bing\s+|wikipedia\s+)",
    r"\bsearch\s+(?:the\s+|this\s+)?(?:web|internet|site)",
    r"\bfind\s+(?:information|details|price|pricing|review|rating|comparison)",
    r"\b(?:look\s+up|check|get)\s+(?:price|pricing|info|details|review)",
    r"\bopen\s+(?:the\s+)?(?:link|page|result|article)",
    r"\bbrowse\s",
    r"\bgo\s+to\s",
    r"\bnavigate\s+to\s",
    r"\bvisit\s",
    r"\b(?:tutorial|article|guide|lesson)\s+on\b",
    r"\bcompare\s+(?:prices|products|options)",
]


# ── Search input discovery (multi-stage JS evaluate) ───────────

# Stage 1: Domain-specific known selectors for major sites
_SITE_SEARCH_SELECTORS = {
    "google.com": "textarea[name='q']",
    "bing.com": "textarea[name='q'], input[name='q']",
    "duckduckgo.com": "input[name='q']",
    "amazon.com": "#twotabsearchtextbox",
    "amazon.co.uk": "#twotabsearchtextbox",
    "amazon.de": "#twotabsearchtextbox",
    "youtube.com": "input#search, input[name='search_query']",
    "github.com": "input[name='q']",
    "ebay.com": "#gh-ac",
    "ebay.co.uk": "#gh-ac",
    "bestbuy.com": "input[type='search']",
    "reddit.com": "input[name='q']",
    "stackoverflow.com": "input[name='q']",
    "stackexchange.com": "input[name='q']",
    "wikipedia.org": "input[name='search']",
    "walmart.com": "input[type='search']",
    "newegg.com": "input[type='search']",
    "etsy.com": "input[name='search_query']",
    "aliexpress.com": "input[type='search']",
    "medium.com": "input[type='search']",
    "npmjs.com": "input[role='combobox']",
    "pypi.org": "input[name='q']",
    "twitter.com": "input[data-testid='SearchBox_Search_Input'], input[aria-label*='search' i]",
    "x.com": "input[data-testid='SearchBox_Search_Input'], input[aria-label*='search' i]",
}

_SITE_SELECTORS_JSON = json.dumps(_SITE_SEARCH_SELECTORS)

# Stage 2-4: Multi-pass discovery via evaluate JS (runs in browser context)
_SEARCH_DISCOVERY_JS = f"""
() => {{
    // Check if element exists in DOM (don't require offsetParent for search
    // inputs — many sites render them in containers with null offsetParent)
    function inDOM(sel) {{
        try {{
            return document.querySelector(sel) ? sel : null;
        }} catch(e) {{ return null; }}
    }}

    // Stage 1: Domain-specific known selectors (exact match first)
    const domain = (window.location.hostname || '').replace(/^www\./, '').toLowerCase();
    const domainMap = {_SITE_SELECTORS_JSON};
    const domainSel = domainMap[domain];
    if (domainSel) {{
        for (const sel of domainSel.split(',')) {{
            const r = inDOM(sel.trim());
            if (r) return r;
        }}
    }}

    // Stage 2: General CSS selectors (priority ordered by specificity)
    const generalSelectors = [
        'input[type="search"]',
        'input[placeholder*="search" i]',
        'input[placeholder*="find" i]',
        'input[placeholder*="product" i]',
        'input[placeholder*="keyword" i]',
        'input[placeholder*="query" i]',
        'textarea[placeholder*="search" i]',
        'input[name="q"]',
        'input[name="search_query"]',
        'input[name="query"]',
        'input[name="search"]',
        'input[name="keyword"]',
        'input[title*="search" i]',
        'input[aria-label*="search" i]',
        'input[aria-label*="find" i]',
        'input[role="searchbox"]',
        'input[role="combobox"]',
        'form[role="search"] input',
        'form[role="search"] textarea',
        '#search-input input',
        '#search-input textarea',
        '.search-box input',
        '.searchbox input',
        '.search input',
        '[data-testid*="search" i] input',
        '[data-testid*="search" i] textarea',
        '[class*="search-bar"] input',
        '[class*="searchBar"] input',
    ];
    for (const sel of generalSelectors) {{
        const r = inDOM(sel);
        if (r) return r;
    }}

    // Stage 3: Scan all text-type inputs for placeholders/aria/name
    const inputs = document.querySelectorAll('input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="checkbox"]):not([type="radio"]):not([type="file"]):not([type="image"]):not([type="range"])');
    const searchKeywords = ['search', 'find', 'query', 'keyword', 'product', 'item', 'lookup', 'look up', 'type here', 'ask'];
    let best = null;
    let bestScore = 0;
    for (const el of inputs) {{
        const text = (el.placeholder || el.title || el.ariaLabel || el.name || el.id || '').toLowerCase();
        let score = 0;
        for (const kw of searchKeywords) {{
            if (text.includes(kw)) {{
                score = Math.max(score, kw.length + (el.offsetWidth > 100 ? 5 : 0));
            }}
        }}
        if (score > bestScore) {{
            bestScore = score;
            best = (el.tagName.toLowerCase() === 'input' ? 'input' : 'textarea') +
                    (el.name ? '[name="' + el.name.replace(/"/g, '\\\\"') + '"]' : '') +
                    (el.id ? '#' + el.id : '');
        }}
    }}
    if (best && bestScore > 0) return best;
    // Fallback: first text input by type or role
    for (const el of inputs) {{
        if (el.offsetWidth > 50 || el.tagName.toLowerCase() === 'textarea') return 'input:not([type="hidden"]):first-of-type';
    }}

    // Stage 4: Try shadow DOM traversal
    try {{
        const hosts = document.querySelectorAll('*');
        for (const host of hosts) {{
            if (!host.shadowRoot) continue;
            const shInputs = host.shadowRoot.querySelectorAll('input[type="search"], input[placeholder*="search" i], input[name="q"]');
            for (const el of shInputs) {{
                if (el.offsetParent !== null) return 'shadow:' + (el.name ? '[name="' + el.name + '"]' : (el.placeholder || 'input'));
            }}
        }}
    }} catch(e) {{}}

    // Stage 5: Last resort — any textarea or text input
    const lastResort = document.querySelector('textarea:not([aria-hidden]), input[type="text"]:not([aria-hidden])');
    if (lastResort) return 'textarea, input[type="text"]';

    return null;
}}
"""

_RESULT_DETECT_JS = """
() => {
    const selectors = [
        '[class*="result"]', '.g', '.srg', '[data-hveid]',
        '[class*="Result"]', '#search', '.search-results',
        '[class*="search-result"]', '.main', '#main',
        'article', '[role="main"]', '.mw-parser-output',
    ];
    for (const sel of selectors) {
        const els = document.querySelectorAll(sel);
        if (els.length > 0) return String(els.length) + ':' + sel;
    }
    const body = document.body;
    const text = body ? body.innerText || '' : '';
    const hasContent = text.length > 200 && /[.!?]/.test(text);
    if (hasContent) return 'content:' + text.slice(0, 80).replace(/\\n/g, ' ');
    return null;
}
"""

_LOGIN_DETECT_JS = """
() => {
    const inputs = document.querySelectorAll('input[type="email"], input[type="password"], input[name="username"], input[name="password"], input[autocomplete="username"], input[autocomplete="current-password"], input[aria-label*="password" i], input[aria-label*="email" i], input[aria-label*="username" i]');
    if (inputs.length >= 2) {
        const types = Array.from(inputs).map(e => e.type || e.name || '?').join(',');
        return inputs.length + ':' + types;
    }
    return null;
}
"""

# ── Selector Engine (v6) ────────────────────────────────────────
# Site-specific ranked selectors for search result links.
# Ordered by reliability — first match wins, but scoring prefers
# visible, in-content, non-navigation links with descriptive text.

_SITE_RESULT_SELECTORS = {
    # Google SERP: links go through /url? redirect, not direct http hrefs
    "google.com": [
        "div.g a[href*='/url?']",
        "h3 a[href*='/url?']",
        ".yuRUbf a",
        "#search a[href*='/url?']",
        "div.g a[href*='http']",
    ],
    "bing.com": [
        ".b_algo h2 a",
        "ol#b_results .b_algo a",
        "#b_results a[href*='http']",
    ],
    "duckduckgo.com": [
        "a[data-testid='result-title-a']",
        ".result__title a",
        "article a[href*='http']",
    ],
    # Amazon: product links are a-link-normal with /dp/ paths inside result cards
    "amazon.com": [
        "a.a-link-normal.a-text-normal[href*='/dp/']",
        "[data-component-type='s-search-result'] a[href*='/dp/']",
        ".s-result-item a[href*='/dp/']",
        "a.a-link-normal[href*='/dp/']",
    ],
    "amazon.co.uk": [
        "a.a-link-normal.a-text-normal[href*='/dp/']",
        "[data-component-type='s-search-result'] a[href*='/dp/']",
        ".s-result-item a[href*='/dp/']",
    ],
    # YouTube: video titles inside ytd-video-renderer
    "youtube.com": [
        "ytd-video-renderer a#video-title[href*='/watch']",
        "h3.title-and-badge a[href*='/watch']",
        "ytd-video-renderer a.yt-simple-endpoint[href*='/watch']",
        "a#video-title[href*='/watch']",
        "ytd-video-renderer a[href*='/watch']",
        "a[href*='/watch']",
    ],
    # GitHub search results: repo links in .repo-list-item or .Box-row
    "github.com": [
        "div.search-title a[href*='/']",
        "div.Repositories-module__headerRow a[data-component='Link']",
        "a.prc-Link-Link-9ZwDx[href*='/']",
        ".Box-row a[href*='/']",
        ".Box-row a[href*='http']",
    ],
    # Reddit: post titles in various formats
    # New Reddit (shreddit): post links use /comments/ paths
    "reddit.com": [
        "a[href*='/comments/']",
        "shreddit-post a[href*='/comments/']",
        "shreddit-post a[href*='/r/']",
        "a[data-testid='post-title']",
        "article a[href*='/r/']",
        "a[href*='/r/']",
    ],
    # Stack Overflow: question links use s-link class
    "stackoverflow.com": [
        "a.s-link",
        ".js-search-results a[href*='/questions/']",
        "a[href*='/questions/']",
    ],
    "stackexchange.com": [
        "a.s-link",
        ".js-search-results a[href*='/questions/']",
    ],
    # Wikipedia: search results use mw-search-result-heading
    # External/reference links use a.external in bodyContent
    "wikipedia.org": [
        ".mw-search-result-heading a",
        ".searchResultImage a",
        ".mw-parser-output a.external",
        "#bodyContent a.external",
        "ul.mw-search-results li a",
        ".mw-search-results a[href*='http']",
    ],
    # PyPI: package links are .package-snippet or /project/ paths
    "pypi.org": [
        "a.package-snippet",
        "a[href*='/project/']",
        "li a[href*='/project/']",
    ],
    "ebay.com": [
        ".s-item a.s-item__link",
        "a[href*='/itm/']",
    ],
    "bestbuy.com": [
        "a[href*='/site/']",
        "li.sku-item a",
    ],
    "walmart.com": [
        "a[data-testid='product-title']",
        "a[href*='/ip/']",
    ],
    "newegg.com": [
        "a.item-title",
        ".item-container a[href*='/p/']",
    ],
    "etsy.com": [
        "a[data-testid='listing-card']",
        "a.listing-link",
    ],
    "twitter.com": [
        "a[href*='/status/']",
        "article a[href*='/status/']",
    ],
    "x.com": [
        "a[href*='/status/']",
        "article a[href*='/status/']",
    ],
    "npmjs.com": [
        "a[href*='/package/']",
        "a[data-testid='package-link']",
    ],
    "medium.com": [
        "article a[href*='http']",
        "a[href*='/p/']",
        "a[href*='/story/']",
    ],
    "ali-express.com": [
        "a[href*='/item/']",
        ".product-item a",
    ],
    "aliexpress.com": [
        "a[href*='/item/']",
        ".product-item a",
    ],
    "developer.mozilla.org": [
        "article a[href*='/en-US/docs/']",
        "a[href*='/en-US/docs/']",
    ],
}

_SITE_LINK_SELECTORS = {
    # Page link exploration: broader selectors for finding content links
    # on any page (articles, docs, repos, etc.)
    "github.com": [
        "article.Box-row h2 a.Link",
        "a.Box-row-link",
        "article.Box-row a.Link",
        ".Box-row a[href*='http']",
        ".repo a[href*='http']",
        "a[href*='/']:not([href*='github.com'])",
    ],
    "reddit.com": [
        "a[href*='/comments/']",
        "shreddit-post a[href*='/comments/']",
        "shreddit-post a[href*='/r/']",
        "a[data-testid='post-title']",
        "article a[href*='/r/']",
        "a[href*='/comments/']",
    ],
    "wikipedia.org": [
        ".mw-parser-output a.external",
        "#bodyContent a.external",
        ".mw-parser-output a[href*='http']:not([href*='wikipedia.org'])",
        "#bodyContent a[href*='http']:not([href*='wikipedia.org'])",
        "div#mw-content-text a[href*='http']:not([href*='wikipedia.org'])",
    ],
    "twitter.com": [
        "a[href*='/status/']",
        "article a[href*='/status/']",
    ],
    "x.com": [
        "a[href*='/status/']",
        "article a[href*='/status/']",
    ],
    "medium.com": [
        "article a[href*='http']:not([href*='medium.com'])",
        "a[href*='/p/']",
        ".section-content a[href*='http']",
    ],
    "developer.mozilla.org": [
        "article a[href*='http']:not([href*='mozilla.org'])",
        "a.heading-anchor",
        ".main-page-content a[href*='http']",
    ],
    "mozilla.org": [
        "article a[href*='http']:not([href*='mozilla.org'])",
        ".main-page-content a[href*='http']",
    ],
}

# Generic fallback selectors for any domain
_GENERIC_RESULT_SELECTORS = [
    "h3 a[href*='http']",
    "h2 a[href*='http']",
    "article a[href*='http']",
    "[class*='result'] a[href*='http']",
    "[class*='Result'] a[href*='http']",
    "[role='main'] a[href*='http']",
    "#main a[href*='http']",
    ".search-results a[href*='http']",
    ".content a[href*='http']",
    "li a[href*='http']",
    "a[href*='/dp/']",
    "a[href*='/itm/']",
    "a[href*='/product/']",
]

_GENERIC_LINK_SELECTORS = [
    "article a[href*='http']",
    "[role='main'] a[href*='http']",
    "#main a[href*='http']",
    ".content a[href*='http']",
    "h2 a[href*='http']",
    "h3 a[href*='http']",
    "h1 a[href*='http']",
    "p a[href*='http']",
    "li a[href*='http']",
    "a[href*='/p/']",
    "a[href*='/comments/']",
    "a[href*='/questions/']",
]

# JS scoring function.  Evaluates all matching links, scores by
# visibility, content context, and descriptor text.  Returns the
# best URL or null.
_SCORE_FN = """
function scoreLink(el) {
    const href = el.href || el.getAttribute('href') || '';
    if (!href || href.startsWith('#') || href.includes('javascript:') || href.includes('google.com/sorry')) return 0;
    let score = 0;
    // Visibility: visible elements are real content
    if (el.offsetParent !== null) score += 20;
    // Text content: longer = more descriptive
    const text = (el.textContent || '').trim();
    if (text.length > 3) score += 5;
    if (text.length > 15) score += 5;
    if (text.length > 30) score += 3;
    // In main content area
    const main = el.closest('#main, [role="main"], article, .content, main, .container, .wrapper');
    if (main) score += 15;
    // NOT in nav/footer/header
    let p = el.parentElement;
    let inNav = false;
    while (p) {
        const t = p.tagName.toLowerCase();
        if (['nav','footer','header','aside'].includes(t)) { inNav = true; break; }
        if (p.getAttribute('role') === 'navigation') { inNav = true; break; }
        p = p.parentElement;
    }
    if (!inNav) score += 10;
    // NOT in ad/ sponsored container
    p = el.parentElement;
    let inAd = false;
    while (p) {
        const c = (p.className || '') + ' ' + (p.id || '');
        if (/ad|sponsored|promo|banner|sidebar/i.test(c)) { inAd = true; break; }
        p = p.parentElement;
    }
    if (!inAd) score += 5;
    // Is heading-descended (search result pattern)
    if (el.closest('h1,h2,h3,h4,h5,h6')) score += 10;
    return score;
}

function findBestUrl(selectors) {
    let bestUrl = null;
    let bestScore = 0;
    for (const sel of selectors) {
        const els = document.querySelectorAll(sel);
        for (const el of els) {
            const s = scoreLink(el);
            if (s > bestScore) {
                bestScore = s;
                bestUrl = el.href || el.getAttribute('href') || '';
            }
        }
    }
    return bestUrl;
}
"""


def _build_selector_js(mode: str = "result") -> str:
    """Build JS evaluate snippet for finding links.

    Args:
        mode: "result" for search result links, "link" for page links.

    Returns:
        A JS string that returns the best matching URL or null.
    """
    if mode == "result":
        site_selectors = _SITE_RESULT_SELECTORS
        generic = _GENERIC_RESULT_SELECTORS
    else:
        site_selectors = _SITE_LINK_SELECTORS
        generic = _GENERIC_LINK_SELECTORS

    site_selectors_json = json.dumps({k: v for k, v in site_selectors.items()})
    generic_json = json.dumps(generic)

    return f"""
() => {{
    const siteSelectors = {site_selectors_json};
    const genericSelectors = {generic_json};
    {_SCORE_FN}

    const domain = (window.location.hostname || '').replace(/^www\./, '').toLowerCase();
    // Try site-specific selectors first
    const siteSels = siteSelectors[domain] || siteSelectors[domain.replace(/\..+$/, '')];
    if (siteSels) {{
        const url = findBestUrl(siteSels);
        if (url) return url;
    }}
    // Fallback to generic selectors
    return findBestUrl(genericSelectors);
}}
"""


# ── Query extraction ───────────────────────────────────────────

# ── Browser Intent Router ────────────────────────────────────

def needs_browser(prompt: str) -> bool:
    """Check if the task requires web browser interaction.
    Returns True if the prompt indicates the agent needs to browse/search the web.
    """
    prompt_lower = prompt.lower()
    return any(re.search(p, prompt_lower) for p in _BROWSER_INTENT_PATTERNS)


def _resolve_browser_target(prompt: str) -> str:
    """Determine the navigation URL based on task prompt.
    Returns a search engine URL or specific site URL.
    """
    prompt_lower = prompt.lower()
    # Direct site mention
    site_map = {
        "amazon": "https://www.amazon.com",
        "reddit": "https://www.reddit.com",
        "youtube": "https://www.youtube.com",
        "github": "https://github.com",
        "wikipedia": "https://www.wikipedia.org",
        "google": "https://www.google.com",
        "duckduckgo": "https://duckduckgo.com",
        "hacker news": "https://news.ycombinator.com",
        "fastapi": "https://fastapi.tiangolo.com",
    }
    for name, url in site_map.items():
        if name in prompt_lower:
            return url
    # Extract query for search engine
    query = extract_query(prompt)
    if query and any(w in prompt_lower for w in ["search", "find", "look up"]):
        return f"https://duckduckgo.com/?q={query.replace(' ', '+')}"
    return "https://duckduckgo.com"


def _llm_chose_browser_tool(tool_blocks: list[Any]) -> bool:
    """Check if LLM already selected any browser tool."""
    for tb in tool_blocks:
        name = getattr(tb, "tool_type", None) or (tb.get("name") if isinstance(tb, dict) else None)
        if name in _BROWSER_TOOLS:
            return True
    return False


def needs_result_click(prompt: str) -> bool:
    """Check if task prompt explicitly requires clicking/opening a search result.
    Prevents the result-click rule from firing on single-page search tasks."""
    prompt_lower = prompt.lower()
    patterns = [
        r'open the first',
        r'open the linked',
        r'open (its|the) (page|result|answer|link|post)',
        r'click (first|on\s+the|the)',
        r'find a reference link',
        r'open top post',
        r'open a related link',
        r'navigate to the result',
    ]
    return any(re.search(p, prompt_lower) for p in patterns)


def extract_query(prompt: str) -> str | None:
    """Extract search query from task prompt — quoted text first, then keywords.

    Handles patterns:
      'quoted query', "quoted query"
      Search X for Y  → Y
      Search for Y    → Y
      Find Y          → Y
      Browse X for Y  → Y
      Open X tutorial on Y  → Y
      Tutorial on Y   → Y
      search [a] question   → full prompt
    """
    for ch in ("'", '"'):
        m = re.search(rf'{ch}([^{ch}]+){ch}', prompt)
        if m:
            return m.group(1)
    # "search X for Y" — X is a single-word site name, Y is the query
    m = re.search(r'search\s+(\w+)\s+for\s+(\S.+)', prompt, re.I)
    if m:
        return m.group(2).strip().rstrip(".,;!")
    # "search for Y"
    m = re.search(r'search\s+for\s+(\S.+)', prompt, re.I)
    if m:
        return m.group(1).strip().rstrip(".,;!")
    # "search Y" (Y not preceded by "for")
    m = re.search(r'search\s+(?:a\s+|the\s+)?(question|solution|answer|topic)\b', prompt, re.I)
    if m:
        return prompt  # generic search — use full prompt
    m = re.search(r'search\s+(\S.+)', prompt, re.I)
    if m:
        return m.group(1).strip().rstrip(".,;!")
    # "find Y"
    m = re.search(r'find\s+(\S.+)', prompt, re.I)
    if m:
        return m.group(1).strip().rstrip(".,;!")
    # "Browse X for Y" — X can be multi-word ("Best Buy")
    m = re.search(r'browse\s+(.+?)\s+for\s+(\S.+)', prompt, re.I)
    if m:
        return m.group(2).strip().rstrip(".,;!")
    # "Open X tutorial on Y"
    m = re.search(r'(?:tutorial|article|guide|lesson)\s+on\s+(\S.+)', prompt, re.I)
    if m:
        return m.group(1).strip().rstrip(".,;!")
    # "Extract the price of Y on X" → Y
    m = re.search(r'(?:price|details|info|version|release)\s+(?:of|for|about)\s+(.+?)\s+(?:on|from|in)\s+\S', prompt, re.I)
    if m:
        return m.group(1).strip().rstrip(".,;!")
    m = re.search(r'(?:price|details|info|version|release)\s+(?:of|for|about)\s+(\S.+)', prompt, re.I)
    if m:
        return m.group(1).strip().rstrip(".,;!")
    # "Look up Y" / "Check Y"
    m = re.search(r'(?:look\s+up|check|get)\s+(\S.+)', prompt, re.I)
    if m:
        return m.group(1).strip().rstrip(".,;!")
    return None


# ── Loop detection ─────────────────────────────────────────────

def detect_loop(history: list[str], threshold: int = 3) -> bool:
    """Check if the last N tool names form a repeating pattern >= threshold times."""
    if len(history) < threshold * 2:
        return False
    for pattern_len in range(1, 4):
        pattern = history[-pattern_len:]
        if len(pattern) * threshold > len(history):
            continue
        repeated = True
        for i in range(threshold):
            start = -(i + 1) * pattern_len
            end = -i * pattern_len if i > 0 else None
            expected = history[start:end] if end else history[start:]
            if expected != pattern:
                repeated = False
                break
        if repeated:
            return True
    return False


# ── FSM Integration Helpers ────────────────────────────────────

def _save_fsm_to_ctx(fsm: Any, fsm_data: dict) -> None:
    """Serialize FSM state to ctx dict for graph roundtrip."""
    fsm_data["state"] = fsm.state.value
    fsm_data["actions_in_state"] = fsm.actions_in_state
    fsm_data["total_actions"] = fsm.total_actions
    fsm_data["forced_transitions"] = fsm.forced_transitions
    fsm_data["loops_prevented"] = fsm.loops_prevented
    fsm_data["page_recognitions"] = fsm.page_recognitions
    fsm_data["timeouts"] = fsm.timeouts
    fsm_data["recoveries"] = fsm.recoveries
    fsm_data["consecutive_same_tool"] = fsm.consecutive_same_tool
    fsm_data["last_tool"] = fsm.last_tool
    fsm_data["visited_urls"] = fsm.visited_urls
    fsm_data["transitions"] = fsm.transitions


def _fsm_force_advance(fsm: Any, executed_results: list[dict], ctx: dict) -> Any:
    """Force advance the FSM when a loop is detected.
    Picks the next logical state based on current state and context.
    """
    from core.tools._constants import ToolBlock
    from core.tools.browser_fsm import BrowserState

    query = ctx.get("query", "")
    has_query = bool(query and len(query) > 3)

    # State-specific forced transitions
    state_map = {
        BrowserState.START: BrowserState.NAVIGATE,
        BrowserState.NAVIGATE: BrowserState.SEARCH_PAGE if has_query else BrowserState.ARTICLE,
        BrowserState.SEARCH_PAGE: BrowserState.SEARCH_RESULTS,
        BrowserState.SEARCH_RESULTS: BrowserState.ARTICLE,
        BrowserState.ARTICLE: BrowserState.EXTRACT,
        BrowserState.EXTRACT: BrowserState.COMPLETE,
        BrowserState.FORM: BrowserState.COMPLETE,
        BrowserState.LOGIN: BrowserState.FAIL,
    }
    target = state_map.get(fsm.state, BrowserState.COMPLETE)
    fsm.transition_to(target, forced=True)
    return target


def _fsm_state_entry_inject(fsm: Any, ctx: dict) -> list[Any]:
    """Inject appropriate tool blocks when entering a new state."""
    from core.tools._constants import ToolBlock
    from core.tools.browser_fsm import BrowserState

    blocks = []
    query = ctx.get("query", "")

    if fsm.state == BrowserState.NAVIGATE:
        pass  # navigation already happened, snapshot will follow
    elif fsm.state == BrowserState.SEARCH_PAGE and query:
        # Inject search probe
        _FAST_SEARCH_JS = """
() => {
    const selectors = [
        'input[type="search"]', 'input[name="q"]', 'input[placeholder*="search" i]',
        'textarea[name="q"]', 'input[name="search_query"]', 'input[name="query"]',
        'input[name="search"]', 'input[aria-label*="search" i]', 'input[role="searchbox"]',
        'input[role="combobox"]', 'textarea[placeholder*="search" i]', 'input[type="text"]',
    ];
    for (const sel of selectors) { const el = document.querySelector(sel); if (el && el.offsetParent !== null) return sel; }
    for (const sel of selectors) { const el = document.querySelector(sel); if (el) return sel; }
    return null;
}"""
        blocks.append(ToolBlock("browser_evaluate", _FAST_SEARCH_JS))
    elif fsm.state == BrowserState.SEARCH_RESULTS:
        blocks.append(ToolBlock("browser_snapshot", ""))
    elif fsm.state == BrowserState.ARTICLE:
        blocks.append(ToolBlock("browser_snapshot", ""))
    elif fsm.state == BrowserState.LOGIN:
        ctx["login_reported"] = True
        blocks.append(ToolBlock("browser_snapshot", ""))

    return blocks


def _fsm_handle_state(
    fsm: Any,
    executed_results: list[dict],
    executed_blocks: list[Any],
    ctx: dict,
) -> list[Any] | None:
    """Handle FSM state-specific logic — unconditionally injects required tools per state.
    The FSM owns execution within each state; the LLM only provides parameters.
    """
    from core.tools._constants import ToolBlock
    from core.tools.browser_fsm import BrowserState, _extract_snapshot_text, _extract_snapshot_dict

    query = ctx.get("query", "")
    decisions = ctx.setdefault("decisions", [])

    # ── SEARCH_PAGE: fill search form and press Enter ──────────
    if fsm.state == BrowserState.SEARCH_PAGE and query:
        # Check if fill+press were already injected this round
        already_filled = any(
            getattr(b, "tool_type", None) == "browser_fill" or (isinstance(b, dict) and b.get("name") == "browser_fill")
            for b in executed_blocks
        )
        if already_filled:
            return None  # Already injected, wait for next cycle

        selector = BrowserPlanner._extract_search_selector(executed_results)
        if selector:
            decisions.append({
                "rule": "fsm_fill_press",
                "time": time.time(),
                "detail": f"filling '{query}' in '{selector}'",
            })
            ctx["pending_search"] = True
            return [
                ToolBlock("browser_fill", f"{selector}\n{query}"),
                ToolBlock("browser_press", f"{selector}\nEnter"),
            ]
        # No selector yet — inject evaluate probe
        _FAST_SEARCH_JS = """
() => {
    const selectors = [
        'input[type="search"]', 'input[name="q"]', 'input[placeholder*="search" i]',
        'textarea[name="q"]', 'input[name="search_query"]', 'input[name="query"]',
        'input[name="search"]', 'input[aria-label*="search" i]', 'input[role="searchbox"]',
        'input[role="combobox"]', 'textarea[placeholder*="search" i]', 'input[type="text"]',
    ];
    for (const sel of selectors) { const el = document.querySelector(sel); if (el && el.offsetParent !== null) return sel; }
    for (const sel of selectors) { const el = document.querySelector(sel); if (el) return sel; }
    return null;
}"""
        decisions.append({
            "rule": "fsm_search_probe",
            "time": time.time(),
            "detail": f"probing for search selector in state {fsm.state.value}",
        })
        return [ToolBlock("browser_evaluate", _FAST_SEARCH_JS)]

    # ── SEARCH_RESULTS: click first result link, then snapshot ─
    if fsm.state == BrowserState.SEARCH_RESULTS:
        # Check ctx flag (set by _handle_search_result_click when navigate succeeds)
        # Do NOT scan executed_blocks — that would match router-injected navigates
        if ctx.get("result_navigated", False):
            ctx["result_navigated"] = True
            return None  # Navigation done, wait for snapshot/extraction next cycle

        # Not navigated yet — find and click first result
        blocks, _ = BrowserPlanner._handle_search_result_click(executed_results, executed_blocks, ctx)
        return blocks

    # ── ARTICLE: snapshot for extraction ──────────────────────
    if fsm.state == BrowserState.ARTICLE:
        already_snapshotted = any(
            getattr(b, "tool_type", None) == "browser_snapshot" or (isinstance(b, dict) and b.get("name") == "browser_snapshot")
            for b in executed_blocks
        )
        if already_snapshotted:
            return None
        decisions.append({
            "rule": "fsm_article_snapshot",
            "time": time.time(),
            "detail": "snapshotting article for extraction",
        })
        return [ToolBlock("browser_snapshot", "")]

    # ── LOGIN: report and snapshot ────────────────────────────
    if fsm.state == BrowserState.LOGIN and not ctx.get("login_reported"):
        ctx["login_reported"] = True
        decisions.append({
            "rule": "fsm_login_detected",
            "time": time.time(),
            "detail": "login form detected",
        })
        return [ToolBlock("browser_snapshot", "")]

    # ── Fallback: result detection after search ────────────────
    if ctx.get("pending_search"):
        result = BrowserPlanner._handle_result_detection(executed_results, executed_blocks, ctx)
        if result:
            blocks, _ = result
            return blocks

    return None


# ── Planner ────────────────────────────────────────────────────

class BrowserPlanner:
    """Stateless deterministic browser planner.

    All state lives in the ``ctx`` dict (stored on AgentState.browser_planner_ctx).
    Methods return ``(modified_tool_blocks_or_extra, updated_ctx)``.
    """

    # ── Context lifecycle ───────────────────────────────────

    @staticmethod
    def init(task_prompt: str) -> dict:
        return {
            "query": extract_query(task_prompt),
            "task_prompt": task_prompt,
            "history": [],
            "decisions": [],
            "pending_search": False,
            "initialized": True,
            "login_reported": False,
            "search_attempts": 0,
            "probe_count": 0,
            "wait_scheduled": False,
            # v4 — task memory for multi-page navigation
            "needs_result_click": needs_result_click(task_prompt),
            "result_detected": False,
            "result_probed": False,
            "result_navigated": False,
            "link_exploration_active": False,
            "link_exploration_done": False,
            "visited_urls": [],
            "searches": [],
            "facts": [],
        }

    # ── Pre-plan (before execution) ─────────────────────────

    @staticmethod
    def pre_plan(tool_blocks: list[Any], ctx: dict) -> tuple[list[Any], dict]:
        """Inject browser_navigate if task requires browsing but LLM chose wrong tool (Rule 0).
        Also injects browser_snapshot after every browser_navigate (Rule 1)."""
        from core.tools._constants import ToolBlock

        task_prompt = ctx.get("task_prompt", "")
        needs_browse = needs_browser(task_prompt)
        llm_chose_browser = _llm_chose_browser_tool(tool_blocks)

        # Check FSM state — don't re-navigate if already past START
        fsm_state = ctx.get("fsm", {}).get("state", "START")
        already_navigated = fsm_state not in ("START", "NAVIGATE")

        planned = []
        # Rule 0: Intent Router — if task needs browsing but LLM didn't pick a browser tool,
        # inject browser_navigate only if we haven't already navigated (FSM past START)
        if needs_browse and not llm_chose_browser and not already_navigated:
            url = _resolve_browser_target(task_prompt)
            planned.append(ToolBlock("browser_navigate", url))
            ctx.setdefault("decisions", []).append({
                "rule": "intent_router",
                "time": time.time(),
                "detail": f"LLM chose non-browser tools for browsing task → injected navigate to {url}",
            })

        # Add LLM's chosen blocks
        for tb in tool_blocks:
            planned.append(tb)

        # Rule 1: Auto-snapshot after EVERY browser_navigate in the planned list
        # (handles both router-injected and LLM-chosen navigates)
        final = []
        for tb in planned:
            final.append(tb)
            name = getattr(tb, "tool_type", None) or (tb.get("name") if isinstance(tb, dict) else None)
            if name == "browser_navigate":
                final.append(ToolBlock("browser_snapshot", ""))
                ctx.setdefault("decisions", []).append({
                    "rule": "auto_snapshot",
                    "time": time.time(),
                    "detail": "injected snapshot after browser_navigate",
                })
        return final, ctx

    # ── Post-plan (after execution) — FSM-driven ──────────────

    @staticmethod
    def post_plan(
        executed_results: list[dict],
        executed_blocks: list[Any],
        ctx: dict,
    ) -> tuple[list[Any], dict]:
        """Analyze execution results and inject new tool blocks.

        Uses the Browser Execution State Machine (browser_fsm.py) for
        deterministic state transitions. The FSM replaces the old rule chain.
        """
        from core.tools._constants import ToolBlock
        from core.tools.browser_fsm import BrowserFSM, BrowserState, recognize_page, _extract_snapshot_dict

        extra: list[Any] = []
        decisions = ctx.setdefault("decisions", [])
        history = ctx.setdefault("history", [])

        # ── Build FSM from ctx (always done) ──────────────────
        fsm_data = ctx.setdefault("fsm", {})
        fsm = BrowserFSM()
        fsm.state = BrowserState(fsm_data.get("state", "START"))
        fsm.actions_in_state = fsm_data.get("actions_in_state", 0)
        fsm.total_actions = fsm_data.get("total_actions", 0)
        fsm.forced_transitions = fsm_data.get("forced_transitions", 0)
        fsm.loops_prevented = fsm_data.get("loops_prevented", 0)
        fsm.page_recognitions = fsm_data.get("page_recognitions", 0)
        fsm.timeouts = fsm_data.get("timeouts", 0)
        fsm.recoveries = fsm_data.get("recoveries", 0)
        fsm.consecutive_same_tool = fsm_data.get("consecutive_same_tool", 0)
        fsm.last_tool = fsm_data.get("last_tool", "")
        fsm.visited_urls = fsm_data.get("visited_urls", [])
        fsm.transitions = fsm_data.get("transitions", [])
        fsm_data.setdefault("_initialized", True)

        # ── Record new tools since last post_plan call ───────
        # Track already-recorded count to avoid double-counting
        # across post_plan loop iterations.
        recorded_count = ctx.setdefault("_fsm_recorded_count", 0)
        for i in range(recorded_count, len(executed_blocks)):
            block = executed_blocks[i]
            name = getattr(block, "tool_type", None) or (block.get("name") if isinstance(block, dict) else None)
            if name:
                history.append({"name": name, "time": time.time()})
                result = executed_results[i].get("result", {}) if i < len(executed_results) and isinstance(executed_results[i], dict) else {}
                fsm.record_action(name, result)
        ctx["_fsm_recorded_count"] = len(executed_blocks)

        # ── Snapshot processing → page recognition ────────────
        # Must run BEFORE timeout/loop checks so recognized pages
        # transition to correct state (e.g. NAVIGATE→SEARCH_PAGE)
        snapshot = _extract_snapshot_dict(executed_results)
        if snapshot:
            url = snapshot.get("url", "") or ""
            recognized = recognize_page(snapshot, url)
            if recognized != fsm.state and recognized not in (BrowserState.NAVIGATE, BrowserState.START):
                decisions.append({
                    "rule": "fsm_page_recognition",
                    "time": time.time(),
                    "detail": f"recognized {recognized.value} from state {fsm.state.value}",
                })
                fsm.transition_to(recognized)
                # On entering new state, inject appropriate next tool
                injected = _fsm_state_entry_inject(fsm, ctx)
                extra.extend(injected)
                _save_fsm_to_ctx(fsm, fsm_data)
                return extra, ctx

        # ── FSM checks (priority order) ───────────────────────

        # 1. Loop detection: same tool 3+ consecutive → forced transition
        if fsm.check_loop():
            decisions.append({
                "rule": "fsm_loop_breaker",
                "time": time.time(),
                "detail": f"same tool {fsm.last_tool} called {fsm.consecutive_same_tool}x in state {fsm.state.value}",
            })
            new_state = _fsm_force_advance(fsm, executed_results, ctx)
            if new_state == BrowserState.FAIL:
                extra.append(ToolBlock("browser_snapshot", ""))
            _save_fsm_to_ctx(fsm, fsm_data)
            return extra, ctx

        # 2. Timeout check: max actions exceeded → forced transition
        if fsm.check_timeout():
            decisions.append({
                "rule": "fsm_timeout",
                "time": time.time(),
                "detail": f"state {fsm.state.value} exceeded {fsm.actions_in_state} actions",
            })
            fsm.handle_timeout()
            _save_fsm_to_ctx(fsm, fsm_data)
            return extra, ctx

        # 3. Challenge bypass (independent of state)
        if not ctx.get("challenge_bypassed"):
            bypass = BrowserPlanner._handle_challenge_bypass(executed_results, executed_blocks, ctx)
            if bypass:
                _save_fsm_to_ctx(fsm, fsm_data)
                return bypass

        # 4. State-specific logic
        injected = _fsm_handle_state(fsm, executed_results, executed_blocks, ctx)
        if injected is not None:
            extra.extend(injected)
            _save_fsm_to_ctx(fsm, fsm_data)
            return extra, ctx

        # 6. Fact extraction from snapshots
        snapshot_facts = BrowserPlanner._extract_snapshot_facts(executed_results, ctx)
        if snapshot_facts:
            ctx["facts"] = ctx.get("facts", []) + snapshot_facts
            decisions.append({
                "rule": "fact_extraction",
                "time": time.time(),
                "detail": f"extracted {len(snapshot_facts)} facts from page",
            })

        _save_fsm_to_ctx(fsm, fsm_data)
        return extra, ctx

    # ── Rule helpers ─────────────────────────────────────────

    @staticmethod
    def _handle_result_detection(
        executed_results: list[dict],
        executed_blocks: list[Any],
        ctx: dict,
    ) -> tuple[list[Any], dict]:
        """After search fill+press, detect if results loaded."""
        from core.tools._constants import ToolBlock
        ctx["pending_search"] = False
        ctx["search_attempts"] = 2
        ctx["probe_count"] = 3

        # Check URL changes — look in result metadata
        for r in executed_results:
            url = BrowserPlanner._safe_get(r, "url", "")
            if not url:
                url = BrowserPlanner._safe_get(r, "result", {})
                if isinstance(url, dict):
                    url = url.get("url", "")
            if isinstance(url, str) and ("?" in url or "search" in url.lower()):
                ctx["result_detected"] = True
                ctx.setdefault("decisions", []).append({
                    "rule": "result_detection",
                    "time": time.time(),
                    "detail": f"URL changed: {url[:120]}",
                })
                return [ToolBlock("browser_snapshot", "")], ctx

        # Inject snapshot anyway
        ctx["result_detected"] = True
        ctx.setdefault("decisions", []).append({
            "rule": "result_detection",
            "time": time.time(),
            "detail": "snapshotting after search",
        })
        return [ToolBlock("browser_snapshot", "")], ctx

    @staticmethod
    def _handle_challenge_bypass(
        executed_results: list[dict],
        executed_blocks: list[Any],
        ctx: dict,
    ) -> tuple[list[Any], dict] | None:
        """Rule 3: Detect bot-challenge pages and click through.

        Amazon and other sites serve a first-visit challenge page with
        a "Continue shopping" / "Submit" button. This rule detects the
        challenge text in the snapshot DOM and injects a click to bypass it.
        """
        from core.tools._constants import ToolBlock

        # Extract the last snapshot's body text
        text = BrowserPlanner._find_snapshot_text(executed_results)
        if not text:
            return None

        text_lower = text.lower()

        # Known challenge patterns
        challenge_patterns = [
            "click the button below to continue shopping",
            "continue shopping",
        ]
        is_challenge = any(p in text_lower for p in challenge_patterns)
        if not is_challenge:
            return None

        ctx["challenge_bypassed"] = True
        ctx.setdefault("decisions", []).append({
            "rule": "challenge_bypass",
            "time": time.time(),
            "detail": "bot challenge detected, clicking through",
        })

        # JS evaluate to find and click the challenge bypass button.
        # Handles Amazon's challenge (input[type=submit] + form action)
        # and generic challenge forms.
        click_js = """
() => {
    // Try submit input
    const btn = document.querySelector('input[type=submit]');
    if (btn) { btn.click(); return true; }
    // Try any form and submit it
    const form = document.querySelector('form');
    if (form) { form.submit(); return true; }
    // Try submit button by text
    const buttons = document.querySelectorAll('button');
    for (const b of buttons) {
        if (b.textContent.toLowerCase().includes('continue')) {
            b.click(); return true;
        }
    }
    // Try link by text
    const links = document.querySelectorAll('a');
    for (const l of links) {
        if (l.textContent.toLowerCase().includes('continue')) {
            window.location.href = l.href; return true;
        }
    }
    return false;
}
"""
        return [ToolBlock("browser_evaluate", click_js)], ctx

    @staticmethod
    def _handle_search_result_click(
        executed_results: list[dict],
        executed_blocks: list[Any],
        ctx: dict,
    ) -> tuple[list[Any], dict]:
        """Two-phase search result click (Rule 5).

        Phase 1 (result_probed=False): Inject evaluate to find first result href.
        Phase 2 (result_probed=True):  Evaluate returned a URL — inject
            navigate + snapshot to open the result page.
        If no result link found, gracefully skips.
        """
        from core.tools._constants import ToolBlock

        # Phase 2: The evaluate was already executed — check its result
        if ctx.get("result_probed"):
            for r in executed_results:
                block_type = str(r.get("block_type", "")) or str(r.get("tool", ""))
                if "browser_evaluate" not in block_type:
                    continue
                inner = r.get("result", {})
                if isinstance(inner, dict):
                    val = inner.get("result", "")
                    if isinstance(val, str) and val.startswith("http"):
                        if val in ctx.get("visited_urls", []):
                            ctx["result_navigated"] = True
                            return [], ctx
                        ctx.setdefault("visited_urls", []).append(val)
                        ctx["result_navigated"] = True
                        ctx.setdefault("decisions", []).append({
                            "rule": "search_result_click",
                            "time": time.time(),
                            "detail": f"navigating to search result: {val[:120]}",
                        })
                        return [
                            ToolBlock("browser_navigate", val),
                            ToolBlock("browser_snapshot", ""),
                        ], ctx
            # No result URL found — give up gracefully
            ctx["result_navigated"] = True
            return [], ctx

        # Phase 1: Probe for a result link
        ctx["result_probed"] = True
        ctx.setdefault("decisions", []).append({
            "rule": "search_result_click",
            "time": time.time(),
            "detail": "probing for first search result link",
        })
        return [ToolBlock("browser_evaluate", _build_selector_js("result"))], ctx

    @staticmethod
    def _handle_page_link_exploration(
        executed_results: list[dict],
        executed_blocks: list[Any],
        ctx: dict,
    ) -> tuple[list[Any], dict]:
        """Two-phase page link exploration (Rule 6).

        Independent of the search pipeline. Fires on any page with external
        links for multi-page tasks. Phase 1 evaluates JS to find the first
        relevant outbound link. Phase 2 navigates to it + snapshot.

        Phase 1 (link_exploration_active=False): Inject evaluate to find href.
        Phase 2 (link_exploration_active=True):  Evaluate returned a URL —
            navigate + snapshot.
        """
        from core.tools._constants import ToolBlock

        if ctx.get("link_exploration_active"):
            for r in executed_results:
                block_type = str(r.get("block_type", "")) or str(r.get("tool", ""))
                if "browser_evaluate" not in block_type:
                    continue
                inner = r.get("result", {})
                if isinstance(inner, dict):
                    val = inner.get("result", "")
                    if isinstance(val, str) and val.startswith("http"):
                        if val in ctx.get("visited_urls", []):
                            ctx["link_exploration_done"] = True
                            ctx["link_exploration_active"] = False
                            return [], ctx
                        ctx.setdefault("visited_urls", []).append(val)
                        ctx["link_exploration_active"] = False
                        ctx["link_exploration_done"] = True
                        ctx.setdefault("decisions", []).append({
                            "rule": "page_link_exploration",
                            "time": time.time(),
                            "detail": f"navigating to page link: {val[:120]}",
                        })
                        return [
                            ToolBlock("browser_navigate", val),
                            ToolBlock("browser_snapshot", ""),
                        ], ctx
            ctx["link_exploration_done"] = True
            ctx["link_exploration_active"] = False
            return [], ctx

        ctx["link_exploration_active"] = True
        ctx.setdefault("decisions", []).append({
            "rule": "page_link_exploration",
            "time": time.time(),
            "detail": "probing for outbound links on page",
        })
        return [ToolBlock("browser_evaluate", _build_selector_js("link"))], ctx

    @staticmethod
    def _safe_get(d: dict, key: str, default: Any = "") -> Any:
        """Safely get a value from a dict, handling non-dict values."""
        if isinstance(d, dict):
            return d.get(key, default)
        return default

    @staticmethod
    def _find_snapshot_text(executed_results: list[dict]) -> str | None:
        """Extract DOM snapshot text from executed tool results.

        Handles the structured snapshot format:
          {'title': '...', 'url': '...', 'buttons': [...], 'inputs': [...],
           'links': [...], 'forms': [...], 'headings': [...], ...}
        """
        for r in executed_results:
            inner = BrowserPlanner._safe_get(r, "result", {})
            if isinstance(inner, dict):
                # Structured snapshot format
                parts = []
                t = inner.get("title", "") or ""
                if t:
                    parts.append(t)
                for h in inner.get("headings", []):
                    if isinstance(h, dict):
                        txt = h.get("text", "") or ""
                        if txt:
                            parts.append(f"[{h.get('tag','h').upper()}] {txt}")
                for inp in inner.get("inputs", []):
                    if isinstance(inp, dict):
                        ph = inp.get("placeholder", "") or ""
                        nm = inp.get("name", "") or ""
                        lbl = inp.get("label", "") or ""
                        at = inp.get("aria_label", "") or ""
                        desc = ph or nm or lbl or at
                        if desc:
                            parts.append(f"[input] {desc}")
                for f in inner.get("forms", []):
                    if isinstance(f, dict):
                        action = f.get("action", "") or ""
                        method = f.get("method", "") or ""
                        parts.append(f"[form] action={action} method={method}")
                for b in inner.get("buttons", []):
                    if isinstance(b, dict):
                        txt = b.get("text", "") or ""
                        if txt:
                            parts.append(f"[button] {txt}")
                for l in inner.get("links", []):
                    if isinstance(l, dict):
                        txt = l.get("text", "") or ""
                        if txt:
                            parts.append(f"[link] {txt}")
                for m in inner.get("modals", []):
                    if isinstance(m, dict):
                        txt = m.get("text", "") or ""
                        if txt:
                            parts.append(f"[modal] {txt}")
                combined = " | ".join(parts)
                if len(combined) > 50:
                    return combined

            # Plain string result
            for k in ("result", "output", "content"):
                v = BrowserPlanner._safe_get(r, k, "")
                if isinstance(v, str) and len(v) > 50:
                    return v
        return None

    @staticmethod
    def _has_search_form(snapshot_text: str) -> bool:
        """Check if snapshot text likely contains a search form."""
        indicators = [
            "search", "input", "textbox", "find", "look up",
            "type here", "ask anything", "what are you looking for",
        ]
        lower = snapshot_text.lower()
        return any(ind in lower for ind in indicators)

    @staticmethod
    def _extract_search_selector(executed_results: list[dict]) -> str | None:
        """Extract search input selector from a browser_evaluate result.
        Only returns valid CSS selectors — filters out null, 'null', and
        non-selector evaluate results like wait timers."""
        skip_values = {"null", "null\n", "waited", "filled_and_submitted"}
        for r in executed_results:
            block_type = str(BrowserPlanner._safe_get(r, "block_type", ""))
            if not block_type:
                block_type = str(BrowserPlanner._safe_get(r, "tool", ""))
            if "browser_evaluate" not in block_type:
                continue
            val = BrowserPlanner._safe_get(r, "output", "")
            if not val:
                inner = BrowserPlanner._safe_get(r, "result", {})
                val = (
                    BrowserPlanner._safe_get(inner if isinstance(inner, dict) else r, "output", "")
                    or BrowserPlanner._safe_get(inner if isinstance(inner, dict) else r, "result", "")
                )
            if isinstance(val, str):
                cleaned = val.strip()
                if cleaned and cleaned not in skip_values:
                    return cleaned
        return None

    @staticmethod
    def _extract_snapshot_facts(executed_results: list[dict], ctx: dict) -> list[dict]:
        """Extract structured facts from browser_snapshot results (Rule 9).

        Skips already-extracted URLs to avoid re-processing the same page.
        Returns serialized fact dicts for storage in ctx["facts"].
        """
        extracted_urls: set = ctx.setdefault("_extracted_fact_urls", set())
        for r in executed_results:
            tool = BrowserPlanner._safe_get(r, "tool", "") or ""
            if "browser_snapshot" not in tool:
                continue
            inner = BrowserPlanner._safe_get(r, "result", {})
            if not isinstance(inner, dict):
                continue
            url = inner.get("url", "") or ""
            if not url or url in extracted_urls:
                continue
            snapshot = {**inner}
            snapshot.pop("_artifacts", None)
            snapshot.pop("_facts", None)
            if not any(k in snapshot for k in ("headings", "paragraphs", "tables", "list_items", "definition_lists")):
                extracted_urls.add(url)
                continue
            try:
                from core.fact_extraction.extractor import BrowserFactExtractor
                extractor = BrowserFactExtractor()
                facts = extractor.extract_from_snapshot(snapshot, url, max_facts=20)
                extracted_urls.add(url)
                if facts:
                    serialized = extractor.to_json_serializable(facts)
                    try:
                        from core.fact_extraction.store import BrowserFactStore
                        store = BrowserFactStore()
                        store.store_facts(facts)
                    except Exception:
                        pass
                    return serialized
            except ImportError:
                break
            except Exception:
                pass
        return []

    @staticmethod
    def _detect_login_form(executed_results: list[dict]) -> str | None:
        """Detect login form from snapshot text or evaluate results."""
        for r in executed_results:
            val = BrowserPlanner._safe_get(r, "output", "")
            if not val:
                inner = BrowserPlanner._safe_get(r, "result", {})
                val = (
                    BrowserPlanner._safe_get(inner if isinstance(inner, dict) else r, "output", "")
                    or BrowserPlanner._safe_get(inner if isinstance(inner, dict) else r, "result", "")
                )
            if isinstance(val, str) and val.strip() and val.strip() != "null":
                parts = val.strip().split(":")
                if len(parts) == 2 and parts[0].isdigit() and int(parts[0]) >= 2:
                    return parts[1]
        snapshot = BrowserPlanner._find_snapshot_text(executed_results)
        if snapshot:
            pw_keywords = ["password", "sign in", "log in", "username", "email"]
            if any(kw in snapshot.lower() for kw in pw_keywords):
                return "keyword_match"
        return None
