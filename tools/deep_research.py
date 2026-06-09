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
import re
import html
import asyncio
import aiohttp
import json
import logging
from typing import Dict, List, Optional
from core.llm_router import complete
from tools.search_tool import search_engine

logger = logging.getLogger("jarvis.deep_research")

async def deep_research(
    query: str,
    rounds: int = 8,
    max_sources: int = 15,
    llm_group: str = "analysis",
) -> Dict:
    """
    5-step research pipeline:
    STEP 1 — PLAN:    LLM → break into 3-5 sub-questions
    STEP 2 — SEARCH:  For each sub-question, call tools.search_tool
    STEP 3 — FETCH:   Async fetch full pages, strip HTML, chunk to 1500 tokens
    STEP 4 — EXTRACT: LLM per chunk → extract relevant facts
    STEP 5 — SYNTH:   Final LLM call → structured report
    
    Returns: {
        summary: str,
        key_findings: List[str],
        sources: List[{url, title, relevance_score}],
        sub_questions: List[str],
        confidence: float,  # 0.0-1.0
        rounds_completed: int,
    }
    """
    logger.info(f"Starting deep research for: {query}")
    
    # Initialize result structure in case of early exit
    final_result = {
        "summary": "Research failed to complete.",
        "key_findings": [],
        "sources": [],
        "sub_questions": [],
        "confidence": 0.0,
        "rounds_completed": 0,
    }

    try:
        # STEP 1 — PLAN
        plan_prompt = (
            f"You are a research planner. Break this question into 3-5 specific, diverse sub-questions "
            f"that will help provide a comprehensive answer: {query}\n"
            "Return a simple bulleted list of questions."
        )
        res = await complete(llm_group, [
            {"role": "system", "content": "You are a research planner."},
            {"role": "user", "content": plan_prompt}
        ])
        if res.is_err():
            raise res.unwrap_err()
        plan_text = res.unwrap()
        sub_questions = []
        for line in plan_text.split('\n'):
            q_match = re.search(r"[-*•]\s*(.*)", line)
            if q_match:
                sub_questions.append(q_match.group(1).strip())
        
        if not sub_questions:
            sub_questions = [query]
        
        final_result["sub_questions"] = sub_questions
        logger.info(f"Research plan: {sub_questions}")

        # STEP 2 — SEARCH
        all_sources = []
        seen_urls = set()
        
        # We use rounds to limit how many sub-questions we actually pursue
        active_questions = sub_questions[:rounds]
        
        for sub_q in active_questions:
            if len(all_sources) >= max_sources:
                break
                
            search_res = await search_engine.search(sub_q)
            # search_tool.search returns a Result object
            if hasattr(search_res, 'is_ok') and search_res.is_ok():
                results = search_res.unwrap()
                for r in results:
                    url = getattr(r, 'url', None) or (r.get('url') if isinstance(r, dict) else None)
                    if url and url not in seen_urls:
                        all_sources.append(r)
                        seen_urls.add(url)
                        if len(all_sources) >= max_sources:
                            break
            elif isinstance(search_res, list): # fallback if it returns a list directly
                for r in search_res:
                    url = getattr(r, 'url', None) or (r.get('url') if isinstance(r, dict) else None)
                    if url and url not in seen_urls:
                        all_sources.append(r)
                        seen_urls.add(url)
                        if len(all_sources) >= max_sources:
                            break

        if not all_sources:
            logger.warning("No sources found for deep research.")
            final_result["summary"] = "No sources found for the given query."
            return final_result

        logger.info(f"Found {len(all_sources)} sources.")

        # STEP 3 — FETCH
        async def fetch_page(session, url):
            try:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        return await response.text()
            except Exception as e:
                logger.debug(f"Failed to fetch {url}: {e}")
            return ""

        raw_pages = []
        connector = aiohttp.TCPConnector(limit_per_host=2)
        async with aiohttp.ClientSession(connector=connector) as session:
            # Concurrency limit: 3 concurrent max
            for i in range(0, len(all_sources), 3):
                batch = all_sources[i:i+3]
                tasks = []
                for r in batch:
                    url = getattr(r, 'url', None) or (r.get('url') if isinstance(r, dict) else None)
                    if url:
                        tasks.append(fetch_page(session, url))
                
                if tasks:
                    raw_pages.extend(await asyncio.gather(*tasks))

        # STEP 4 — EXTRACT
        all_extracted_facts = []
        for i, html_content in enumerate(raw_pages):
            if not html_content:
                continue
                
            # Strip HTML and decode entities
            clean_text = re.sub(r'<[^>]+>', ' ', html_content)
            clean_text = html.unescape(clean_text)
            clean_text = re.sub(r'\s+', ' ', clean_text).strip()
            
            # Chunk text: split on sentences, max 1500 chars
            # Simple sentence split
            sentences = re.split(r'(?<=[.!?])\s+', clean_text)
            chunks = []
            current_chunk = ""
            for s in sentences:
                if len(current_chunk) + len(s) < 1500:
                    current_chunk += s + " "
                else:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = s + " "
            if current_chunk:
                chunks.append(current_chunk.strip())

            # Process top 3 chunks per page to save tokens/time
            for chunk in chunks[:3]:
                extract_prompt = (
                    f"From this source text, extract facts relevant to: {query}\n"
                    f"Text: {chunk}\n"
                    "Return bullet points of key facts."
                )
                res = await complete(llm_group, [{"role": "user", "content": extract_prompt}])
                if res.is_ok():
                    facts = res.unwrap()
                    if facts and "extract" not in facts.lower(): # Basic check for content
                        all_extracted_facts.append(facts)

        if not all_extracted_facts:
            logger.warning("No facts extracted from sources.")
            final_result["summary"] = "Failed to extract relevant facts from the found sources."
            return final_result

        # STEP 5 — SYNTH
        all_facts_joined = "\n".join(all_extracted_facts)
        synth_prompt = (
            "You are a research analyst. Synthesize these findings into a structured report.\n"
            f"Query: {query}\n"
            f"Findings:\n{all_facts_joined}\n\n"
            "Return JSON only: {\"summary\": \"...\", \"key_findings\": [\"...\"], \"confidence\": 0.0-1.0}"
        )
        res = await complete(llm_group, [{"role": "user", "content": synth_prompt}])
        if res.is_err():
            raise res.unwrap_err()
        synth_response = res.unwrap()
        
        # Parse synth JSON safely
        try:
            json_block = re.search(r'\{.*\}', synth_response, re.DOTALL)
            if json_block:
                synth_data = json.loads(json_block.group())
            else:
                synth_data = json.loads(synth_response)
        except Exception:
            logger.warning("Failed to parse synthesis JSON. Falling back to raw text.")
            synth_data = {
                "summary": synth_response,
                "key_findings": [],
                "confidence": 0.5
            }

        # Final successful assembly
        formatted_sources = []
        for r in all_sources:
            url = getattr(r, 'url', None) or (r.get('url') if isinstance(r, dict) else None)
            title = getattr(r, 'title', None) or (r.get('title') if isinstance(r, dict) else "Untitled")
            if url:
                formatted_sources.append({"url": url, "title": title, "relevance_score": 1.0})

        return {
            "summary": synth_data.get("summary", synth_response),
            "key_findings": synth_data.get("key_findings", []),
            "sources": formatted_sources,
            "sub_questions": sub_questions,
            "confidence": synth_data.get("confidence", 0.7),
            "rounds_completed": rounds,
        }

    except Exception as e:
        logger.error(f"Deep research pipeline failed: {e}", exc_info=True)
        final_result["summary"] = f"An error occurred during research: {str(e)}"
        return final_result
