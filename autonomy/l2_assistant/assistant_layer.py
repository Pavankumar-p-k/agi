"""
l2_assistant/assistant_layer.py
═══════════════════════════════════════════════════════════════════
LEVEL 2 — ASSISTANT LAYER  (Copilot / Cursor equivalent)

WRAPS (does not replace):
  jarvis_codex/python/codex_server.py  → 10 coding endpoints
  jarvis_brain/gpu/pool.py             → ModelPool

ADDS:
  • CodebaseIndexer — scans project, builds symbol graph
  • InlineReasoner  — multi-file context before every code call
  • AssistantLayer  — façade wiring indexer + reasoner
"""
from __future__ import annotations
import ast, hashlib, json, logging, os, re, time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("jarvis.l2_assistant")

EXT_LANG = {
    ".py": "python", ".dart": "dart", ".js": "javascript",
    ".ts": "typescript", ".java": "java", ".kt": "kotlin",
    ".go": "go", ".rs": "rust", ".cpp": "cpp", ".c": "c",
    ".swift": "swift", ".sql": "sql", ".sh": "bash",
}
IGNORE_DIRS = {".git", "__pycache__", "node_modules", ".dart_tool",
               "build", ".gradle", "venv", ".venv", "dist", "out"}

MODELS = {
    "complete":  "qwen2.5-coder:3b",
    "explain":   "deepseek-r1:1.5b",
    "review":    "qwen3:4b",
    "fix":       "qwen2.5-coder:3b",
    "refactor":  "qwen2.5-coder:3b",
    "test":      "qwen2.5-coder:3b",
    "docs":      "qwen3:4b",
}


@dataclass
class FileNode:
    path:         str
    language:     str
    size:         int
    checksum:     str
    symbols:      list = field(default_factory=list)
    imports:      list = field(default_factory=list)
    last_indexed: float = 0.0


@dataclass
class AssistantResult:
    action:      str
    content:     str
    confidence:  float
    files_used:  list
    latency_ms:  int
    model_used:  str = "qwen2.5-coder:3b"


class CodebaseIndexer:
    """
    Scans project directory → symbol graph.
    Enables multi-file context for code actions.
    """

    def __init__(self, max_files: int = 500):
        self._index:   dict[str, FileNode] = {}
        self._max      = max_files

    def scan(self, root: str) -> dict[str, FileNode]:
        root_path = Path(root)
        count = 0
        for p in root_path.rglob("*"):
            if count >= self._max:
                break
            if any(ign in p.parts for ign in IGNORE_DIRS):
                continue
            if not p.is_file():
                continue
            lang = EXT_LANG.get(p.suffix.lower())
            if not lang:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
                self._index[str(p)] = FileNode(
                    path         = str(p),
                    language     = lang,
                    size         = len(text),
                    checksum     = hashlib.md5(text.encode()).hexdigest()[:8],
                    symbols      = self._symbols(text, lang),
                    imports      = self._imports(text, lang),
                    last_indexed = time.time(),
                )
                count += 1
            except Exception as err:
                import logging
                logging.getLogger(__name__).error("Exception swallowed: %s", err)
                raise RuntimeError(f"Exception swallowed: {err}")
        logger.info("[L2] Indexed %d files in %s", count, root)
        return self._index

    def related(self, file_path: str, top_k: int = 4) -> list[FileNode]:
        """Files most related to current — by shared imports/symbols/dir."""
        if file_path not in self._index:
            return []
        cur = self._index[file_path]
        cur_dir = os.path.dirname(file_path)
        scores: dict[str, int] = {}
        for path, node in self._index.items():
            if path == file_path:
                continue
            score = 0
            if os.path.dirname(path) == cur_dir:
                score += 3
            score += len(set(cur.imports) & set(node.imports)) * 2
            score += len(set(cur.symbols) & set(node.symbols))
            if score > 0:
                scores[path] = score
        ranked = sorted(scores, key=lambda p: scores[p], reverse=True)
        return [self._index[p] for p in ranked[:top_k]]

    def context_window(self, file_path: str,
                       max_chars: int = 6000) -> str:
        related = self.related(file_path)
        parts = []
        used  = 0
        for node in related:
            try:
                text = Path(node.path).read_text(
                    encoding="utf-8", errors="ignore")
                snippet = (
                    f"# {node.path} ({node.language})\n"
                    f"# Symbols: {', '.join(node.symbols[:8])}\n"
                    f"{text[:1800]}\n\n"
                )
                if used + len(snippet) > max_chars:
                    break
                parts.append(snippet)
                used += len(snippet)
            except Exception as err:
                import logging
                logging.getLogger(__name__).error("Exception swallowed: %s", err)
                raise RuntimeError(f"Exception swallowed: {err}")
        return "\n".join(parts)

    def _symbols(self, text: str, lang: str) -> list[str]:
        symbols = []
        if lang == "python":
            try:
                tree = ast.parse(text)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef,
                                         ast.AsyncFunctionDef,
                                         ast.ClassDef)):
                        symbols.append(node.name)
                return symbols[:40]
            except Exception as err:
                return []
        for line in text.splitlines():
            m = re.match(
                r"^\s*(def|class|function|fn|func|async\s+def)\s+(\w+)",
                line)
            if m:
                symbols.append(m.group(2))
        return symbols[:40]

    def _imports(self, text: str, lang: str) -> list[str]:
        imports = []
        if lang == "python":
            for line in text.splitlines():
                m = re.match(r"^(?:import|from)\s+([\w.]+)", line)
                if m:
                    imports.append(m.group(1))
        elif lang in ("javascript", "typescript", "dart"):
            for line in text.splitlines():
                m = re.match(r"^import\s+.*?['\"](.+?)['\"]", line)
                if m:
                    imports.append(m.group(1))
        elif lang == "java":
            for line in text.splitlines():
                m = re.match(r"^import\s+([\w.]+);", line)
                if m:
                    imports.append(m.group(1))
        return imports[:25]


class AssistantLayer:
    """
    L2 façade — wires CodebaseIndexer with Codex server + ModelPool fallback.
    """

    def __init__(self, pool, project_root: str = ".",
                 codex_url: str = "http://localhost:11435"):
        self._pool     = pool
        self._indexer  = CodebaseIndexer()
        self._root     = project_root
        self._codex    = codex_url
        self._index    = {}
        logger.info("[L2] AssistantLayer initialized (root=%s)", project_root)

    def scan(self, root: str = None):
        self._root  = root or self._root
        self._index = self._indexer.scan(self._root)

    async def handle(self, action: str, code: str, language: str,
                     current_file: str = "",
                     extra: dict = None) -> AssistantResult:
        t0     = time.time()
        extra  = extra or {}

        # Build multi-file context
        ctx       = ""
        files_used = []
        if current_file and current_file in self._index:
            ctx        = self._indexer.context_window(current_file)
            files_used = [n.path for n in
                          self._indexer.related(current_file)]

        # Try Codex server (already built)
        try:
            import httpx
            payload = {"code": code, "language": language, **extra}
            if ctx:
                payload["context"] = ctx[:2000]
            async with httpx.AsyncClient(timeout=120) as c:
                r = await c.post(f"{self._codex}/{action}",
                                  json=payload)
                r.raise_for_status()
                data = r.json()
                key  = {"complete": "completion", "explain": "explanation",
                        "review": "review", "fix": "fixed_code",
                        "refactor": "refactored", "test": "tests",
                        "docs": "documented"}.get(action, "result")
                return AssistantResult(
                    action=action, content=data.get(key, str(data)),
                    confidence=0.92, files_used=files_used,
                    latency_ms=int((time.time()-t0)*1000),
                    model_used=MODELS.get(action, "qwen3:4b"),
                )
        except Exception as e:
            logger.warning("[L2] Codex server error: %s — using pool", e)

        # Fallback: direct ModelPool call
        system = (
            f"You are an expert {language} programmer. "
            f"Perform: {action}. Return code or analysis only."
            + (f"\n\nContext:\n{ctx[:1500]}" if ctx else "")
        )
        raw = await self._pool.generate(
            model=MODELS.get(action, "qwen3:4b"),
            prompt=f"```{language}\n{code}\n```",
            system=system,
            max_tokens=600,
            temperature=0.2,
        )
        return AssistantResult(
            action=action, content=raw, confidence=0.72,
            files_used=files_used,
            latency_ms=int((time.time()-t0)*1000),
        )

    # Alias used by jarvis_main_autonomous.py
    def scan_project(self, root: str = None):
        self.scan(root)

    @property
    def index_size(self) -> int:
        return len(self._index)
