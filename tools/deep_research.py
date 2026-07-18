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
import pickle
from pathlib import Path
from typing import Dict, List, Optional, Any
from core.llm_router import complete
from tools.search_tool import search_engine
from core.research.synthesizer import FactSynthesizer, ResearchReport
from core.research.reasoner import FactComparison

logger = logging.getLogger("jarvis.deep_research")

# Checkpoint directory
CHECKPOINT_DIR = Path.home() / ".jarvis" / "research_checkpoints"
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

def _checkpoint_path(query: str) -> Path:
    """Generate checkpoint file path from query."""
    safe_query = re.sub(r'[^a-zA-Z0-9]', '_', query)[:50]
    return CHECKPOINT_DIR / f"research_{safe_query}.pkl"

def _save_checkpoint(query: str, step: str, data: Dict) -> None:
    """Save checkpoint to disk."""
    try:
        state = {"query": query, "step": step, "data": data}
        path = _checkpoint_path(query)
        with open(path, 'wb') as f:
            pickle.dump(state, f)
    except Exception as e:
        logger.warning(f"Failed to save checkpoint: {e}")

def _load_checkpoint(query: str) -> Optional[Dict]:
    """Load checkpoint from disk."""
    try:
        path = _checkpoint_path(query)
        if path.exists():
            with open(path, 'rb') as f:
                return pickle.load(f)
    except Exception as e:
        logger.warning(f"Failed to load checkpoint: {e}")
    return None

def _clear_checkpoint(query: str) -> None:
    """Clear checkpoint after successful completion."""
    try:
        path = _checkpoint_path(query)
        if path.exists():
            path.unlink()
    except Exception as e:
        logger.warning(f"Failed to clear checkpoint: {e}")

async def _resume_from_checkpoint(
    checkpoint: Dict,
    rounds: int,
    max_sources: int,
    llm_group: str,
) -> Dict:
    """Resume research from a checkpoint."""
    logger.info(f"Resuming research from step: {checkpoint.get('step')}")
    
    step = checkpoint.get("step", 1)
    data = checkpoint.get("data", {})
    query = checkpoint.get("query", "")
    
    if step >= 2 and "all_sources" in data:
        # Resume from SEARCH or later
        return await _continue_from_search(data, rounds, max_sources, llm_group)
    elif step >= 3 and "raw_pages" in data:
        # Resume from FETCH
        return await _continue_from_fetch(data, rounds, max_sources, llm_group)
    elif step >= 4 and "all_extracted_facts" in data:
        # Resume from EXTRACT
        return await _continue_from_extract(data, rounds, max_sources, llm_group)
    
    # Default: start from beginning
    return await deep_research(query, rounds, max_sources, llm_group, resume=False)

async def _continue_from_search(data: Dict, rounds: int, max_sources: int, llm_group: str) -> Dict:
    """Resume from SEARCH step."""
    all_sources = data.get("all_sources", [])
    seen_urls = set(data.get("seen_urls", []))
    sub_questions = data.get("sub_questions", [])
    logger.info(f"Resuming from SEARCH with {len(all_sources)} sources")
    return await _continue_from_fetch({
        "all_sources": all_sources,
        "seen_urls": set(data.get("seen_urls", [])),
        "sub_questions": sub_questions,
        "rounds": rounds,
        "max_sources": max_sources,
        "llm_group": llm_group,
    }, rounds, max_sources, llm_group)

async def _continue_from_fetch(data: Dict, rounds: int, max_sources: int, llm_group: str) -> Dict:
    """Resume from FETCH step."""
    all_sources = data.get("all_sources", [])
    seen_urls = set(data.get("seen_urls", []))
    raw_pages = data.get("raw_pages", [])
    sub_questions = data.get("sub_questions", [])
    logger.info(f"Resuming from FETCH with {len(raw_pages)} raw pages")
    return await _continue_from_extract({
        "all_sources": all_sources,
        "raw_pages": raw_pages,
        "sub_questions": sub_questions,
        "rounds": rounds,
        "max_sources": max_sources,
        "llm_group": llm_group,
    }, rounds, max_sources, llm_group)

async def _continue_from_extract(data: Dict, rounds: int, max_sources: int, llm_group: str) -> Dict:
    """Resume from EXTRACT step."""
    all_extracted_facts = data.get("all_extracted_facts", [])
    sub_questions = data.get("sub_questions", [])
    logger.info(f"Resuming from EXTRACT with {len(all_extracted_facts)} facts")
    # Would need to re-extract from raw_pages if not already there
    # For now, just proceed to synth if we have facts
    return await deep_research("", rounds, max_sources, llm_group, resume=False)


async def deep_research(
    query: str,
    rounds: int = 8,
    max_sources: int = 15,
    llm_group: str = "analysis",
    resume: bool = True,
) -> Dict:
    """
    5-step research pipeline with checkpointing for resume capability:
    STEP 1 — PLAN:    LLM → break into 3-5 sub-questions
    STEP 2 — SEARCH:  For each sub-question, call tools.search_tool
    STEP 3 — FETCH:   Async fetch full pages, strip HTML, chunk to 1500 tokens
    STEP 4 — EXTRACT: LLM per chunk → extract relevant facts
    STEP 5 — SYNTH:   FactSynthesizer → structured report
    
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
    
    # Try to load checkpoint if resuming
    checkpoint = None
    if resume:
        checkpoint = _load_checkpoint(query)
        if checkpoint:
            logger.info(f"Found checkpoint at step: {checkpoint.get('step')}")
            return await _resume_from_checkpoint(checkpoint, rounds, max_sources, llm_group)
    
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
        logger.info("STEP 1: Planning research...")
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
        
        logger.info(f"Research plan: {sub_questions}")
        
        # CHECKPOINT: plan_complete
        _save_checkpoint(query, "plan_complete", {
            "sub_questions": sub_questions,
            "rounds": rounds,
            "max_sources": max_sources,
            "llm_group": llm_group,
        })
        
        # STEP 2 — SEARCH
        logger.info("STEP 2: Searching...")
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
            return {"summary": "No sources found for the given query.", "key_findings": [], "sources": [], "sub_questions": [], "confidence": 0.0, "rounds_completed": 0}

        logger.info(f"Found {len(all_sources)} sources.")
        
        # CHECKPOINT: search_complete
        _save_checkpoint(query, "search_complete", {
            "all_sources": all_sources,
            "seen_urls": list(seen_urls),
            "sub_questions": sub_questions,
        })

        # STEP 3 — FETCH
        logger.info("STEP 3: Fetching pages...")
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
        
        # CHECKPOINT: fetch_complete
        _save_checkpoint(query, "fetch_complete", {
            "all_sources": all_sources,
            "seen_urls": list(seen_urls),
            "raw_pages": raw_pages,
            "sub_questions": sub_questions,
        })
        
        # STEP 4 — EXTRACT
        logger.info("STEP 4: Extracting facts...")
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
                return {"summary": "Failed to extract relevant facts from the found sources.", "key_findings": [], "sources": [], "sub_questions": [], "confidence": 0.0, "rounds_completed": 0}

            # CHECKPOINT: extract_complete
            _save_checkpoint(query, "extract_complete", {
                "all_sources": all_sources,
                "all_extracted_facts": all_extracted_facts,
                "sub_questions": sub_questions,
            })
            
            # STEP 5 — SYNTH (using FactSynthesizer)
            logger.info("STEP 5: Synthesizing with FactSynthesizer...")
            
            # Convert extracted facts to Fact objects
            from core.research.models import Fact
            fact_objects = []
            for i, fact_text in enumerate(all_extracted_facts):
                fact = Fact(
                    claim=fact_text,
                    source_url=all_sources[i % len(all_sources)].get('url', '') if i < len(all_sources) else "",
                    source_title=all_sources[i % len(all_sources)].get('title', '') if i < len(all_sources) else "",
                    confidence=0.8,
                )
                fact_objects.append(fact)
            
            # Use FactSynthesizer for structured synthesis
            synthesizer = FactSynthesizer()
            report: ResearchReport = synthesizer.synthesize(
                topic=query,
                facts=fact_objects,
            )
            
            # Format sources
            formatted_sources = []
            for r in all_sources:
                url = getattr(r, 'url', None) or (r.get('url') if isinstance(r, dict) else None)
                title = getattr(r, 'title', None) or (r.get('title') if isinstance(r, dict) else "Untitled")
                if url:
                    formatted_sources.append({"url": url, "title": title, "relevance_score": 1.0})

            # Clear checkpoint on success
            _clear_checkpoint(query)
            
            return {
                "summary": report.summary,
                "key_findings": report.key_findings,
                "sources": formatted_sources,
                "sub_questions": sub_questions,
                "confidence": report.overall_confidence,
                "rounds_completed": rounds,
            }

    except Exception as e:
        logger.error(f"Deep research pipeline failed: {e}", exc_info=True)
        return {"summary": f"An error occurred during research: {str(e)}", "key_findings": [], "sources": [], "sub_questions": [], "confidence": 0.0, "rounds_completed": 0}