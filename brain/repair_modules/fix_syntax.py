"""brain/repair_modules/fix_syntax.py
Deterministic syntax error repair.
Inserts missing semicolons, closes unclosed string literals, etc.
"""

import os
import re


def fix_missing_semicolon(project_dir: str, errors: list[dict]) -> bool:
    """Insert missing semicolons at specified lines."""
    return _apply_line_fix(project_dir, errors, _insert_semicolon)


def fix_unclosed_string(project_dir: str, errors: list[dict]) -> bool:
    """Close unclosed string literals at specified lines."""
    return _apply_line_fix(project_dir, errors, _close_string)


def _apply_line_fix(project_dir: str, errors: list[dict], fix_fn) -> bool:
    """Generic line-based fix: read file, fix line, write back."""
    changed = False
    for error in errors:
        file_path = error.get("file", "")
        line_num = error.get("line", 0)
        if not file_path or line_num < 1:
            continue
        full = os.path.join(project_dir, file_path)
        if not os.path.exists(full):
            continue
        try:
            with open(full, encoding="utf-8") as f:
                lines = f.readlines()
            if line_num > len(lines):
                continue
            original = lines[line_num - 1]
            fixed = fix_fn(original)
            if fixed and fixed != original:
                lines[line_num - 1] = fixed
                with open(full, "w", encoding="utf-8") as f:
                    f.writelines(lines)
                changed = True
        except Exception:
            pass
    return changed


def _insert_semicolon(line: str) -> str | None:
    """Add a semicolon at the end of a statement if missing."""
    stripped = line.strip()
    if not stripped or stripped.endswith(";") or stripped.endswith("{") or stripped.endswith("}"):
        return None
    if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
        return None
    return line.rstrip() + ";\n"


def _close_string(line: str) -> str | None:
    """Close an unclosed string literal."""
    count = line.count('"')
    if count % 2 == 0:
        return None  # already balanced
    return line.rstrip() + '"\n'
