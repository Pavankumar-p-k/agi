from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger(__name__)

_ERROR_FIX_REGISTRY: list[tuple[re.Pattern, str, str, dict]] = [
    (re.compile(r"cannot find symbol.*class (\w+)", re.I), "missing_import", "add_import", {}),
    (re.compile(r"package (.+) does not exist", re.I), "missing_package", "add_gradle_dependency", {}),
    (re.compile(r"cannot find symbol.*variable (\w+)", re.I), "undefined_variable", "fix_code", {}),
    (re.compile(r"R\.layout\.(\w+)", re.I), "missing_layout", "create_resource_file", {"type": "layout"}),
    (re.compile(r"R\.id\.(\w+)", re.I), "missing_view_id", "fix_code", {}),
    (re.compile(r"R\.(\w+)", re.I), "missing_resource", "create_resource_file", {}),
    (re.compile(r"cannot find symbol.*method (\w+)", re.I), "missing_method", "fix_code", {}),
    (re.compile(r"plugin.*not found.*'([^']+)'", re.I), "missing_gradle_plugin", "fix_gradle", {}),
    (re.compile(r"Could not find method (\w+)", re.I), "gradle_syntax", "fix_gradle", {}),
    (re.compile(r"incompatible types", re.I), "type_mismatch", "fix_code", {}),
    (re.compile(r"(?:file|resource|layout|drawable) not found:?\s*(.+)", re.I), "missing_file", "create_file", {}),
    (re.compile(r"Unresolved reference: (\w+)", re.I), "unresolved_reference", "fix_code", {}),
    (re.compile(r"Activity (.+) not registered", re.I), "missing_activity_registration", "fix_manifest", {}),
    (re.compile(r"has not been declared in AndroidManifest", re.I), "missing_activity_registration", "fix_manifest", {}),
    (re.compile(r"(syntax error|unexpected token|';' expected)", re.I), "syntax_error", "fix_code", {}),
    (re.compile(r"class (\w+) not found", re.I), "missing_class", "create_file", {}),
]

_FIX_DESCRIPTIONS = {
    "add_import": "Add missing import for %s",
    "add_gradle_dependency": "Add Gradle dependency for package %s",
    "fix_code": "Fix code at the indicated location",
    "create_resource_file": "Create missing resource file: %s",
    "fix_gradle": "Fix Gradle build file",
    "create_file": "Create missing file: %s",
    "fix_manifest": "Fix AndroidManifest.xml",
    "missing_layout": "Create missing layout file: %s.xml",
    "missing_activity_registration": "Register activity in AndroidManifest.xml",
}


def classify_error(build_output: str) -> list[dict]:
    """Classify build errors into structured fixes without LLM.

    Returns list of {error_text, fix_type, fix_params, file?, line?}
    """
    results = []
    for pattern, fix_type, fix_action, default_params in _ERROR_FIX_REGISTRY:
        for match in pattern.finditer(build_output):
            error_text = match.group(0)
            line = match.string[match.start():match.start() + 200]
            file_match = re.search(r'([\w/]+\.\w+):', line)
            file_path = file_match.group(1) if file_match else ""
            line_num = 0
            line_match = re.search(r':(\d+):', line)
            if line_match:
                line_num = int(line_match.group(1))

            params = dict(default_params)
            if match.groups():
                params["name"] = match.group(1)

            results.append({
                "error_text": error_text[:100],
                "fix_type": fix_type,
                "fix_action": fix_action,
                "fix_params": params,
                "file": file_path,
                "line": line_num,
                "match": match,
            })
    seen = set()
    unique = []
    for r in results:
        key = r["error_text"]
        if key not in seen:
            seen.add(key)
            r.pop("match")
            unique.append(r)
    return unique


def apply_fix(fix: dict, proj_dir: str, root: str) -> bool:
    """Apply a classified fix. Returns True if applied."""
    fix_type = fix.get("fix_type", "")
    fix_action = fix.get("fix_action", "")
    params = fix.get("fix_params", {})
    name = params.get("name", "")

    if fix_action == "add_import":
        file_path = fix.get("file", "")
        if file_path:
            full = os.path.join(proj_dir, file_path.replace("\\", "/"))
            if os.path.exists(full):
                with open(full, "r", encoding="utf-8") as f:
                    content = f.read()
                import_line = f"import {name};\n"
                if import_line not in content and "package " in content:
                    pkg_end = content.index(";", content.index("package ")) + 1
                    content = content[:pkg_end] + "\n" + import_line + content[pkg_end:]
                    with open(full, "w", encoding="utf-8") as f:
                        f.write(content)
                    logger.info("[Fix] added import %s to %s", name, file_path)
                    return True
        for r, dirs, files in os.walk(root or proj_dir):
            for f in files:
                if f.endswith(".java"):
                    full = os.path.join(r, f)
                    with open(full, "r", encoding="utf-8") as fh:
                        content = fh.read()
                    import_line = f"import {name};\n"
                    if import_line not in content and "package " in content:
                        pkg_end = content.index(";", content.index("package ")) + 1
                        content = content[:pkg_end] + "\n" + import_line + content[pkg_end:]
                        with open(full, "w", encoding="utf-8") as fh:
                            fh.write(content)
                        logger.info("[Fix] added import %s to %s", name, os.path.relpath(full, proj_dir))
                        return True
        return False

    if fix_action in ("create_file", "create_resource_file"):
        res_type = params.get("type", "")
        if res_type == "layout" and name:
            fname = f"{name}.xml"
            for r, dirs, files in os.walk(root or proj_dir):
                if r.endswith("layout") or "layout" in dirs:
                    layout_dir = os.path.join(r if r.endswith("layout") else r, "layout")
                    full = os.path.join(layout_dir, fname)
                    if not os.path.exists(full):
                        os.makedirs(os.path.dirname(full), exist_ok=True)
                        with open(full, "w", encoding="utf-8") as fh:
                            fh.write('<?xml version="1.0" encoding="utf-8"?>\n<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"\n    android:layout_width="match_parent"\n    android:layout_height="match_parent"\n    android:orientation="vertical">\n\n</LinearLayout>\n')
                        logger.info("[Fix] created layout %s", fname)
                        return True
        if name and name.endswith(".java"):
            full = os.path.join(proj_dir, name.replace("\\", "/"))
            if not os.path.exists(full):
                os.makedirs(os.path.dirname(full), exist_ok=True)
                cls = os.path.splitext(os.path.basename(name))[0]
                pkg = "com.example"
                with open(full, "w", encoding="utf-8") as fh:
                    fh.write(f"package {pkg};\n\npublic class {cls} {{\n    // TODO\n}}\n")
                logger.info("[Fix] created file %s", name)
                return True
        file_path = fix.get("file", "")
        if file_path and not os.path.exists(os.path.join(proj_dir, file_path.replace("\\", "/"))):
            full = os.path.join(proj_dir, file_path.replace("\\", "/"))
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w") as fh:
                fh.write(f"// {file_path}\n// TODO\n")
            logger.info("[Fix] created file %s", file_path)
            return True
        return False

    if fix_action == "fix_manifest":
        manifest_path = os.path.join(proj_dir, "src/main/AndroidManifest.xml")
        if not os.path.exists(manifest_path):
            manifest_path = os.path.join(proj_dir, "AndroidManifest.xml")
        if os.path.exists(manifest_path):
            with open(manifest_path, "r", encoding="utf-8") as fh:
                content = fh.read()
            if name and "activity" not in content.lower() or (name and name not in content):
                activity_xml = f'\n        <activity android:name=".{name}" />\n'
                if "</application>" in content and name not in content:
                    content = content.replace("</application>", activity_xml + "    </application>")
                    with open(manifest_path, "w", encoding="utf-8") as fh:
                        fh.write(content)
                    logger.info("[Fix] registered activity %s in manifest", name)
                    return True
        return False

    if fix_action == "fix_gradle":
        gradle_path = os.path.join(proj_dir, "build.gradle")
        if not os.path.exists(gradle_path):
            gradle_path = os.path.join(root, "build.gradle") if root else ""
        if os.path.exists(gradle_path):
            with open(gradle_path, "r", encoding="utf-8") as fh:
                content = fh.read()
            if name and "implementation" not in content:
                dep_line = f"    implementation '{name}'\n"
                if "dependencies {" in content:
                    content = content.replace("dependencies {", "dependencies {\n" + dep_line)
                    with open(gradle_path, "w", encoding="utf-8") as fh:
                        fh.write(content)
                    logger.info("[Fix] added dependency %s to build.gradle", name)
                    return True
        return False

    if fix_action == "fix_code":
        file_path = fix.get("file", "")
        if file_path:
            full = os.path.join(proj_dir, file_path.replace("\\", "/"))
            if os.path.exists(full):
                logger.info("[Fix] code fix needed in %s — will use LLM", file_path)
        return False

    return False
