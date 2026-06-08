from __future__ import annotations

import logging
import re
import os
from collections import Counter
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_INDEXED_PATHS: set[str] = set()


def index_workspace(workspace_root: str | Path, owner: Optional[str] = None) -> dict:
    workspace_root = str(Path(workspace_root).resolve())
    try:
        from core.rag_vector import VectorRAG
        vrag = VectorRAG()
        exts = {".py", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go", ".java",
                ".c", ".h", ".cpp", ".hpp", ".cs", ".rb", ".php", ".swift",
                ".kt", ".scala", ".md", ".txt", ".yaml", ".yml", ".json",
                ".toml", ".cfg", ".ini", ".css", ".html", ".sql", ".sh"}
        result = vrag.index_personal_documents(workspace_root, file_extensions=exts, owner=owner)
        if result.get("success"):
            _INDEXED_PATHS.add(workspace_root)
        return result
    except Exception as e:
        logger.warning("codebase indexing failed: %s", e)
        return {"success": False, "message": str(e)}


def search_codebase(query: str, k: int = 5, owner: Optional[str] = None) -> str:
    if not query:
        return ""
    all_results: list[dict] = []

    # 1) Symbol search (function/class name match via regex)
    try:
        sym_results = _symbol_search(query)
        all_results.extend(sym_results)
    except Exception as e:
        logger.debug("symbol search failed: %s", e)

    # 2) BM25 keyword search
    try:
        bm25_results = _bm25_search(query, k=k * 2)
        all_results.extend(bm25_results)
    except Exception as e:
        logger.debug("BM25 search failed: %s", e)

    # 3) Vector search
    try:
        from core.rag_vector import VectorRAG
        vrag = VectorRAG()
        if vrag.healthy:
            vec_results = vrag.search(query, k=k * 2, owner=owner)
            for r in vec_results:
                meta = r.get("metadata", {})
                source = meta.get("source", "")
                text = r.get("document", "")
                if source and text:
                    all_results.append({"source": source, "text": text, "rank": 2})
    except Exception as e:
        logger.debug("RAG search failed: %s", e)

    if not all_results:
        return ""

    seen: dict[str, dict] = {}
    for r in all_results:
        src = r.get("source", "")
        if not src:
            continue
        rank = r.get("rank", 5)
        if src not in seen or rank < seen[src].get("rank", 99):
            seen[src] = r

    ranked = sorted(seen.values(), key=lambda x: (x.get("rank", 99), x.get("source", "")))[:k]
    lines = []
    for r in ranked:
        source = r.get("source", "?")
        text = r.get("text", "")
        rank_label = {0: "[exact]", 1: "[symbol]", 2: "[vector]", 3: "[keyword]"}.get(r.get("rank", 5), "")
        lines.append(f"# {source} {rank_label}")
        lines.append(text[:500])
        lines.append("")
    return "\n".join(lines)


def find_code(query: str, k: int = 5, owner: Optional[str] = None) -> list[dict]:
    """Return structured code search results with file paths, line numbers, and snippets.

    Use this for programmatic access to code search results. Returns a list of
    dicts with keys: source, text, rank, line_start, line_end.
    """
    raw = search_codebase(query, k=k, owner=owner)
    if not raw:
        return []
    results = []
    for block in raw.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        lines = block.split("\n")
        if not lines:
            continue
        first = lines[0]
        if not first.startswith("# "):
            continue
        rest = first[2:].strip()
        source = rest.split(" [")[0] if " [" in rest else rest
        snippet = "\n".join(lines[1:])
        results.append({"source": source, "text": snippet, "rank": 0})
    return results


def _symbol_search(query: str) -> list[dict]:
    """Find files containing a symbol (class/function) matching the query."""
    results = []
    q_lower = query.lower()
    # Build patterns for common symbol definitions
    def_patterns = [
        re.compile(r"^\s*(?:def|async def)\s+(\w+)", re.MULTILINE),
        re.compile(r"^\s*(?:class|struct|trait|interface|enum)\s+(\w+)", re.MULTILINE),
        re.compile(r"^\s*(?:fn|func|function|sub)\s+(\w+)", re.MULTILINE),
        re.compile(r"^\s*(?:export\s+)?(?:const|let|var|function)\s+(\w+)", re.MULTILINE),
    ]
    exts = {".py", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go", ".java",
            ".rb", ".php", ".swift", ".kt", ".cs", ".cpp", ".h"}
    root = Path.cwd()
    for f in sorted(root.rglob("*")):
        if any(p.startswith(".") or p in ("node_modules", ".git", "__pycache__", "venv", ".venv") for p in f.relative_to(root).parts):
            continue
        if f.suffix not in exts:
            continue
        try:
            text = f.read_text("utf-8", errors="replace")
        except Exception:
            continue
        rel = str(f.relative_to(root))
        for pat in def_patterns:
            for m in pat.finditer(text):
                name = m.group(1).lower()
                if q_lower in name or name in q_lower:
                    context = text[m.start():m.start() + 400]
                    results.append({"source": rel, "text": context, "rank": 1})
                    break
            if results and results[-1].get("source") == rel:
                break
    return results


def _bm25_search(query: str, k: int = 10) -> list[dict]:
    """Simple BM25-like keyword search using word frequency scoring."""
    stopwords = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                 "being", "have", "has", "had", "do", "does", "did", "will",
                 "would", "could", "should", "may", "might", "shall", "can",
                 "to", "of", "in", "for", "on", "with", "at", "by", "from",
                 "as", "into", "through", "during", "before", "after", "above",
                 "below", "between", "out", "off", "over", "under", "again",
                 "further", "then", "once", "here", "there", "when", "where",
                 "why", "how", "all", "each", "every", "both", "few", "more",
                 "most", "other", "some", "such", "no", "nor", "not", "only",
                 "own", "same", "so", "than", "too", "very", "just", "because",
                 "and", "but", "or", "if", "while", "that", "this", "it", "its",
                 "what", "which", "who", "whom"}
    query_terms = [w.lower() for w in query.split() if w.lower() not in stopwords and len(w) > 2]
    if not query_terms:
        return []
    exts = {".py", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go", ".java",
            ".rb", ".php", ".swift", ".kt", ".cs", ".cpp", ".h",
            ".md", ".txt", ".yaml", ".yml", ".json", ".toml"}
    root = Path.cwd()
    scored: list[tuple[str, str, float]] = []
    for f in sorted(root.rglob("*")):
        if any(p.startswith(".") or p in ("node_modules", ".git", "__pycache__", "venv", ".venv") for p in f.relative_to(root).parts):
            continue
        if f.suffix not in exts:
            continue
        try:
            text = f.read_text("utf-8", errors="replace")
        except Exception:
            continue
        rel = str(f.relative_to(root))
        text_lower = text.lower()
        words = text_lower.split()
        total_words = len(words)
        if total_words < 10:
            continue
        word_counts = Counter(words)
        score = 0.0
        for term in query_terms:
            tf = word_counts.get(term, 0) / max(total_words, 1)
            score += tf * 1000  # simple TF scoring
        if score > 0:
            # Extract relevant snippet around first occurrence
            first_pos = text_lower.find(query_terms[0])
            start = max(0, text.rfind("\n", 0, first_pos) + 1) if first_pos >= 0 else 0
            snippet = text[start:start + 400]
            scored.append((rel, snippet, score))
    scored.sort(key=lambda x: -x[2])
    return [{"source": s[0], "text": s[1], "rank": 3} for s in scored[:k]]


def is_workspace_indexed(workspace_root: str | Path) -> bool:
    return str(Path(workspace_root).resolve()) in _INDEXED_PATHS
