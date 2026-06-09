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

"""core/content_writer.py
Generates context-specific website content using LLM.
One-shot per section, cached by (business_type, section).
"""
import logging
from typing import Optional

logger = logging.getLogger("content_writer")

_content_cache: dict[tuple[str, str], str] = {}

SECTION_PROMPTS = {
    "hero_headline": (
        "Write a short hero headline (max 8 words) for a {tone} {business_type} website called {brand_name}. "
        "Return only the headline text, no quotes or punctuation."
    ),
    "hero_subtitle": (
        "Write one sentence (max 15 words) describing the unique value of {brand_name}, a {tone} {business_type}. "
        "Return only the sentence."
    ),
    "about_text": (
        "Write a short 'About Us' paragraph (3-4 sentences) for {brand_name}, a {tone} {business_type}. "
        "Include founding story and mission. Return only the paragraph."
    ),
    "feature_cards": (
        "Write 3 feature cards for {brand_name}, a {tone} {business_type}. "
        "Return as JSON array: [{{\"title\": str, \"description\": str, \"icon\": \"fa-star\"}}] "
        "Use Font Awesome 6 icon names (fa-*). Make each card specific to {business_type}."
    ),
    "team_members": (
        "Write 3 team members for {brand_name}, a {tone} {business_type}. "
        "Return as JSON array: [{{\"name\": str, \"role\": str, \"bio\": str}}]. "
        "Make roles specific to {business_type} (e.g., Head Chef for restaurant, Lead Designer for portfolio)."
    ),
    "testimonial": (
        "Write one customer testimonial for {brand_name}, a {tone} {business_type}. "
        "Return as JSON: {{\"quote\": str, \"author\": str, \"role\": str}}. "
        "Make it sound authentic and specific to {business_type}."
    ),
    "cta_text": (
        "Write a call-to-action headline (max 6 words) and subtext (max 12 words) for {brand_name}, "
        "a {tone} {business_type}. Return as JSON: {{\"headline\": str, \"subtext\": str}}."
    ),
}


async def generate_section(business_type: str, section: str, tone: str = "professional",
                           brand_name: str = "Website") -> str:
    """Generate content for a specific page section using LLM."""
    cache_key = (business_type, section)
    if cache_key in _content_cache:
        return _content_cache[cache_key]

    prompt_template = SECTION_PROMPTS.get(section)
    if not prompt_template:
        logger.warning(f"[CONTENT] Unknown section: {section}")
        logger.warning("[CONTENT] generate_section returning None for unknown section")
        return None

    prompt = prompt_template.format(
        business_type=business_type.replace("_", " ").title(),
        tone=tone,
        brand_name=brand_name,
    )

    try:
        from core.llm_router import complete as llm_complete
        resp = (await llm_complete("analysis", [{"role": "user", "content": prompt}], timeout=20)).unwrap_or("")
        resp = resp.strip()
        # Strip markdown code fences if present
        if resp.startswith("```"):
            resp = resp.split("\n", 1)[1] if "\n" in resp else resp[3:]
            if "```" in resp:
                resp = resp.rsplit("```", 1)[0]
            resp = resp.strip()
        _content_cache[cache_key] = resp
        return resp
    except Exception as e:
        logger.warning(f"[CONTENT] LLM failed for {section}: {e}")
        logger.warning("[CONTENT] generate_section returning None after LLM failure")
        return None


async def generate_sections(business_type: str, tone: str = "professional",
                            brand_name: str = "Website") -> dict:
    """Generate all content sections in parallel."""
    sections = list(SECTION_PROMPTS.keys())
    import asyncio
    results = await asyncio.gather(*[
        generate_section(business_type, s, tone, brand_name)
        for s in sections
    ], return_exceptions=True)
    return dict(zip(sections, results))
