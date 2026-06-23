"""brain/repair_modules/fix_class_names.py
Renames classes to match filenames (or vice versa).
Handles import-name collisions (e.g., a class named 'Database' conflicting with androidx.room.Database).
"""
import re
from pathlib import Path


def fix_class_names(project_dir: str, errors: list[dict]) -> list[str]:
    """Fix class/file name mismatches and import-name collisions."""
    fixes = []
    proj = Path(project_dir)
    java_files = list(proj.rglob("*.java"))

    for error in errors:
        msg = error.get("message", "")
        file_path = error.get("file", "")

        # Class/file mismatch
        mismatch = re.search(r"class (\w+) is public, should be declared in a file named (\w+\.java)", msg)
        if mismatch:
            class_name = mismatch.group(1)
            file_name = mismatch.group(2)
            target_name = file_name.replace(".java", "")
            for jf in java_files:
                content = jf.read_text(encoding="utf-8")
                if class_name in content and jf.name != file_name:
                    content = content.replace(f"class {class_name}", f"class {target_name}")
                    jf.write_text(content, encoding="utf-8")
                    fixes.append(f"Renamed class {class_name} -> {target_name} in {jf.name}")

        # Package mismatch
        pkg_match = re.search(r"expected (.+)\.(.+)\.(\w+)", msg)
        if pkg_match:
            expected_pkg = f"{pkg_match.group(1)}.{pkg_match.group(2)}"
            for jf in java_files:
                content = jf.read_text(encoding="utf-8")
                pkg_decl = re.search(r"^package\s+([\w.]+)\s*;", content, re.MULTILINE)
                if pkg_decl and pkg_decl.group(1) != expected_pkg:
                    content = re.sub(r"^package\s+[\w.]+\s*;", f"package {expected_pkg};", content, flags=re.MULTILINE)
                    jf.write_text(content, encoding="utf-8")
                    fixes.append(f"Fixed package in {jf.name}: {pkg_decl.group(1)} -> {expected_pkg}")

        # Import name collision (e.g., class named Database conflicting with import)
        collision = re.search(r"(\w+) cannot be resolved to a type", msg)
        if collision:
            collision_name = collision.group(1)
            for jf in java_files:
                content = jf.read_text(encoding="utf-8")
                if f"class {collision_name}" in content and f"import" in content.lower():
                    import re as _re
                    if _re.search(rf"import\s+\w+\.{collision_name}\s*;", content):
                        new_name = collision_name + "Local"
                        content = content.replace(f"class {collision_name}", f"class {new_name}")
                        content = content.replace(f"new {collision_name}", f"new {new_name}")
                        jf.write_text(content, encoding="utf-8")
                        fixes.append(f"Renamed class {collision_name} -> {new_name} to resolve import collision")
                        break

    return fixes
