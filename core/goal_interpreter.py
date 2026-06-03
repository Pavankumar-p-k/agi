"""core/goal_interpreter.py
Takes a vague goal string and returns a structured interpretation.
Uses LLM only — no keyword heuristic fallback.
"""
import re, json, logging
from typing import Optional

logger = logging.getLogger("goal_interpreter")

DEFAULT_PAGES = ["index", "about", "contact"]

LLM_PROMPT = """Analyze this project goal and return ONLY valid JSON with no markdown formatting.

Goal: {goal}

Return this exact schema:
{{
  "project_type": "website|webapp|api|mobile|cli|library",
  "business_type": "restaurant|bakery|coffee_shop|portfolio|blog|ecommerce|saas|real_estate|fitness|hotel|salon|spa|gym|tech_startup|law_firm|dental_clinic|music_store|book_store|general",
  "brand_name": "Creative business name based on the goal (max 3 words)",
  "pages_requested": ["index", "about", "contact", ...],
  "tech_stack": ["html", "css", "javascript", ...],
  "style": "modern_minimal|business|creative|ecommerce|blog|portfolio|saas|static",
  "tone": "professional|casual|luxury|fun|warm|minimal|bold",
  "constraints": ["responsive", "fast_load", ...]
}}

Page options: index, about, contact, menu, blog, portfolio, faq, reviews, team, login, signup, dashboard, cart, gallery, services, pricing, bookings, listings, rooms
Tech options: html, css, javascript, react, vue, nextjs, tailwind, bootstrap, fastapi, flask, node, django, static, python
Style options: modern_minimal (clean whitespace), business (professional blue/gray), creative (bold colors/animated), ecommerce (product-grid), blog (article-list), portfolio (gallery-heavy), saas (landing-first), static (simple)
Tone sets the writing style and design feel.

Choose brand_name that fits the goal — be specific and creative, not generic.
Choose pages based on what the business type actually needs. A restaurant needs menu+gallery. A portfolio needs gallery. A SaaS needs services+pricing."""


async def interpret_goal(goal: str) -> dict:
    """Parse a vague goal into a structured interpretation using LLM."""
    result = {
        "original_goal": goal,
        "project_type": "website",
        "business_type": "general",
        "brand_name": "Website",
        "pages": list(DEFAULT_PAGES),
        "tech_stack": ["html", "css"],
        "style": "modern_minimal",
        "tone": "professional",
        "success_criteria": ["all_pages_exist", "no_broken_links", "no_placeholders", "nav_consistent", "browser_loads"],
        "constraints": ["responsive"],
        "reasoning": [],
    }

    try:
        from core.llm_router import health_check, complete as llm_complete
        if not await health_check():
            logger.warning("[GOAL] LLM not available, using defaults")
            result["reasoning"].append("llm_unavailable")
            return result

        prompt = LLM_PROMPT.format(goal=goal)
        resp = (await llm_complete("analysis", [{"role": "user", "content": prompt}], timeout=30)).unwrap_or("")

        # Remove markdown code fences if present
        resp = resp.strip()
        if resp.startswith("```"):
            resp = resp.split("\n", 1)[1] if "\n" in resp else resp[3:]
            if "```" in resp:
                resp = resp.rsplit("```", 1)[0]
            resp = resp.strip()

        parsed = json.loads(resp)
        result["reasoning"].append("llm")

        if parsed.get("project_type"):
            result["project_type"] = parsed["project_type"]
        if parsed.get("business_type"):
            result["business_type"] = parsed["business_type"]
        if parsed.get("brand_name"):
            result["brand_name"] = parsed["brand_name"]
        if parsed.get("pages_requested"):
            normalized = []
            for p in parsed["pages_requested"]:
                pl = p.lower().strip()
                normalized.append("index" if pl == "home" else pl)
            result["pages"] = sorted(set(normalized))
        if parsed.get("tech_stack"):
            result["tech_stack"] = list(set(parsed["tech_stack"]))
        if parsed.get("style"):
            result["style"] = parsed["style"]
        if parsed.get("tone"):
            result["tone"] = parsed["tone"]
        if parsed.get("constraints"):
            result["constraints"] = list(set(parsed["constraints"]))

    except json.JSONDecodeError as e:
        logger.warning(f"[GOAL] LLM returned invalid JSON: {e}")
        result["reasoning"].append("llm_json_failed")
    except Exception as e:
        logger.warning(f"[GOAL] LLM interpret failed: {e}")
        result["reasoning"].append("llm_failed")

    return result
