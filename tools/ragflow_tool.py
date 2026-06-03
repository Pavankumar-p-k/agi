"""
tools/ragflow_tool.py
RAGFlow API client — document upload, knowledge base query, citation retrieval.
Wraps the RAGFlow REST API (Apache 2.0 — infiniflow/ragflow).
"""
from __future__ import annotations
import logging
import os
from typing import List, Dict, Any, Optional
import httpx

logger = logging.getLogger("jarvis.tools.ragflow")

RAGFLOW_BASE = os.getenv("RAGFLOW_BASE_URL", "http://localhost:9380")
RAGFLOW_API_KEY = os.getenv("RAGFLOW_API_KEY", "")


async def ragflow_search(
    query: str,
    dataset_ids: Optional[List[str]] = None,
    top_k: int = 10,
) -> Dict[str, Any]:
    """
    Search RAGFlow knowledge bases.
    Returns: {answer, chunks: [{content, source, score}], citations}
    """
    if not RAGFLOW_API_KEY:
        return {"answer": "", "chunks": [], "error": "RAGFLOW_API_KEY not set"}
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{RAGFLOW_BASE}/api/v1/retrieval",
                headers={"Authorization": f"Bearer {RAGFLOW_API_KEY}"},
                json={
                    "question": query,
                    "dataset_ids": dataset_ids or [],
                    "top_k": top_k,
                    "similarity_threshold": 0.2,
                    "rerank_id": None,
                    "keyword": True,
                    "highlight": True,
                }
            )
            response.raise_for_status()
            data = response.json()
            chunks = data.get("data", {}).get("chunks", [])
            return {
                "chunks": [
                    {
                        "content": c.get("content_with_weight", c.get("content", "")),
                        "source": c.get("document_name", "unknown"),
                        "score": c.get("similarity", 0.0),
                        "document_id": c.get("doc_id", ""),
                    }
                    for c in chunks
                ],
                "total": len(chunks),
            }
    except Exception as e:
        logger.error(f"RAGFlow search failed: {e}")
        return {"chunks": [], "error": str(e)}


async def list_datasets() -> List[Dict]:
    """List all RAGFlow knowledge bases/datasets."""
    if not RAGFLOW_API_KEY:
        return []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{RAGFLOW_BASE}/api/v1/dataset",
                headers={"Authorization": f"Bearer {RAGFLOW_API_KEY}"},
            )
            r.raise_for_status()
            return r.json().get("data", [])
    except Exception as e:
        logger.error(f"RAGFlow list_datasets failed: {e}")
        return []


def format_rag_context(chunks: List[Dict]) -> str:
    """Format RAGFlow chunks as LLM context with citations."""
    if not chunks:
        return ""
    lines = ["## Document Context (from knowledge base):"]
    for i, chunk in enumerate(chunks[:5], 1):
        lines.append(f"\n[{i}] Source: {chunk['source']} (score: {chunk['score']:.2f})")
        lines.append(chunk["content"][:800])
    return "\n".join(lines)
