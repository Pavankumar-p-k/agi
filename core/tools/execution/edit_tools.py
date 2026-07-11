import asyncio
import difflib
import hashlib
import logging
import os
import re
from pathlib import Path

from core.tools.execution.security import _resolve_tool_path

logger = logging.getLogger(__name__)

_BACKUP_DIR = None


def _get_backup_dir() -> str:
    global _BACKUP_DIR
    if _BACKUP_DIR is None:
        from core.constants import DATA_DIR
        _BACKUP_DIR = os.path.join(str(DATA_DIR), "file_backups")
        os.makedirs(_BACKUP_DIR, exist_ok=True)
    return _BACKUP_DIR


async def do_edit_file(content: str, owner: str | None = None) -> dict:
    from core.tools.document_tools import (
        _apply_edit_to_text,
        _apply_unified_diff,
        _normalize_text,
        parse_edit_blocks,
    )

    lines = content.split("\n", 1)
    first_line = lines[0].strip()

    if first_line.startswith("--- "):
        edit_content = content
        diff_match = re.search(r"--- a/(.+)", edit_content)
        raw_path = diff_match.group(1).split("\t")[0] if diff_match else None
        if not raw_path:
            return {"error": "Cannot determine file path from unified diff", "exit_code": 1}
        try:
            file_path = _resolve_tool_path(raw_path)
        except ValueError:
            return {"error": "Invalid file path", "exit_code": 1}
    else:
        file_path = first_line
        if not file_path:
            return {"error": "No file path provided", "exit_code": 1}
        edit_content = lines[1] if len(lines) > 1 else ""

    try:
        resolved = _resolve_tool_path(file_path)
    except ValueError:
        return {"error": "Invalid file path", "exit_code": 1}
    path = Path(resolved)

    if not path.exists():
        return {"error": f"File not found: {path}", "exit_code": 1}
    if not path.is_file():
        return {"error": f"Not a file: {path}", "exit_code": 1}

    try:
        original = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"error": f"Cannot read {path}: {e}", "exit_code": 1}

    stripped = edit_content.strip()
    if stripped.startswith("--- "):
        new_text, err = _apply_unified_diff(original, stripped)
        if new_text is None:
            return {"error": f"Unified diff failed: {err}", "exit_code": 1}
        applied = 1
        failed = 0
        details = [{"status": "ok", "match": "diff"}]
    else:
        edits = parse_edit_blocks(edit_content)
        if not edits:
            return {"error": "No FIND/REPLACE blocks or unified diff found", "exit_code": 1}
        current = _normalize_text(original)
        applied = 0
        failed = 0
        details = []
        for ed in edits:
            new_text_part, detail = _apply_edit_to_text(current, ed)
            if new_text_part is None:
                details.append(detail)
                failed += 1
            else:
                current = new_text_part
                details.append(detail)
                applied += 1
        if applied == 0:
            return {"error": "No edits matched file content", "details": details, "exit_code": 1}
        new_text = current

    if new_text == original:
        return {"error": "No changes — edited content matches original", "exit_code": 1}

    diff_lines = list(difflib.unified_diff(
        original.splitlines(keepends=True),
        new_text.splitlines(keepends=True),
        fromfile=f"a/{path.name}",
        tofile=f"b/{path.name}",
    ))
    diff_text = "".join(diff_lines)

    try:
        backup_dir = _get_backup_dir()
        backup_name = f"{path.name}.{hashlib.md5(str(path).encode()).hexdigest()[:8]}.bak"
        backup_path = os.path.join(backup_dir, backup_name)
        with open(backup_path, "w", encoding="utf-8") as fh:
            fh.write(original)
    except Exception as e:
        logger.warning("backup failed for %s: %s", path, e)

    try:
        path.write_text(new_text, encoding="utf-8")
    except Exception as e:
        return {"error": f"Cannot write {path}: {e}", "exit_code": 1}

    format_result = None
    try:
        if path.suffix == ".py":
            proc = await asyncio.create_subprocess_exec(
                "ruff", "format", str(path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode == 0:
                format_result = "ruff format"
            elif stderr:
                logger.debug("ruff format failed: %s", stderr.decode("utf-8", errors="replace")[:200])
        elif path.suffix in (".js", ".ts", ".tsx", ".jsx", ".css", ".json", ".md"):
            proc = await asyncio.create_subprocess_exec(
                "npx", "prettier", "--write", str(path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode == 0:
                format_result = "prettier"
            elif stderr:
                logger.debug("prettier format failed: %s", stderr.decode("utf-8", errors="replace")[:200])
    except Exception as e:
        logger.debug("auto-format skipped: %s", e)

    verify_note = ""
    if path.suffix == ".py":
        try:
            import ast
            ast.parse(new_text, filename=str(path))
        except SyntaxError as se:
            verify_note = f"⚠ SyntaxError: {se}"
            details.append({"status": "verify", "note": verify_note})

    test_suggestions = []
    try:
        base = path.stem
        parent = path.parent
        test_patterns = [
            parent / f"test_{path.name}",
            parent / f"test_{base}.py",
            parent.parent / "tests" / f"test_{base}.py",
            parent.parent / "tests" / f"test_{path.name}",
            Path.cwd() / "tests" / f"test_{base}.py",
        ]
        for tp in test_patterns:
            if tp.exists():
                test_suggestions.append(str(tp.relative_to(Path.cwd())))
    except Exception as e:
        logger.warning("handle_parallel_execution failed: %s", e)

    rel_path = str(path.relative_to(Path.cwd())) if path.is_relative_to(Path.cwd()) else str(path)
    try:
        from core.tools.hot_files import touch_file
        touch_file(rel_path)
    except Exception as e:
        logger.warning("handle_parallel_execution failed: %s", e)

    return {
        "action": "edit_file",
        "path": rel_path,
        "applied": applied,
        "failed": failed,
        "size": len(new_text),
        "diff": diff_text,
        "format": format_result,
        "verify": verify_note or None,
        "test_suggestions": test_suggestions or None,
        "details": details,
    }


async def do_refactor(content: str, owner: str | None = None) -> dict:
    from core.codebase_indexer import search_codebase

    lines = content.split("\n", 2)
    goal = lines[0].strip()
    if len(lines) > 1:
        file_list = [f.strip() for f in lines[1].split(",") if f.strip()]
    else:
        file_list = []
    edit_blocks = lines[2] if len(lines) > 2 else ""

    if not goal:
        return {"error": "No refactoring goal provided", "exit_code": 1}

    if edit_blocks.strip():
        from core.tools.document_tools import _apply_edit_to_text, _normalize_text, parse_edit_blocks
        edits = parse_edit_blocks(edit_blocks)
        if edits and file_list:
            results = []
            for fp_str in file_list:
                fp = Path(fp_str.strip())
                if not fp.is_absolute():
                    fp = Path.cwd() / fp
                try:
                    _resolve_tool_path(str(fp))
                except ValueError as e:
                    results.append({"file": fp_str, "error": f"path blocked: {e}"})
                    continue
                if not fp.exists():
                    results.append({"file": fp_str, "error": "not found"})
                    continue
                try:
                    original = fp.read_text(encoding="utf-8")
                except Exception as e:
                    logger.debug("Read error for %s: %s", fp_str, e)
                    results.append({"file": fp_str, "error": "Failed to read file"})
                    continue
                current = _normalize_text(original)
                applied = 0
                for ed in edits:
                    new_text, _ = _apply_edit_to_text(current, ed)
                    if new_text is not None:
                        current = new_text
                        applied += 1
                if applied > 0:
                    fp.write_text(current, encoding="utf-8")
                    results.append({"file": fp_str, "applied": applied})
                else:
                    results.append({"file": fp_str, "applied": 0})
            return {
                "action": "refactor",
                "goal": goal,
                "results": results,
                "total_files": len(results),
            }

    if not file_list:
        results = search_codebase(goal, k=5, owner=owner)
        search_hits = results.count("\n# ") if results else 0
    else:
        search_hits = len(file_list)

    plan_steps = _generate_refactor_plan(goal, file_list)
    return {
        "action": "refactor",
        "goal": goal,
        "plan": plan_steps,
        "search_hits": search_hits,
        "note": "Use the plan steps above to guide your edits. Call edit_file or batch_edit_file for each step.",
        "exit_code": 0,
    }


def _generate_refactor_plan(goal: str, files: list[str]) -> list[dict]:
    plan = [{"step": 1, "action": "Understand current code", "detail": f"Read the relevant files to understand current structure: {', '.join(files) if files else '(use semantic_search to find them)'}"},
            {"step": 2, "action": "Make the changes", "detail": "Use edit_file or batch_edit_file for each change"},
            {"step": 3, "action": "Verify", "detail": "Run tests to verify the changes work"}]
    return plan


async def do_undo_edit_file(path_str: str) -> dict:
    path = Path(path_str)
    if not path.is_absolute():
        path = Path.cwd() / path
    path = path.resolve()
    try:
        _resolve_tool_path(str(path))
    except ValueError as e:
        return {"error": f"path blocked: {e}", "exit_code": 1}

    backup_dir = _get_backup_dir()
    prefix = f"{path.name}.{hashlib.md5(str(path).encode()).hexdigest()[:8]}."
    backups = sorted(
        [f for f in os.listdir(backup_dir) if f.startswith(prefix)],
        key=lambda f: os.path.getmtime(os.path.join(backup_dir, f)),
        reverse=True,
    )
    if not backups:
        return {"error": f"No backups found for {path.name}", "exit_code": 1}

    latest = os.path.join(backup_dir, backups[0])
    try:
        with open(latest, encoding="utf-8") as fh:
            restored = fh.read()
        path.write_text(restored, encoding="utf-8")
        rel = str(path.relative_to(Path.cwd())) if path.is_relative_to(Path.cwd()) else str(path)
        return {"action": "undo_edit_file", "path": rel, "size": len(restored), "exit_code": 0}
    except Exception as e:
        return {"error": f"Undo failed: {e}", "exit_code": 1}


async def do_batch_edit_file(content: str) -> dict:
    from core.tools.document_tools import _apply_edit_to_text, _normalize_text, parse_edit_blocks

    lines = content.split("\n", 1)
    pattern = lines[0].strip()
    edit_blocks = lines[1] if len(lines) > 1 else ""
    if not pattern or not edit_blocks:
        return {"error": "Usage: <glob_pattern>\\n<FIND/REPLACE blocks>", "exit_code": 1}

    edits = parse_edit_blocks(edit_blocks)
    if not edits:
        return {"error": "No FIND/REPLACE blocks found", "exit_code": 1}

    matched = list(Path.cwd().glob(pattern))
    if not matched:
        return {"error": f"No files matching '{pattern}'", "exit_code": 1}

    results = []
    total_applied = 0
    total_failed = 0
    for fp in matched:
        try:
            _resolve_tool_path(str(fp))
        except ValueError as e:
            results.append({"path": str(fp), "error": f"path blocked: {e}"})
            total_failed += 1
            continue
        if not fp.is_file():
            continue
        try:
            original = fp.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.debug("Read error for %s: %s", fp, e)
            results.append({"path": str(fp), "error": "Failed to read file"})
            continue

        current = _normalize_text(original)
        applied = 0
        failed = 0
        file_details = []
        for ed in edits:
            new_text_part, detail = _apply_edit_to_text(current, ed)
            if new_text_part is None:
                file_details.append(detail)
                failed += 1
            else:
                current = new_text_part
                file_details.append(detail)
                applied += 1

        if applied == 0:
            results.append({"path": str(fp), "applied": 0, "details": file_details})
            continue

        try:
            fp.write_text(current, encoding="utf-8")
        except Exception as e:
            logger.debug("Write error for %s: %s", fp, e)
            results.append({"path": str(fp), "error": "Failed to write file"})
            continue

        total_applied += applied
        total_failed += failed
        results.append({"path": str(fp), "applied": applied, "failed": failed})

    return {
        "action": "batch_edit_file",
        "files_edited": len([r for r in results if r.get("applied", 0) > 0]),
        "total_applied": total_applied,
        "total_failed": total_failed,
        "results": results,
    }
