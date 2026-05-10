"""
l2_assistant/assistant_engine.py
═══════════════════════════════════════════════════════════════════
LEVEL 2 — ASSISTANT ENGINE (Copilot / Cursor equivalent)

Extends existing jarvis_codex with:
  • Persistent codebase index (file tree + symbols + imports)
  • Multi-file context window (related files auto-included)
  • Real-time inline reasoning (improvement suggestions)
  • Developer workflow integration (git, tests, deps)

Reads from:
  • WorldState (current activity = coding?)
  • SemanticStore (past code sessions)
  • CodebaseIndex (file graph)

Outputs:
  • AssistantContext (used by L3 Executor and L1 Brain)
═══════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
import ast, hashlib, json, logging, os, re, time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jarvis.l2")

OLLAMA_URL   = os.getenv("OLLAMA_URL",   "http://localhost:11434")
CODEX_URL    = os.getenv("CODEX_URL",    "http://localhost:11435")
CODER_MODEL  = "qwen2.5-coder:3b"
REASON_MODEL = "deepseek-r1:1.5b"


# ─────────────────────────────────────────────────────────────────
#  DATA CLASSES
# ─────────────────────────────────────────────────────────────────

@dataclass
class FileSymbol:
    name:     str
    kind:     str   # function|class|method|variable|import
    file:     str
    line:     int
    signature: str = ""

@dataclass
class FileNode:
    path:     str
    language: str
    symbols:  List[FileSymbol] = field(default_factory=list)
    imports:  List[str]        = field(default_factory=list)
    size:     int              = 0
    checksum: str              = ""
    indexed_at: float          = field(default_factory=time.time)

@dataclass
class AssistantContext:
    """Structured context passed to L3 Executor and API responses."""
    primary_file:   str
    related_files:  List[str]
    relevant_code:  str          # concatenated context for LLM
    symbols:        List[FileSymbol]
    suggestions:    List[str]    # inline improvement suggestions
    file_graph:     Dict[str, List[str]]  # file → [files it imports]
    session_id:     str
    built_at:       float = field(default_factory=time.time)

    def to_prompt_context(self, max_chars: int = 8000) -> str:
        """LLM-ready context string."""
        parts = [f"# Codebase Context\n"]
        if self.primary_file:
            parts.append(f"Primary file: {self.primary_file}")
        if self.related_files:
            parts.append(f"Related files: {', '.join(self.related_files[:5])}")
        if self.relevant_code:
            code = self.relevant_code[:max_chars]
            parts.append(f"\n```\n{code}\n```")
        if self.suggestions:
            parts.append("\nPending suggestions:\n" +
                "\n".join(f"  - {s}" for s in self.suggestions[:3]))
        return "\n".join(parts)


# ─────────────────────────────────────────────────────────────────
#  CODEBASE INDEX
# ─────────────────────────────────────────────────────────────────

class CodebaseIndex:
    """
    Builds and maintains a symbol + dependency graph of the project.
    Cached in memory + JSON on disk.
    Re-indexes only changed files (checksum-based).
    """

    INDEX_FILE = Path("data/codebase_index.json")

    def __init__(self, root: str = "."):
        self.root   = Path(root).resolve()
        self._index: Dict[str, FileNode] = {}
        self._load_cache()

    # ── Index building ────────────────────────────────────────────

    def build(self, extensions: list = None, max_files: int = 500) -> int:
        """
        Walk the project and index all source files.
        Returns number of files indexed.
        """
        if extensions is None:
            extensions = [".py", ".dart", ".js", ".ts", ".java",
                          ".kt", ".go", ".rs", ".cpp", ".swift"]

        exclude_dirs = {".git", ".idea", "node_modules", "__pycache__",
                        ".dart_tool", "build", "dist", ".venv", "venv"}
        count = 0

        for fpath in self.root.rglob("*"):
            if count >= max_files:
                break
            if fpath.suffix not in extensions:
                continue
            if any(p in fpath.parts for p in exclude_dirs):
                continue
            try:
                self._index_file(fpath)
                count += 1
            except Exception as e:
                logger.debug("[L2] Index skip %s: %s", fpath.name, e)

        self._save_cache()
        logger.info("[L2] Indexed %d files | root=%s", count, self.root)
        return count

    def _index_file(self, fpath: Path) -> FileNode:
        rel   = str(fpath.relative_to(self.root))
        text  = fpath.read_text(encoding="utf-8", errors="ignore")
        csum  = hashlib.md5(text.encode()).hexdigest()

        # Return cached if unchanged
        if rel in self._index and self._index[rel].checksum == csum:
            return self._index[rel]

        lang    = self._detect_lang(fpath.suffix)
        symbols = self._extract_symbols(text, lang, rel)
        imports = self._extract_imports(text, lang)

        node = FileNode(
            path=rel, language=lang, symbols=symbols,
            imports=imports, size=len(text), checksum=csum,
        )
        self._index[rel] = node
        return node

    def _extract_symbols(self, code: str, lang: str, path: str) -> List[FileSymbol]:
        symbols = []
        if lang == "python":
            try:
                tree = ast.parse(code)
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        sig = f"def {node.name}({', '.join(a.arg for a in node.args.args)})"
                        symbols.append(FileSymbol(node.name, "function", path, node.lineno, sig))
                    elif isinstance(node, ast.ClassDef):
                        symbols.append(FileSymbol(node.name, "class", path, node.lineno, f"class {node.name}"))
            except SyntaxError:
                return []
        else:
            # Regex fallback for other languages
            patterns = {
                "dart":       (r'\b(?:class|void|Future|String|int|bool)\s+(\w+)\s*[({]', "symbol"),
                "javascript": (r'(?:function|class|const|let)\s+(\w+)', "symbol"),
                "java":       (r'(?:class|interface|enum|void|public|private)\s+(\w+)\s*[({]', "symbol"),
            }
            pat = patterns.get(lang)
            if pat:
                for m in re.finditer(pat[0], code):
                    line = code[:m.start()].count("\n") + 1
                    symbols.append(FileSymbol(m.group(1), pat[1], path, line))
        return symbols

    def _extract_imports(self, code: str, lang: str) -> List[str]:
        imports = []
        if lang == "python":
            for m in re.finditer(r'^(?:import|from)\s+([\w.]+)', code, re.M):
                imports.append(m.group(1))
        elif lang in ("javascript", "typescript"):
            for m in re.finditer(r"(?:import|require)\s*\(?['\"]([^'\"]+)['\"]", code):
                imports.append(m.group(1))
        elif lang == "dart":
            for m in re.finditer(r"import\s+'([^']+)'", code):
                imports.append(m.group(1))
        return imports[:20]

    def _detect_lang(self, ext: str) -> str:
        return {
            ".py":"python",".dart":"dart",".js":"javascript",
            ".ts":"typescript",".java":"java",".kt":"kotlin",
            ".go":"go",".rs":"rust",".cpp":"cpp",".swift":"swift",
        }.get(ext, "text")

    # ── Query ──────────────────────────────────────────────────────

    def find_related(self, target: str, max_results: int = 5) -> List[str]:
        """Find files related to target (by imports or name similarity)."""
        related = []
        target_base = Path(target).stem.lower()

        for path, node in self._index.items():
            if path == target:
                continue
            score = 0
            # Direct import
            if target in " ".join(node.imports) or target_base in " ".join(node.imports):
                score += 10
            # Name similarity
            if target_base in Path(path).stem.lower():
                score += 5
            # Symbol match
            for sym in node.symbols:
                if target_base in sym.name.lower():
                    score += 2
            if score > 0:
                related.append((score, path))

        related.sort(reverse=True)
        return [p for _, p in related[:max_results]]

    def search_symbol(self, name: str) -> List[FileSymbol]:
        """Find symbol by name across all indexed files."""
        results = []
        for node in self._index.values():
            for sym in node.symbols:
                if name.lower() in sym.name.lower():
                    results.append(sym)
        return results

    def get_file_content(self, path: str) -> str:
        try:
            return (self.root / path).read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return ""

    def stats(self) -> dict:
        total_symbols = sum(len(n.symbols) for n in self._index.values())
        return {
            "files":   len(self._index),
            "symbols": total_symbols,
            "root":    str(self.root),
        }

    # ── Cache ──────────────────────────────────────────────────────

    def _load_cache(self):
        if self.INDEX_FILE.exists():
            try:
                raw = json.loads(self.INDEX_FILE.read_text())
                for p, d in raw.items():
                    syms = [FileSymbol(**s) for s in d.get("symbols", [])]
                    self._index[p] = FileNode(
                        path=d["path"], language=d["language"],
                        symbols=syms, imports=d.get("imports", []),
                        size=d.get("size", 0), checksum=d.get("checksum", ""),
                    )
                logger.info("[L2] Index loaded from cache: %d files", len(self._index))
            except Exception as e:
                logger.warning("[L2] Cache load failed: %s", e)

    def _save_cache(self):
        self.INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
        raw = {}
        for p, n in self._index.items():
            raw[p] = {
                "path": n.path, "language": n.language,
                "symbols": [{"name":s.name,"kind":s.kind,"file":s.file,
                              "line":s.line,"signature":s.signature}
                             for s in n.symbols],
                "imports": n.imports, "size": n.size, "checksum": n.checksum,
            }
        self.INDEX_FILE.write_text(json.dumps(raw, indent=2))


# ─────────────────────────────────────────────────────────────────
#  MULTI-FILE REASONER
# ─────────────────────────────────────────────────────────────────

class MultiFileReasoner:
    """
    Builds a multi-file context window for LLM reasoning.
    Respects token budget — prioritizes most relevant code.
    """

    MAX_CONTEXT_CHARS = 12_000

    def __init__(self, index: CodebaseIndex):
        self.index = index

    def build_context(self, primary: str, intent: str = "",
                      max_chars: int = None) -> AssistantContext:
        budget = max_chars or self.MAX_CONTEXT_CHARS
        related = self.index.find_related(primary, max_results=6)

        # Build code context — primary file first
        parts         = []
        files_used    = []
        chars_used    = 0
        all_symbols   = []

        for fpath in [primary] + related:
            content = self.index.get_file_content(fpath)
            if not content:
                continue
            chunk = f"\n# {fpath}\n{content}\n"
            if chars_used + len(chunk) > budget:
                # Truncate to fit budget
                remaining = budget - chars_used
                if remaining > 200:
                    parts.append(chunk[:remaining] + "\n# [truncated]\n")
                break
            parts.append(chunk)
            files_used.append(fpath)
            chars_used += len(chunk)

            node = self.index._index.get(fpath)
            if node:
                all_symbols.extend(node.symbols)

        # File dependency graph
        graph = {}
        for fp in files_used:
            node = self.index._index.get(fp)
            graph[fp] = node.imports if node else []

        return AssistantContext(
            primary_file  = primary,
            related_files = related,
            relevant_code = "".join(parts),
            symbols       = all_symbols,
            suggestions   = [],
            file_graph    = graph,
            session_id    = hashlib.md5(primary.encode()).hexdigest()[:8],
        )


# ─────────────────────────────────────────────────────────────────
#  INLINE REASONING ENGINE
# ─────────────────────────────────────────────────────────────────

class InlineReasoningEngine:
    """
    Analyzes code for real-time improvement suggestions.
    Uses lightweight patterns — no LLM needed for basic checks.
    Falls back to JARVIS Codex server for deeper analysis.
    """

    def __init__(self, codex_url: str = CODEX_URL):
        self._codex = codex_url

    def analyze_python(self, code: str) -> List[str]:
        suggestions = []
        lines = code.splitlines()

        # Static checks
        if "except:" in code and "Exception" not in code:
            suggestions.append("Bare except clause — catch specific exceptions")
        if re.search(r'print\(', code) and "logging" not in code:
            suggestions.append("Using print() — consider logging module")
        if re.search(r'time\.sleep\(', code):
            suggestions.append("time.sleep() blocks thread — use asyncio.sleep() in async code")
        if re.search(r'global\s+\w+', code):
            suggestions.append("Global variable detected — consider class or dependency injection")
        if len([l for l in lines if len(l) > 120]) > 3:
            suggestions.append("Multiple lines >120 chars — consider breaking for readability")

        # Complexity check
        if code.count("if ") + code.count("for ") + code.count("while ") > 15:
            suggestions.append("High cyclomatic complexity — consider extracting functions")

        return suggestions[:5]

    async def deep_analyze(self, code: str, language: str) -> List[str]:
        """Uses Codex server for deeper analysis."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.post(f"{self._codex}/review", json={
                    "code": code, "language": language, "focus": "bugs"
                })
                data = r.json()
                review = data.get("review", "")
                # Extract HIGH/CRITICAL issues
                suggestions = []
                for line in review.splitlines():
                    if "[CRITICAL]" in line or "[HIGH]" in line:
                        suggestions.append(line.strip())
                return suggestions[:5]
        except Exception:
            return []


# ─────────────────────────────────────────────────────────────────
#  ASSISTANT ENGINE — main entry point
# ─────────────────────────────────────────────────────────────────

class AssistantEngine:
    """
    L2 Assistant main entry point.
    Wired into AutonomousSystem at startup.
    """

    def __init__(self, project_root: str = "."):
        self.index    = CodebaseIndex(project_root)
        self.reasoner = MultiFileReasoner(self.index)
        self.inline   = InlineReasoningEngine()
        logger.info("[L2] AssistantEngine ready | root=%s", project_root)

    def initialize(self, force_reindex: bool = False) -> dict:
        """Build/refresh codebase index."""
        count = self.index.build()
        return {"indexed": count, **self.index.stats()}

    def build_context(self, file: str, intent: str = "") -> AssistantContext:
        """Build multi-file context for a target file."""
        ctx = self.reasoner.build_context(file, intent)

        # Add inline suggestions for Python
        if file.endswith(".py"):
            code = self.index.get_file_content(file)
            ctx.suggestions = self.inline.analyze_python(code)

        logger.debug("[L2] Context for %s: %d related, %d symbols, %d suggestions",
                     file, len(ctx.related_files),
                     len(ctx.symbols), len(ctx.suggestions))
        return ctx

    async def suggest(self, file: str, code_snippet: str,
                      language: str = "python") -> List[str]:
        """Async deep suggestions via Codex server."""
        return await self.inline.deep_analyze(code_snippet, language)

    def search(self, query: str) -> dict:
        """Search symbols and files by name."""
        symbols = self.index.search_symbol(query)
        related = self.index.find_related(query)
        return {
            "symbols": [{"name":s.name,"kind":s.kind,"file":s.file,"line":s.line}
                        for s in symbols[:10]],
            "files":   related,
        }

    def stats(self) -> dict:
        return self.index.stats()
