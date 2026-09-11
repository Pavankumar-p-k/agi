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
from __future__ import annotations

import asyncio
import json
import logging
from typing import List, Dict, Any, Optional

from core.result import Ok, Err, Result
from core.errors import ProviderError

from tools.search_tool import search_engine, SearchResult
from tools.search_fallback import search as unified_search, search_with_content
from tools.crawl4ai_tool import get_crawler
from tools.ragflow_tool import ragflow_search, format_rag_context

logger = logging.getLogger("jarvis.research.retriever")


class RetrievalStrategy(Enum):
    """Strategies for retrieving information."""
    WEB_SEARCH = "web_search"
    SEARXNG = "searxng"
    DDGS = "ddgs"
    RAGFLOW = "ragflow"
    FILESYSTEM = "filesystem"
    CRAWL4AI = "crawl4ai"
    COMBINED = "combined"


class Retriever:
    """Research retriever - gathers evidence from various sources."""
    
    def __init__(self, strategy: RetrievalStrategy = RetrievalStrategy.COMBINED):
        self.strategy = strategy
        self.crawl4ai_tool = get_crawler()
        self.research_in_progress: Dict[str, bool] = {}
    
    async def research(self, query: str, max_sources: int = 15, 
                       max rounds: int = 8, use_ragflow: bool = False,
                       rag_dataset_ids: Optional[List[str]] = None) -> Result[Dict[str, Any], ProviderError]:
        """Perform research on a query, returning gathered evidence."""
        
        # Initialize result structure
        result = {
            "query": query,
            "sources": [],
            "all_extracted_facts": [],
            "sub_questions": [],
            "raw_pages": [],
            "search_strategy": self.strategy.value,
            "rounds_completed": 0,
            "confidence": 0.0,
        }
        
        try:
            # Step 1: Generate sub-questions (simple planner)
            sub_questions = await self._generate_sub_questions(query)
            result["sub_questions"] = sub_questions
            
            if not sub_questions:
                sub_questions = [query]
            
            # Step 2: Search for sources
            all_sources = await self._search_sources(sub_questions, max_sources)
            result["sources"] = all_sources
            
            # Step 3: Fetch page content
            raw_pages = await self._fetch_pages(all_sources)
            result["raw_pages"] = raw_pages
            
            # Step 4: Extract facts from pages
            extracted_facts = await self._extract_facts(raw_pages, sub_questions)
            result["all_extracted_facts"] = extracted_facts
            
            result["rounds_completed"] = rounds
            result["confidence"] = self._compute_confidence(extracted_facts, all_sources)
            
            return Ok(result)
            
        except Exception as e:
            logger.error(f"Research retrieval failed: {e}", exc_info=True)
            return Err(ProviderError(f"Research retrieval failed: {e}"))
    
    async def _generate_sub_questions(self, query: str) -> List[str]:
        """Break query into sub-questions using LLM."""
        try:
            from core.llm_core import complete_text
            prompt = (
                f"Break this research question into 3-5 specific, diverse sub-questions "
                f"that will help provide a comprehensive answer:\n{query}\n"
                "Return a simple bulleted list of questions."
            )
            res = await complete_text(prompt, model="ollama/qwen2.5-coder:3b")
            if res.is_err():
                return []
            
            text = res.unwrap()
            sub_questions = []
            for line in text.split('\n'):
                q_match = __import__('re').search(r"[-*•]\s*(.*)", line)
                if q_match:
                    sub_questions.append(q_match.group(1).strip())
            
            return sub_questions if sub_questions else [query]
        except Exception as e:
            logger.warning(f"Sub-question generation failed: {e}")
            return [query]
    
    async def _search_sources(self, sub_questions: List[str], max_sources: int) -> List[Dict]:
        """Search for sources using the selected strategy."""
        all_sources = []
        seen_urls = set()
        
        # Determine how many sub-questions to pursue based on rounds
        active_questions = sub_questions[:3]  # Pursue top 3 sub-questions
        
        for sub_q in active_questions:
            if len(all_sources) >= max_sources:
                break
            
            # Try different search methods based on strategy
            if self.strategy in (RetrievalStrategy.WEB_SEARCH, RetrievalStrategy.COMBINED):
                search_res = await unified_search(sub_q, max_results=10)
                if search_res.is_ok():
                    results = search_res.unwrap()
                    for r in results:
                        url = r.get('url', '')
                        if url and url not in seen_urls:
                            all_sources.append(r)
                            seen_urls.add(url)
            
            if self.strategy in (RetrievalStrategy.RAGFLOW, RetrievalStrategy.COMBINED) and rag_dataset_ids:
                try:
                    rag_res = await ragflow_search(sub_q, dataset_ids=rag_dataset_ids, top_k=10)
                    if rag_res.get("chunks"):
                        for c in rag_res["chunks"]:
                            url = c.get("source", "")
                            if url and url not in seen_urls:
                                all_sources.append({
                                    "url": url,
                                    "title": c.get("source", "RAGFlow"),
                                    "content": c.get("content", ""),
                                    "snippet": c.get("content", "")[:200],
                                })
                                seen_urls.add(url)
                except Exception as e:
                    logger.warning(f"RAGFlow search failed: {e}")
            
            if self.strategy in (RetrievalStrategy.CRAWL4AI, RetrievalStrategy.COMBINED):
                try:
                    # Search then crawl
                    search_res = await unified_search(sub_q, max_results=5)
                    if search_res.is_ok():
                        results = search_res.unwrap()
                        urls = [r.get('url', '') for r in results[:3] if r.get('url')]
                        if urls:
                            crawled = await self.crawl4ai_tool.scrape_multi(urls)
                            for i, r in enumerate(results[:3]):
                                if i < len(crawled) and crawled[i].get("success"):
                                    crawled_data = crawled[i]
                                    url = r.get('url', '')
                                    if url and url not in seen_urls:
                                        all_sources.append({
                                            "url": url,
                                            "title": crawled_data.get("title", r.get('title', '')),
                                            "content": crawled_data.get("content", ""),
                                            "snippet": crawled_data.get("content", "")[:200],
                                        })
                                        seen_urls.add(url)
                except Exception as e:
                    logger.warning(f"Crawl4AI search failed: {e}")
            
            # Fallback: DDGS/DuckDuckGo
            if len(all_sources) < max_sources and self.strategy in (RetrievalStrategy.SEARXNG, RetrievalStrategy.COMBINED):
                try:
                    ddgs_res = await unified_search(sub_q, max_results=5)
                    if ddgs_res.is_ok():
                        results = ddgs_res.unwrap()
                        for r in results[:5]:
                            url = r.get('url', '')
                            if url and url not in seen_urls:
                                all_sources.append(r)
                                seen_urls.add(url)
                except Exception:
                    pass
        
        # Deduplicate and sort
        unique_sources = []
        for s in all_sources:
            url = s.get('url', '')
            if url and url not in seen_urls:
                unique_sources.append(s)
                seen_urls.add(url)
        
        # Sort by relevance (simple: longer content = potentially more relevant)
        unique_sources.sort(key=lambda x: len(x.get('content', '')), reverse=True)
        
        return unique_sources[:max_sources]
    
    async def _fetch_pages(self, sources: List[Dict]) -> List[str]:
        """Fetch full page content for sources."""
        raw_pages = []
        
        # Concurrency-limited fetching
        connector = asyncio.Semaphore(3)
        
        async def fetch_one(url: str) -> str:
            async with connector:
                try:
                    # Use trafilatura for content extraction
                    import trafilatura
                    downloaded = trafilatura.fetch_url(url)
                    if downloaded:
                        return trafilatura.extract(downloaded)
                    # Fallback: httpx + simple extract
                    import httpx
                    async with httpx.AsyncClient(timeout=15) as client:
                        resp = await client.get(url, headers={
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                        })
                        if resp.status_code == 200:
                            text = resp.text
                            # Simple HTML strip
                            import re
                            text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
                            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
                            text = re.sub(r'<[^>]+>', ' ', text)
                            text = re.sub(r'\s+', ' ', text).strip()
                            return text[:3000]
                except Exception as e:
                    logger.debug(f"Failed to fetch {url}: {e}")
                return ""
        
        tasks = [fetch_one(s.get('url', '')) for s in sources if s.get('url')]
        if tasks:
            results = await asyncio.gather(*tasks)
            raw_pages = [r for r in results if r]
        
        return raw_pages
    
    async def _extract_facts(self, raw_pages: List[str], sub_questions: List[str]) -> List[str]:
        """Extract facts from raw page content using LLM."""
        from core.llm_core import complete_text
        
        all_facts = []
        
        for i, page_content in enumerate(raw_pages[:10]):  # Limit to top 10 pages
            if not page_content or len(page_content) < 50:
                continue
            
            # Process top 2 chunks per page to avoid token limits
            chunks = self._chunk_text(page_content)
            
            for chunk in chunks[:2]:
                # Extract facts relevant to sub-questions
                q_str = " | ".join(sub_questions[:3]) if sub_questions else "general research"
                prompt = (
                    f"From this text, extract factual information relevant to: {q_str}\n"
                    f"Text: {chunk[:2000]}\n"
                    "Return bullet points of key facts. If no relevant facts, say 'NO_FACTS'."
                )
                
                try:
                    res = await complete_text(prompt, model="ollama/qwen2.5-coder:3b")
                    if res.is_err():
                        continue
                    text = res.unwrap()
                    if text and "NO_FACTS" not in text.upper():
                        # Parse bullet points
                        for line in text.split('\n'):
                            line = line.strip().strip('-•* ')
                            if line and len(line) > 10:
                                all_facts.append(line)
                except Exception as e:
                    logger.debug(f"Fact extraction failed for chunk: {e}")
        
        return all_facts[:50]  # Limit total facts
    
    def _chunk_text(self, text: str, max_chars: int = 1500) -> List[str]:
        """Split text into chunks at sentence boundaries."""
        import re
        
        # Split on sentences
        sentences = re.split(r'(?<=[.!?])\s+', text)
        chunks = []
        current_chunk = ""
        
        for s in sentences:
            if len(current_chunk) + len(s) + 1 <= max_chars:
                current_chunk += s + " "
            else:
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                current_chunk = s + " "
        
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def _compute_confidence(self, extracted_facts: List[str], sources: List[Dict]) -> float:
        """Compute overall confidence in the research results."""
        if not extracted_facts:
            return 0.0
        if not sources:
            return 0.5
        
        # Base confidence from number of facts and sources
        fact_score = min(1.0, len(extracted_facts) / 10.0)
        source_score = min(1.0, len(sources) / 5.0)
        
        # Combine
        confidence = (fact_score * 0.6) + (source_score * 0.4)
        return round(confidence, 2)


# Singleton
retriever = Retriever()