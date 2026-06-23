"""brain/repair_modules/fix_file_ops.py
Deterministic file operation repair.
Handles class/file name mismatch, package mismatch, duplicate/invalid @Override.
"""

import os
import re
from pathlib import Path


def fix_class_file_mismatch(project_dir: str, errors: list[dict]) -> bool:
    """Rename file or class to resolve class/file name mismatch."""
    changed = False
    for error in errors:
        expected_file = error.get("symbol", "")
        file_path = error.get("file", "")
        if not expected_file or not file_path:
            continue

        full = os.path.join(project_dir, file_path)
        if not os.path.exists(full):
            continue

        expected = expected_file.replace(".java", "") + ".java"
        parent = os.path.dirname(full)
        target = os.path.join(parent, expected)
        if os.path.exists(target):
            continue

        # Read file to find actual class name
        try:
            with open(full, encoding="utf-8") as f:
                content = f.read()
            m = re.search(r"(?:public\s+)?(?:class|interface|enum)\s+(\w+)", content)
            wrong_class = m.group(1) if m else ""

            if not wrong_class:
                continue

            # Option 1: rename file to match class name
            target = os.path.join(parent, wrong_class + ".java")
            if not os.path.exists(target):
                os.rename(full, target)
                changed = True

            # Option 2: if the error said "should be FileName.java", rename class instead
            if expected_file.endswith(".java"):
                expected_class = expected_file.replace(".java", "")
                if wrong_class and wrong_class != expected_class:
                    content = content.replace(f"class {wrong_class}", f"class {expected_class}", 1)
                    with open(target, "w", encoding="utf-8") as f:
                        f.write(content)
                    changed = True
        except Exception:
            pass
    return changed


def fix_package_mismatch(project_dir: str, errors: list[dict]) -> bool:
    """Rewrite package declaration to match directory structure."""
    changed = False
    for error in errors:
        file_path = error.get("file", "")
        expected_pkg = error.get("symbol", "")
        if not file_path:
            continue

        full = os.path.join(project_dir, file_path)
        if not os.path.exists(full):
            continue

        # Infer correct package from directory path
        abs_path = os.path.abspath(full)
        src_dir = _find_src_root(abs_path)
        if not src_dir:
            continue

        rel = os.path.relpath(os.path.dirname(abs_path), src_dir)
        correct_pkg = rel.replace(os.sep, ".")
        if correct_pkg == ".":
            continue

        try:
            with open(full, encoding="utf-8") as f:
                content = f.read()
            pkg_match = re.search(r"package\s+([\w.]+);", content)
            if not pkg_match:
                continue
            current_pkg = pkg_match.group(1)
            if current_pkg == correct_pkg:
                continue  # already correct

            content = content.replace(f"package {current_pkg};", f"package {correct_pkg};")
            with open(full, "w", encoding="utf-8") as f:
                f.write(content)
            changed = True
        except Exception:
            pass
    return changed


def _find_src_root(abs_path: str) -> str | None:
    """Find the source root (java/ or kotlin/) by walking up from file path."""
    p = Path(abs_path)
    for parent in [p] + list(p.parents):
        parts = parent.parts
        if "java" in parts:
            idx = parts.index("java")
            return str(Path(*parts[: idx + 1]))
        if "kotlin" in parts:
            idx = parts.index("kotlin")
            return str(Path(*parts[: idx + 1]))
    return None


def fix_duplicate_override(project_dir: str, errors: list[dict]) -> bool:
    """Remove duplicate @Override annotations from source files."""
    changed = False
    for error in errors:
        file_path = error.get("file", "")
        if not file_path:
            continue
        full = os.path.join(project_dir, file_path)
        if not os.path.exists(full):
            continue
        try:
            with open(full, encoding="utf-8") as f:
                content = f.read()
            new_content = re.sub(r'@Override\s*\n\s*@Override', '@Override', content)
            if new_content != content:
                with open(full, "w", encoding="utf-8") as f:
                    f.write(new_content)
                changed = True
        except Exception:
            pass
    return changed
