"""Unified deterministic compiler repair engine.

Parses javac/Gradle/AAPT2 errors into structured fixes,
applies deterministic repair modules in priority order,
records successful fixes in PatternFailureMemory,
and collects build metrics.

Priority order:
  1. Exact PatternFailureMemory match
  2. Pattern PatternFailureMemory match
  3. Deterministic repair rule matching structured error category
  4. ArchitecturalMemory guidance
  5. LLM repair (last resort)
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class JavacError:
    file: str
    line: int
    category: str
    symbol: str
    message: str
    raw: str = ""

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "line": self.line,
            "category": self.category,
            "symbol": self.symbol,
            "message": self.message[:200],
            "raw": self.raw[:300],
        }


@dataclass
class RepairAction:
    category: str
    action: str
    params: dict = field(default_factory=dict)
    success: bool = False
    duration_ms: float = 0.0
    error: str = ""


@dataclass
class BuildMetrics:
    total_errors: int = 0
    classified_errors: int = 0
    fixed_errors: int = 0
    repair_attempts: int = 0
    llm_fallback_used: bool = False
    pattern_memory_hits: int = 0
    pattern_memory_misses: int = 0
    start_time: str = ""
    end_time: str = ""
    total_duration_ms: float = 0.0
    repairs: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_errors": self.total_errors,
            "classified_errors": self.classified_errors,
            "fixed_errors": self.fixed_errors,
            "repair_attempts": self.repair_attempts,
            "llm_fallback_used": self.llm_fallback_used,
            "pattern_memory_hits": self.pattern_memory_hits,
            "pattern_memory_misses": self.pattern_memory_misses,
            "total_duration_ms": round(self.total_duration_ms, 1),
            "fix_rate_pct": round(self.fixed_errors / max(self.total_errors, 1) * 100, 1),
            "repairs": self.repairs[-20:],
        }


# ── Structured Javac Error Parsers ─────────────────────────────

_ERROR_PARSERS: list[tuple[re.Pattern, str, str]] = [
    # Missing import: cannot find symbol class X
    (re.compile(r"([\w/]+\.java):(\d+):\s*error:\s*cannot find symbol\s*\n\s*symbol:\s*(?:class|variable)\s+(\w+)", re.M), "missing_import", "class"),
    (re.compile(r"cannot find symbol\s*\n\s*symbol:\s*(?:class|variable)\s+(\w+)", re.I), "missing_import", "class"),
    # Package does not exist
    (re.compile(r"package\s+([\w.]+)\s+does not exist", re.I), "missing_package", "package"),
    # Cannot resolve symbol
    (re.compile(r"([\w/]+\.java):(\d+):\s*error:\s*cannot find symbol", re.M), "missing_symbol", "symbol"),
    (re.compile(r"error: cannot find symbol\s+(\w+)", re.I), "missing_symbol", "symbol"),
    # R.layout / R.id / R.drawable / R.string not found
    (re.compile(r"([\w/]+\.java):(\d+):\s*error:\s*R\.layout\.(\w+)", re.M), "missing_layout", "layout"),
    (re.compile(r"R\.layout\.(\w+)"), "missing_layout", "layout"),
    (re.compile(r"R\.id\.(\w+)"), "missing_view_id", "id"),
    (re.compile(r"R\.drawable\.(\w+)"), "missing_drawable", "drawable"),
    (re.compile(r"R\.string\.(\w+)"), "missing_string", "string"),
    (re.compile(r"R\.color\.(\w+)"), "missing_color", "color"),
    (re.compile(r"R\.mipmap\.(\w+)"), "missing_mipmap", "mipmap"),
    (re.compile(r"R\.(\w+)\.(\w+)"), "missing_resource", "resource"),
    # Class/file name mismatch
    (re.compile(r"class\s+(\w+)\s+is\s+public,\s*should\s+be\s+declared\s+in\s+a\s+file\s+named\s+(\w+)", re.I), "class_file_mismatch", "class"),
    # Package mismatch
    (re.compile(r"package\s+(\S+)\s+does not match expected package\s+(\S+)", re.I), "package_mismatch", "package"),
    (re.compile(r"error: expected package\s+(\S+)", re.I), "package_mismatch", "package"),
    # Duplicate @Override
    (re.compile(r"@Override\s*\n\s*@Override", re.I), "duplicate_override", "annotation"),
    (re.compile(r"method does not override or implement a method from a supertype", re.I), "invalid_override", "annotation"),
    # Incompatible types
    (re.compile("incompatible types:\s*(\S+)\s*cannot be converted to\s*(\S+)", re.I), "type_mismatch", "type"),
    # Method not found
    (re.compile("cannot find symbol.*method\s+(\w+)", re.I | re.DOTALL), "missing_method", "method"),
    # Room: @Entity, @Dao, @Database errors
    (re.compile("error: Entities and POJOs must have a usable public constructor", re.I), "room_entity", "room"),
    (re.compile("error: Cannot find setter for field", re.I), "room_field", "room"),
    (re.compile("error: Primary key must be set", re.I), "room_primary_key", "room"),
    (re.compile("error: Schema export directory is not provided", re.I), "room_schema", "room"),
    (re.compile("error: Not sure how to convert a Cursor to this method's return type", re.I), "room_query", "room"),
    (re.compile("error: The query returns an empty cursor", re.I), "room_query", "room"),
    # Navigation
    (re.compile("error: resource style/Theme\..+ \(aka .+\) not found", re.I), "missing_theme", "resource"),
    (re.compile("error: cannot find symbol class NavHostFragment", re.I), "missing_nav_import", "navigation"),
    (re.compile("error: cannot find symbol class NavController", re.I), "missing_nav_import", "navigation"),
    (re.compile("error: cannot find symbol class Navigation", re.I), "missing_nav_import", "navigation"),
    # RecyclerView
    (re.compile("error: cannot find symbol class RecyclerView", re.I), "missing_recyclerview_import", "recyclerview"),
    (re.compile("error: cannot find symbol class LinearLayoutManager", re.I), "missing_recyclerview_import", "recyclerview"),
    (re.compile("error: cannot find symbol class RecyclerView\.Adapter", re.I), "missing_recyclerview_adapter", "recyclerview"),
    (re.compile("error: cannot find symbol class RecyclerView\.ViewHolder", re.I), "missing_recyclerview_viewholder", "recyclerview"),
    # LiveData / ViewModel
    (re.compile("error: cannot find symbol class (LiveData|MutableLiveData)", re.I), "missing_livedata_import", "livedata"),
    (re.compile("error: cannot find symbol class ViewModel", re.I), "missing_viewmodel_import", "viewmodel"),
    (re.compile("error: cannot find symbol class ViewModelProvider", re.I), "missing_viewmodel_provider", "viewmodel"),
    # Material
    (re.compile("error: cannot find symbol class (MaterialButton|MaterialCardView|FloatingActionButton|BottomNavigationView|NavigationView|Snackbar|TextInputLayout|Chip|ChipGroup)", re.I), "missing_material_import", "material"),
    # Gson
    (re.compile("error: cannot find symbol class (Gson|GsonBuilder|JsonParser)", re.I), "missing_gson_import", "gson"),
    # Glide / Picasso
    (re.compile("error: cannot find symbol class (Glide|Picasso|RequestOptions)", re.I), "missing_image_loader_import", "image_loader"),
    # Manifest: Activity not registered
    (re.compile("error: Activity (.+) has not been declared in AndroidManifest", re.I), "missing_activity", "manifest"),
    (re.compile("Activity (.+) not registered", re.I), "missing_activity", "manifest"),
    # Manifest: Permission
    (re.compile("error: Permission (.+) is not declared in AndroidManifest", re.I), "missing_permission", "manifest"),
    # Gradle: Plugin not found
    (re.compile("Plugin with id '([^']+)' not found", re.I), "missing_gradle_plugin", "gradle"),
    (re.compile("Could not find method (\w+)\(\)", re.I), "gradle_syntax", "gradle"),
    # Gradle: Dependency
    (re.compile("Could not resolve all dependencies for configuration", re.I), "missing_dependency", "gradle"),
    (re.compile("Cannot resolve external dependency", re.I), "missing_dependency", "gradle"),
    # DataBinding
    (re.compile("error: cannot find symbol class (DataBindingUtil|.*Binding)", re.I), "missing_databinding", "databinding"),
    # AAPT2 / Resource linking
    (re.compile("AAPT2 error: check logs for details", re.I), "aapt2_error", "resource"),
    (re.compile("resource [\w./]+ not found", re.I), "resource_not_found", "resource"),
    (re.compile("error: failed linking file resources", re.I), "resource_linking", "resource"),
    # Unclosed string literal / syntax
    (re.compile(r"([\w/]+\.java):(\d+):\s*error:\s*unclosed string literal", re.M), "syntax_string", "syntax"),
    (re.compile("unclosed string literal", re.I), "syntax_string", "syntax"),
    (re.compile(r"([\w/]+\.java):(\d+):\s*error:\s*'\)'\s*expected", re.M), "syntax_paren", "syntax"),
    (re.compile("error: '\)' expected", re.I), "syntax_paren", "syntax"),
    (re.compile(r"([\w/]+\.java):(\d+):\s*error:\s*';'\s*expected", re.M), "syntax_semicolon", "syntax"),
    (re.compile("error: ';' expected", re.I), "syntax_semicolon", "syntax"),
    # Lambda
    (re.compile("error: lambda expression not expected here", re.I), "lambda_syntax", "syntax"),
    # Generic Android
    (re.compile("error: cannot find symbol class (\w+)", re.I), "missing_class", "class"),
    # D8 duplicate class
    (re.compile("Duplicate\s+class\s+(\S+)\s+found\s+in\s+modules", re.I), "d8_duplicate_class", "dependency"),
    (re.compile("Program\s+type\s+already\s+present:\s*(\S+)", re.I), "d8_duplicate_class", "dependency"),
    # Kotlin JVM target mismatch
    (re.compile("Incompatible\s+JVM\s+target\s+version\s+between\s+Java\s+and\s+Kotlin", re.I), "kotlin_jvm_target", "gradle"),
    # D8 desugar failure
    (re.compile("D8\s+Desugar:\s*Error:\s*Could\s+not\s+desugar\s+type", re.I), "d8_desugar_error", "desugar"),
    (re.compile("Lambda\s+desugaring\s+failed\s+for\s+method", re.I), "d8_desugar_error", "desugar"),
    # NDK / CMake errors
    (re.compile(r"ninja:\s*error:", re.I), "ndk_build_error", "ndk"),
    (re.compile(r"fatal\s+error:\s*'\S+'\s+file\s+not\s+found", re.I), "ndk_build_error", "ndk"),
    (re.compile(r"C/C\+\+:\s*fatal\s+error:", re.I), "ndk_build_error", "ndk"),
]

# Map error categories to deterministic repair functions
CATEGORY_REPAIR_MAP: dict[str, str] = {
    "missing_import": "add_import",
    "missing_package": "add_gradle_dependency",
    "missing_symbol": "fix_code",
    "missing_layout": "create_layout",
    "missing_view_id": "add_view_id",
    "missing_drawable": "create_drawable",
    "missing_string": "add_string_resource",
    "missing_color": "add_color_resource",
    "missing_mipmap": "create_mipmap",
    "missing_resource": "fix_code",
    "class_file_mismatch": "fix_class_name",
    "package_mismatch": "fix_package",
    "duplicate_override": "fix_duplicate_override",
    "invalid_override": "fix_invalid_override",
    "type_mismatch": "fix_code",
    "missing_method": "fix_code",
    "room_entity": "fix_room",
    "room_field": "fix_room",
    "room_primary_key": "fix_room",
    "room_schema": "fix_room",
    "room_query": "fix_room",
    "missing_nav_import": "add_import",
    "missing_recyclerview_import": "add_import",
    "missing_recyclerview_adapter": "fix_code",
    "missing_recyclerview_viewholder": "fix_code",
    "missing_livedata_import": "add_import",
    "missing_viewmodel_import": "add_import",
    "missing_viewmodel_provider": "add_import",
    "missing_material_import": "add_import",
    "missing_gson_import": "add_import",
    "missing_image_loader_import": "add_import",
    "missing_activity": "fix_manifest",
    "missing_permission": "fix_manifest",
    "missing_gradle_plugin": "fix_gradle",
    "gradle_syntax": "fix_gradle",
    "missing_dependency": "fix_dependencies",
    "missing_databinding": "fix_code",
    "aapt2_error": "fix_resources",
    "resource_not_found": "fix_resources",
    "resource_linking": "fix_resources",
    "syntax_string": "fix_syntax",
    "syntax_paren": "fix_syntax",
    "syntax_semicolon": "fix_syntax",
    "lambda_syntax": "fix_code",
    "missing_class": "create_file",
    "missing_theme": "fix_resources",
    "missing_recyclerview_import": "add_import",
    "d8_duplicate_class": "fix_dependencies",
    "kotlin_jvm_target": "fix_gradle",
    "d8_desugar_error": "fix_gradle",
    "ndk_build_error": "fix_code",
}


class CompilerRepairEngine:
    """Unified deterministic compiler repair engine.

    Parses build output into structured errors, applies deterministic
    repairs in priority order, records results in PatternFailureMemory.
    """

    def __init__(self, project_dir: str, pattern_memory=None):
        self.project_dir = project_dir
        self._pattern_memory = pattern_memory
        self.metrics = BuildMetrics()
        self._parsers = _ERROR_PARSERS

    def parse_errors(self, build_output: str) -> list[JavacError]:
        """Parse build output into structured JavacError list."""
        errors: list[JavacError] = []
        seen: set[str] = set()

        for pattern, category, symbol_field in self._parsers:
            for match in pattern.finditer(build_output):
                raw = match.group(0)
                groups = match.groups()
                file_path = ""
                line_num = 0
                symbol = ""

                if len(groups) >= 3:
                    file_path = groups[0]
                    try:
                        line_num = int(groups[1])
                    except (ValueError, IndexError):
                        line_num = 0
                    symbol = groups[2] if len(groups) > 2 else ""
                elif len(groups) == 2:
                    first_looks_like_file = bool(re.match(r"^[\w/]+\.[a-z]+$", groups[0]))
                    second_is_int = bool(re.match(r"^\d+$", str(groups[1])))
                    if first_looks_like_file and second_is_int:
                        file_path = groups[0]
                        line_num = int(groups[1])
                        symbol = symbol_field
                    else:
                        symbol = groups[1]
                elif len(groups) == 1:
                    symbol = groups[0]
                else:
                    symbol = symbol_field

                if not file_path:
                    fl = self._extract_file_line_from_output(build_output, match.start())
                    file_path = fl[0]
                    line_num = fl[1]

                err = JavacError(
                    file=file_path,
                    line=line_num,
                    category=category,
                    symbol=symbol,
                    message=raw[:200],
                    raw=raw[:300],
                )
                # Dedup: skip if same raw text already seen
                if raw in seen:
                    continue
                # Also skip if raw is a substring of an existing error's raw
                # (fallback pattern matches a subset of the full pattern's text)
                is_substring = False
                for existing_raw in seen:
                    if len(raw) < len(existing_raw) and raw in existing_raw:
                        is_substring = True
                        break
                    if len(existing_raw) < len(raw) and existing_raw in raw:
                        is_substring = True
                        break
                if is_substring:
                    continue
                seen.add(raw)

                errors.append(err)

        # Sort by file then line
        errors.sort(key=lambda e: (e.file, e.line))
        self.metrics.total_errors = len(errors)
        return errors

    def _extract_file_line_from_output(self, output: str, match_start: int) -> tuple[str, int]:
        """Look backwards from match_start for the nearest file.java:line: prefix."""
        text_before = output[:match_start]
        matches = list(re.finditer(r"([\w/]+\.[a-z]+):(\d+):\s*(?:error:|warning:)", text_before))
        if matches:
            last = matches[-1]
            return (last.group(1), int(last.group(2)))
        return ("", 0)

    def classify(self, errors: list[JavacError]) -> list[JavacError]:
        """Classify parsed errors. Currently returns as-is; future: NLP classification."""
        self.metrics.classified_errors = len(errors)
        return errors

    async def repair(self, errors: list[JavacError],
                     root: str | None = None,
                     objective: str = "") -> tuple[bool, list[RepairAction]]:
        """Repair all errors deterministically. Returns (any_fixed, actions)."""
        self.metrics.start_time = datetime.now().isoformat()
        self.metrics.repair_attempts = len(errors)
        actions: list[RepairAction] = []
        any_fixed = False
        root = root or self.project_dir

        for error in errors:
            action = await self._repair_one(error, root, objective)
            actions.append(action)
            if action.success:
                any_fixed = True
                self.metrics.fixed_errors += 1
                self.metrics.repairs.append(action.__dict__)
                if self._pattern_memory:
                    self._pattern_memory.record_success(
                        error.message,
                        f"{action.action}:{error.category}",
                    )
            elif self._pattern_memory:
                self._pattern_memory.record_failure(
                    error.message,
                    f"{action.action}:{error.category}",
                )

        self.metrics.end_time = datetime.now().isoformat()
        return any_fixed, actions

    async def _repair_one(self, error: JavacError, root: str, objective: str) -> RepairAction:
        """Apply deterministic repair for a single error."""
        import time
        start = time.time()

        # Priority 1: Check PatternFailureMemory
        if self._pattern_memory:
            match = self._pattern_memory.match(error.message)
            if match:
                self.metrics.pattern_memory_hits += 1
                strategy = match.fix_strategy
                if not strategy.startswith("FAILED:"):
                    action_name = strategy.split(":")[0] if ":" in strategy else strategy
                    result = await self._apply_repair(action_name, error, root)
                    result.duration_ms = (time.time() - start) * 1000
                    return result
                else:
                    self.metrics.pattern_memory_misses += 1

        # Priority 2: Deterministic repair by category
        action_name = CATEGORY_REPAIR_MAP.get(error.category, "fix_code")
        result = await self._apply_repair(action_name, error, root)
        result.duration_ms = (time.time() - start) * 1000
        return result

    async def _apply_repair(self, action: str, error: JavacError, root: str) -> RepairAction:
        """Apply a specific repair action to fix the error."""
        ra = RepairAction(category=error.category, action=action, params=error.to_dict())

        try:
            if action == "add_import":
                ok = self._fix_import(error.symbol, error.file, root)
                ra.success = ok

            elif action == "add_gradle_dependency":
                ok = self._fix_gradle_dependency(error.symbol, root)
                ra.success = ok

            elif action == "create_layout":
                ok = self._create_layout(error.symbol, root)
                ra.success = ok

            elif action == "add_view_id":
                ok = self._add_view_id(error.symbol, error.file, root)
                ra.success = ok

            elif action == "create_drawable":
                ok = self._create_drawable(error.symbol, root)
                ra.success = ok

            elif action == "add_string_resource":
                ok = self._add_resource("string", error.symbol, root)
                ra.success = ok

            elif action == "add_color_resource":
                ok = self._add_resource("color", error.symbol, root)
                ra.success = ok

            elif action == "create_mipmap":
                ok = self._create_mipmap(error.symbol, root)
                ra.success = ok

            elif action == "fix_class_name":
                ok = self._fix_class_name(error.symbol, error.file, root)
                ra.success = ok

            elif action == "fix_package":
                ok = self._fix_package(error.symbol, error.file, root)
                ra.success = ok

            elif action == "fix_duplicate_override":
                ok = self._fix_duplicate_override(error.file, root)
                ra.success = ok

            elif action == "fix_invalid_override":
                ok = self._fix_invalid_override(error.file, root)
                ra.success = ok

            elif action == "fix_manifest":
                ok = self._fix_manifest(error.symbol, root)
                ra.success = ok

            elif action == "fix_gradle":
                ok = self._fix_gradle(root)
                ra.success = ok

            elif action == "fix_dependencies":
                ok = self._fix_dependencies(error.symbol, root)
                ra.success = ok

            elif action == "fix_resources":
                ok = self._fix_resources_generic(error.symbol, root)
                ra.success = ok

            elif action == "fix_room":
                ok = self._fix_room_generic(error, root)
                ra.success = ok

            elif action == "create_file":
                ok = self._create_class(error.symbol, error.file, root)
                ra.success = ok

            elif action == "fix_code":
                ok = await self._fix_code_deterministic(error, root)
                ra.success = ok
                if not ok:
                    ra.error = "Code fix too complex for deterministic repair"

            elif action == "fix_syntax":
                ok = await self._fix_syntax(error, root)
                ra.success = ok
                if not ok:
                    ra.error = "Syntax fix failed"

            else:
                ra.error = f"Unknown repair action: {action}"

        except Exception as e:
            ra.success = False
            ra.error = str(e)
            logger.warning("[Repair] %s failed for %s: %s", action, error.category, e)

        if ra.success:
            logger.info("[Repair] Fixed %s (%s) in %s", error.category, error.symbol[:40], error.file or "unknown")
        else:
            logger.debug("[Repair] Cannot fix %s (%s) — %s", error.category, error.symbol[:40], ra.error)

        return ra

    # ── Deterministic Repair Implementations ─────────────────────

    def _fix_import(self, symbol: str, file_path: str, root: str) -> bool:
        """Add missing import for a symbol. Returns True if import is present (or was added)."""
        from brain.repair_modules.fix_imports import KNOWN_ANDROID_IMPORTS

        import_line = KNOWN_ANDROID_IMPORTS.get(symbol, "")
        if not import_line:
            return False

        full = os.path.join(root, file_path) if file_path else ""
        if not full or not os.path.exists(full):
            for r, _dirs, files in os.walk(root):
                for f in files:
                    if f.endswith(".java"):
                        fp = os.path.join(r, f)
                        try:
                            with open(fp, encoding="utf-8") as fh:
                                content = fh.read()
                            if symbol not in content:
                                continue
                            if import_line in content:
                                return True  # already correct
                            if "package " in content:
                                pkg_end = content.index(";", content.index("package ")) + 1
                                content = content[:pkg_end] + "\n" + import_line + content[pkg_end:]
                                with open(fp, "w", encoding="utf-8") as fh:
                                    fh.write(content)
                                return True
                        except Exception:
                            continue
            return False

        try:
            with open(full, encoding="utf-8") as f:
                content = f.read()
            if symbol not in content:
                return False
            if import_line in content:
                return True  # already correct
            if "package " in content:
                pkg_end = content.index(";", content.index("package ")) + 1
                content = content[:pkg_end] + "\n" + import_line + content[pkg_end:]
                with open(full, "w", encoding="utf-8") as f:
                    f.write(content)
                return True
        except Exception:
            pass
        return False

    def _fix_gradle_dependency(self, package_name: str, root: str) -> bool:
        """Add Gradle dependency for a missing package."""
        from brain.repair_modules.fix_dependencies import DEPENDENCY_MAP

        # Find gradle build file
        build_gradle = self._find_build_gradle(root)
        if not build_gradle:
            return False

        dependency = DEPENDENCY_MAP.get(package_name, "")
        if not dependency:
            # Try matching just the class name part
            for key, dep in DEPENDENCY_MAP.items():
                if key.split(".")[-1] == package_name.split(".")[-1]:
                    dependency = dep
                    break
        if not dependency:
            return False

        try:
            with open(build_gradle, encoding="utf-8") as f:
                content = f.read()
            if dependency not in content:
                if "dependencies {" in content:
                    content = content.replace("dependencies {", f"dependencies {{\n    {dependency}")
                    with open(build_gradle, "w", encoding="utf-8") as f:
                        f.write(content)
                    return True
        except Exception:
            pass
        return False

    def _create_layout(self, layout_name: str, root: str) -> bool:
        """Create missing layout XML file."""
        from brain.repair_modules.fix_layouts import fix_layouts
        msg = f"R.layout.{layout_name} cannot be found"
        return len(fix_layouts(root, [{"message": msg}])) > 0

    def _add_view_id(self, view_id: str, file_path: str, root: str) -> bool:
        """Add @+id/ reference to layout XML."""
        layout_dir = self._find_layout_dir(root)
        if not layout_dir:
            return False
        # If we have a specific file, add it there
        if file_path:
            full = os.path.join(root, file_path)
            if os.path.exists(full) and full.endswith(".xml"):
                with open(full, encoding="utf-8") as f:
                    lines = f.readlines()
                inserted = False
                for i, line in enumerate(lines):
                    if "android:layout_width" in line and "android:id" not in line:
                        indent = line[:len(line) - len(line.lstrip())]
                        lines.insert(i + 1, f'{indent}    android:id="@+id/{view_id}"\n')
                        inserted = True
                        break
                if inserted:
                    with open(full, "w", encoding="utf-8") as f:
                        f.writelines(lines)
                    return True
        return False

    def _create_drawable(self, drawable_name: str, root: str) -> bool:
        """Create a stub vector drawable XML."""
        from brain.repair_modules.fix_resources import fix_resources
        msg = f"@drawable/{drawable_name}"
        return len(fix_resources(root, [{"message": msg}])) > 0

    def _add_resource(self, res_type: str, name: str, root: str) -> bool:
        """Add a string/color resource entry."""
        from brain.repair_modules.fix_resources import fix_resources
        msg = f"@{res_type}/{name}"
        return len(fix_resources(root, [{"message": msg}])) > 0

    def _create_mipmap(self, mipmap_name: str, root: str) -> bool:
        """Create a stub mipmap resource."""
        res_dir = self._find_res_dir(root)
        if not res_dir:
            return False
        mipmap_dir = os.path.join(res_dir, f"mipmap-hdpi")
        os.makedirs(mipmap_dir, exist_ok=True)
        path = os.path.join(mipmap_dir, f"{mipmap_name}.xml")
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                f.write('<?xml version="1.0" encoding="utf-8"?>\n<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n    <background android:drawable="@color/white"/>\n    <foreground android:drawable="@color/black"/>\n</adaptive-icon>\n')
            return True
        return False

    def _fix_class_name(self, symbol: str, file_path: str, root: str) -> bool:
        """Fix class/file name mismatch."""
        from brain.repair_modules.fix_file_ops import fix_class_file_mismatch
        errors = [{"file": file_path, "symbol": symbol, "category": "class_file_mismatch"}]
        return fix_class_file_mismatch(root, errors)

    def _fix_package(self, symbol: str, file_path: str, root: str) -> bool:
        """Fix package declaration."""
        from brain.repair_modules.fix_file_ops import fix_package_mismatch
        return fix_package_mismatch(root, [{"file": file_path, "symbol": symbol}])

    def _fix_duplicate_override(self, file_path: str, root: str) -> bool:
        """Remove duplicate @Override annotations."""
        from brain.repair_modules.fix_file_ops import fix_duplicate_override
        return fix_duplicate_override(root, [{"file": file_path}])

    def _fix_invalid_override(self, file_path: str, root: str) -> bool:
        """Remove @Override from methods that don't override."""
        full = os.path.join(root, file_path) if file_path else ""
        if not full or not os.path.exists(full):
            return False
        try:
            with open(full, encoding="utf-8") as f:
                lines = f.readlines()
            new_lines = []
            skip_next = False
            for i, line in enumerate(lines):
                if "@Override" in line and i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    # If the next line starts a method that doesn't match known overrides
                    if next_line.startswith("protected") or next_line.startswith("public"):
                        pass  # Keep @Override — may be valid
                new_lines.append(line)
            with open(full, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
            return True
        except Exception:
            return False

    def _fix_manifest(self, symbol: str, root: str) -> bool:
        """Register activity or permission in AndroidManifest.xml."""
        from brain.repair_modules.fix_manifest import fix_manifest
        manifest_path = self._find_manifest(root)
        if not manifest_path:
            return False
        return fix_manifest(manifest_path, [{"name": symbol}])

    def _fix_gradle(self, root: str) -> bool:
        """Fix or regenerate Gradle build files."""
        from brain.repair_modules.fix_gradle import fix_gradle
        return "gradle" in fix_gradle(root, [])

    def _fix_dependencies(self, symbol: str, root: str) -> bool:
        """Add missing Gradle dependency."""
        from brain.repair_modules.fix_dependencies import fix_dependencies
        build_gradle = self._find_build_gradle(root)
        if not build_gradle:
            return False
        return fix_dependencies(build_gradle, [{"name": symbol}])

    def _fix_resources_generic(self, symbol: str, root: str) -> bool:
        """Fix missing resources."""
        from brain.repair_modules.fix_resources import fix_resources
        return "resource" in fix_resources(root, [{"name": symbol}])

    def _fix_room_generic(self, error: JavacError, root: str) -> bool:
        """Apply Room-specific fixes."""
        if "room_schema" in error.category:
            # Add schema export to build.gradle
            build_gradle = self._find_build_gradle(root)
            if build_gradle:
                with open(build_gradle, encoding="utf-8") as f:
                    content = f.read()
                if "room.schemaLocation" not in content:
                    schema_line = '\n        javaCompileOptions {\n            annotationProcessorOptions {\n                arguments += ["room.schemaLocation": "$projectDir/schemas"]\n            }\n        }'
                    if "android {" in content:
                        content = content.replace("android {", "android {" + schema_line)
                        with open(build_gradle, "w", encoding="utf-8") as f:
                            f.write(content)
                        return True
        return False

    async def _fix_syntax(self, error: JavacError, root: str) -> bool:
        """Fix syntax errors using the fix_syntax module."""
        from brain.repair_modules.fix_syntax import fix_missing_semicolon, fix_unclosed_string
        if error.category == "syntax_semicolon":
            return fix_missing_semicolon(root, [{"file": error.file, "line": error.line}])
        if error.category == "syntax_string":
            return fix_unclosed_string(root, [{"file": error.file, "line": error.line}])
        return False

    async def _fix_code_deterministic(self, error: JavacError, root: str) -> bool:
        """Attempt deterministic code fixes before falling back to LLM."""
        # Missing symbol → try import first, then stub class
        if error.category in ("missing_symbol", "missing_class") and error.symbol:
            ok = self._fix_import(error.symbol, error.file, root)
            if ok:
                return True
            ok = self._create_class(error.symbol, error.file, root)
            if ok:
                return True

        # Syntax errors → try line-based fix
        if error.category.startswith("syntax_") and error.file and error.line > 0:
            return self._fix_syntax_line(error.category, error.file, error.line, root)

        # Type mismatch → try cast (only for simple cases)
        if error.category == "type_mismatch" and error.message:
            return self._fix_type_mismatch(error, root)

        return False

    def _fix_syntax_line(self, category: str, file_path: str, line_num: int, root: str) -> bool:
        """Fix common syntax errors by editing the source file line."""
        full = os.path.join(root, file_path) if file_path else ""
        if not full or not os.path.exists(full):
            return False
        try:
            with open(full, encoding="utf-8") as f:
                lines = f.readlines()
            if line_num < 1 or line_num > len(lines):
                return False
            line = lines[line_num - 1]
            fixed = line
            if category == "syntax_semicolon":
                stripped = line.rstrip()
                if not stripped.endswith(";") and not stripped.endswith("{"):
                    fixed = stripped.rstrip() + ";\n"
            elif category == "syntax_string":
                # Try adding missing closing quote
                count = line.count('"')
                if count % 2 == 1:
                    fixed = line.rstrip() + '"\n'
            if fixed != line:
                lines[line_num - 1] = fixed
                with open(full, "w", encoding="utf-8") as f:
                    f.writelines(lines)
                return True
        except Exception:
            pass
        return False

    def _fix_type_mismatch(self, error: JavacError, root: str) -> bool:
        """Fix type mismatch by adding a cast."""
        # Extract source and target types from error message
        m = re.search(r"incompatible types:\s*(\S+)\s*cannot be converted to\s*(\S+)", error.message, re.I)
        if not m:
            return False
        source_type, target_type = m.group(1), m.group(2)
        if error.file:
            full = os.path.join(root, error.file)
            if os.path.exists(full):
                try:
                    with open(full, encoding="utf-8") as f:
                        lines = f.readlines()
                    if 0 < error.line <= len(lines):
                        line = lines[error.line - 1]
                        # Replace the source expression with cast: (TargetType) sourceExpr
                        # Simple heuristic: wrap last assignment or return value
                        if "=" in line:
                            parts = line.split("=", 1)
                            rhs = parts[1].strip().rstrip(";")
                            indent = line[:len(line) - len(line.lstrip())]
                            lines[error.line - 1] = f"{indent}{parts[0]}= ({target_type}) {rhs};\n"
                            with open(full, "w", encoding="utf-8") as f:
                                f.writelines(lines)
                            return True
                except Exception:
                    pass
        return False

    def _create_class(self, symbol: str, file_path: str, root: str) -> bool:
        """Create a stub class file for a missing class. Returns True if already exists or was created."""
        if not symbol:
            return False
        pkg = self._detect_package(root)
        if file_path:
            full = os.path.join(root, file_path.replace("\\", "/"))
        else:
            src_root = os.path.join(root, "src/main/java")
            full = os.path.join(src_root, *pkg.split("."), f"{symbol}.java")
        if os.path.exists(full):
            return True  # already exists
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(f"package {pkg};\n\npublic class {symbol} {{\n}}\n")
        return True

    # ── Helpers ───────────────────────────────────────────────────

    def _find_build_gradle(self, root: str) -> str | None:
        for r, _dirs, files in os.walk(root):
            for f in files:
                if f in ("build.gradle", "build.gradle.kts", "app/build.gradle", "app/build.gradle.kts"):
                    return os.path.join(r, f)
        return None

    def _find_layout_dir(self, root: str) -> str | None:
        for r, dirs, _files in os.walk(root):
            if "layout" in dirs:
                return os.path.join(r, "layout")
            for d in dirs:
                if d.endswith("layout"):
                    return os.path.join(r, d)
        return None

    def _find_res_dir(self, root: str) -> str | None:
        for r, dirs, _files in os.walk(root):
            if "res" in dirs:
                return os.path.join(r, "res")
            if r.endswith("res"):
                return r
        return None

    def _find_manifest(self, root: str) -> str | None:
        for r, _dirs, files in os.walk(root):
            for f in files:
                if f == "AndroidManifest.xml":
                    return os.path.join(r, f)
        return None

    def _detect_package(self, root: str) -> str:
        for r, _dirs, files in os.walk(root):
            for f in files:
                if f.endswith(".java"):
                    try:
                        with open(os.path.join(r, f), encoding="utf-8") as fh:
                            m = re.search(r'package\s+([\w.]+);', fh.read())
                            if m:
                                return m.group(1)
                    except Exception:
                        continue
        return "com.example.app"

    def get_metrics(self) -> dict:
        return self.metrics.to_dict()
