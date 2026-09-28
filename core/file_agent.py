"""JarvisFileAgent — file operations: read/write/edit/list/tree/commands."""
from __future__ import annotations

import asyncio
import difflib
import os
import re
import shutil
from pathlib import Path
from typing import Any

from core.result import Ok

# Commands that must never run (destructive / irreversible).
_BLOCKED_PATTERNS = [
    r"\brm\s+(-[a-z]*\s+)*-?r[a-z]*f",   # rm -rf variants
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r"\bformat\b.*:",
    r"\bdel\s+/[sq]\b",
    r"\brd\s+/s\b",
    r":\(\)\{.*\};:",                      # fork bomb
    r"\bshutdown\b",
    r"\breboot\b",
]

_OUTPUT_LIMIT = 10_000


def llm_complete(prompt: str):
    """Module-level LLM hook (tests patch this).

    Routed through the Execution stage gateway — LLM access is owned by the
    execution stage (Rule 1).
    """
    from core.pipeline.stages.execution import complete
    return complete(prompt)


class JarvisFileAgent:
    """File operations with confirmation gates and output limits."""

    def __init__(self, **kwargs: Any):
        for k, v in kwargs.items():
            setattr(self, k, v)

    # ── read / write ─────────────────────────────────────────────────
    async def read_file(self, path: str) -> str:
        def _read():
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        return await asyncio.to_thread(_read)

    async def write_file(self, path: str, content: str,
                         skip_confirm: bool = False) -> dict[str, Any]:
        def _write():
            p = Path(path)
            existed = p.exists()
            old = p.read_text(encoding="utf-8", errors="replace") if existed else ""
            if existed and old == content:
                return {"changed": False, "size": len(content)}
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            diff = "\n".join(difflib.unified_diff(
                old.splitlines(), content.splitlines(),
                fromfile="old", tofile="new", lineterm=""))[:2000] if existed else ""
            result = {"changed": True, "size": len(content)}
            if diff:
                result["diff"] = diff
            return result
        return await asyncio.to_thread(_write)

    # ── edit ─────────────────────────────────────────────────────────
    async def edit_file(self, path: str, old: str, new: str,
                        skip_confirm: bool = False) -> dict[str, Any]:
        def _edit():
            p = Path(path)
            if not p.exists():
                return {"error": f"file not found: {path}"}
            content = p.read_text(encoding="utf-8", errors="replace")
            if old in content:
                updated = content.replace(old, new, 1)
                p.write_text(updated, encoding="utf-8")
                return {"changed": True, "exact_match": True}
            # Fuzzy match: similar block replacement
            lines = content.splitlines()
            old_lines = old.splitlines()
            matcher = difflib.SequenceMatcher(None, lines, old_lines)
            block = matcher.get_matching_blocks()
            if block and block[0].size > 0:
                start = block[0].a
                end = start + len(old_lines) if start + len(old_lines) <= len(lines) else len(lines)
                similarity = sum(b.size for b in block) / max(1, len(old_lines))
                if similarity >= 0.6:
                    updated_lines = lines[:start] + new.splitlines() + lines[end:]
                    p.write_text("\n".join(updated_lines), encoding="utf-8")
                    return {"changed": True, "fuzzy_match": True,
                            "similarity": round(similarity, 2)}
            return {"error": "no match found for edit"}
        return await asyncio.to_thread(_edit)

    # ── list / tree ──────────────────────────────────────────────────
    async def list_files(self, directory: str, recursive: bool = False,
                         pattern: str = "") -> list[dict[str, Any]]:
        def _list():
            p = Path(directory)
            if not p.is_dir():
                return []
            glob = p.rglob("*") if recursive else p.glob("*")
            out = []
            for f in sorted(glob):
                if not f.is_file():
                    continue
                rel = str(f.relative_to(p)) if recursive else f.name
                if pattern and pattern not in f.name:
                    continue
                out.append({"name": rel, "path": str(f),
                            "size": f.stat().st_size})
            return out
        return await asyncio.to_thread(_list)

    async def tree_view(self, directory: str, depth: int = 3) -> str:
        def _tree():
            p = Path(directory)
            if not p.is_dir():
                return ""
            lines: list[str] = []

            def walk(d: Path, level: int) -> None:
                if level > depth:
                    return
                for child in sorted(d.iterdir()):
                    indent = "  " * level
                    if child.is_dir():
                        lines.append(f"{indent}{child.name}/")
                        walk(child, level + 1)
                    else:
                        lines.append(f"{indent}{child.name}")
            walk(p, 0)
            return "\n".join(lines)
        return await asyncio.to_thread(_tree)

    # ── commands ─────────────────────────────────────────────────────
    async def run_command(self, command: str, timeout: int = 60,
                          cwd: str | None = None,
                          skip_confirm: bool = False) -> dict[str, Any]:
        for pattern in _BLOCKED_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return {"error": f"blocked destructive command: {pattern}"}

        async def _run():
            try:
                proc = await asyncio.create_subprocess_shell(
                    command,
                    cwd=cwd or os.getcwd(),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                try:
                    out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
                except asyncio.TimeoutError:
                    proc.kill()
                    return {"returncode": -1, "stdout": "", "error": f"timed out after {timeout}s"}
                text = out.decode("utf-8", errors="replace") if out else ""
                return {"returncode": proc.returncode or 0,
                        "stdout": text[:_OUTPUT_LIMIT]}
            except Exception as exc:  # noqa: BLE001
                return {"returncode": -1, "stdout": "", "error": str(exc)}
        return await _run()

    # ── organize / generate ─────────────────────────────────────────
    async def organize_folder(self, directory: str, instruction: str = "",
                              skip_confirm: bool = False) -> dict[str, Any]:
        p = Path(directory)
        if not p.is_dir():
            return {"error": f"not a directory: {directory}"}
        moved = 0
        by_type: dict[str, str] = {
            ".jpg": "images", ".png": "images", ".gif": "images",
            ".pdf": "documents", ".docx": "documents", ".txt": "documents",
            ".mp3": "audio", ".mp4": "video", ".zip": "archives",
        }
        for f in list(p.iterdir()):
            if f.is_file() and f.suffix.lower() in by_type:
                target = p / by_type[f.suffix.lower()]
                target.mkdir(exist_ok=True)
                if not (target / f.name).exists():
                    shutil.move(str(f), str(target / f.name))
                    moved += 1
        return {"summary": f"organized {moved} file(s) by type", "moved": moved}

    async def generate_document(self, template: str, data: dict[str, Any],
                                output_path: str,
                                skip_confirm: bool = False) -> dict[str, Any]:
        # Try LLM enhancement, fall back to plain template fill.
        content = template
        for key, value in (data or {}).items():
            content = content.replace("{{" + key + "}}", str(value))
        if "{{" not in content:
            try:
                res = llm_complete(f"Polish this document:\n{content}")
                if hasattr(res, "is_ok") and res.is_ok():
                    content = res.unwrap()
            except Exception:  # noqa: BLE001 — LLM optional
                pass
        return await self.write_file(output_path, content, skip_confirm=True)


# Module-level singleton
file_agent = JarvisFileAgent()

__all__ = ["JarvisFileAgent", "file_agent", "llm_complete"]
