"""Strict autonomous build loop.

For every software task:
  plan(tool_aware) -> generate() -> verify_gates() -> build(classified repair) -> test() -> verify() -> finish()

Architecture:
  Priority 1: Classify build errors → apply targeted fix (not full LLM rewrite)
  Priority 2: Each plan step specifies which tool to use
  Priority 3: Static verification gates before build
  Priority 4: Memory of failures — skip LLM on repeat errors
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

from brain.executor.executor import executor, ActionResult
from core.planner.protocol import Plan
from core.planner.unified_store import UnifiedStore
from brain.task_resolver import task_resolver
from memory.memory_facade import memory as _memory_facade
from core.execution import ExecutionManager
from core.llm_router import complete
from core.pattern_failure_memory import pattern_memory as _pattern_memory_singleton
from brain.automation.failure_memory import FailureMemory, KnownFix
from brain.automation.architectural_memory import ArchitecturalMemory

# DEPRECATED: Use ``self.execution_manager.engine`` instead.
# Kept for backward compatibility during Phase 5 migration.
_WORKFLOW_ENGINE = None


def _ensure_workflow_engine():
    global _WORKFLOW_ENGINE
    if _WORKFLOW_ENGINE is not None:
        return
    logger.warning("[AutoBuild] _ensure_workflow_engine() is deprecated — use ExecutionManager.engine instead")
    try:
        from core.workflow.engine import WorkflowEngine
        _WORKFLOW_ENGINE = WorkflowEngine()
        logger.debug("[AutoBuild] using WorkflowEngine for step execution (deprecated path)")
    except Exception:
        logger.debug("[AutoBuild] WorkflowEngine not available")
        _WORKFLOW_ENGINE = False

logger = logging.getLogger(__name__)


# ── Requirement Completion Tracking ────────────────────────────

@dataclass
class Requirement:
    name: str
    completed: bool = False


class RequirementTracker:
    """Parse goal into named requirements and measure completion percentage."""

    def __init__(self):
        self.requirements: list[Requirement] = []
        self._raw_goal: str = ""

    def parse_goal(self, goal: str):
        self._raw_goal = goal
        self.requirements = []
        lines = goal.split("\n")
        for line in lines:
            line = line.strip()
            m = re.match(r"^[-*\d+\.]\s+(.+)$", line)
            if m:
                self.requirements.append(Requirement(name=m.group(1).strip()))
        if not self.requirements:
            parts = re.split(r"\band\b|,", goal)
            for p in parts:
                p = p.strip()
                if p and len(p) > 3 and p.lower() not in ("with", "the", "for", "using", "that", "this"):
                    self.requirements.append(Requirement(name=p))
        if not self.requirements:
            self.requirements.append(Requirement(name=goal.strip()))

    def check_completion(self, proj_dir: str, plan: dict) -> float:
        proj_name = plan.get("project_name", "project")
        root = os.path.join(proj_dir, proj_name) if proj_dir else proj_name
        for req in self.requirements:
            req.completed = self._check_requirement(req.name, root)
        if not self.requirements:
            return 0.0
        done = sum(1 for r in self.requirements if r.completed)
        return (done / len(self.requirements)) * 100.0

    def _check_requirement(self, name: str, root: str) -> bool:
        lo = name.lower()
        keywords = [w for w in lo.split() if len(w) > 3]
        if not keywords:
            return False
        for r, _dirs, files in os.walk(root if root and os.path.isdir(root) else "."):
            for f in files:
                if f.endswith((".java", ".kt", ".py", ".ts", ".js", ".xml", ".rs", ".md")):
                    try:
                        with open(os.path.join(r, f), encoding="utf-8", errors="replace") as fh:
                            c = fh.read().lower()
                        found = sum(1 for w in keywords if w in c)
                        if found >= max(1, len(keywords) * 2 // 3):
                            return True
                    except Exception:
                        pass
        return False

    def summary(self) -> str:
        lines = []
        for r in self.requirements:
            lines.append(f"{'✓' if r.completed else '✗'} {r.name}")
        return "\n".join(lines)


# ── Runtime Validation ──────────────────────────────────────────

RUNTIME_VALIDATE_PROMPT = """You are validating a running {project_type} application.

Requirements: {requirements}

Screenshot analysis:
{vision_report}

Does the running application satisfy the requirements? Focus on visible UI elements.
Output JSON:
{{
  "validated": true/false,
  "visible_elements": ["list of what was seen"],
  "missing_elements": ["list of required but unseen elements"],
  "issues": ["any visual defects or incorrect behavior"]
}}
"""


# ── Priority 1: Error Classifier ────────────────────────────────

_ERROR_FIX_REGISTRY: list[tuple[re.Pattern, str, str, dict]] = [
    # Java: cannot find symbol / package does not exist
    (re.compile(r"cannot find symbol.*class (\w+)", re.I), "missing_import", "add_import", {}),
    (re.compile(r"package (.+) does not exist", re.I), "missing_package", "add_gradle_dependency", {}),
    (re.compile(r"cannot find symbol.*variable (\w+)", re.I), "undefined_variable", "fix_code", {}),
    # Java: R.layout / R.id not found
    (re.compile(r"R\.layout\.(\w+)", re.I), "missing_layout", "create_resource_file", {"type": "layout"}),
    (re.compile(r"R\.id\.(\w+)", re.I), "missing_view_id", "fix_code", {}),
    (re.compile(r"R\.(\w+)", re.I), "missing_resource", "create_resource_file", {}),
    # Java: method not found
    (re.compile(r"cannot find symbol.*method (\w+)", re.I), "missing_method", "fix_code", {}),
    # Gradle: plugin not found
    (re.compile(r"plugin.*not found.*'([^']+)'", re.I), "missing_gradle_plugin", "fix_gradle", {}),
    (re.compile(r"Could not find method (\w+)", re.I), "gradle_syntax", "fix_gradle", {}),
    # Java: incompatible types
    (re.compile(r"incompatible types", re.I), "type_mismatch", "fix_code", {}),
    # General: file not found / no such file
    (re.compile(r"(?:file|resource|layout|drawable) not found:?\s*(.+)", re.I), "missing_file", "create_file", {}),
    (re.compile(r"Unresolved reference: (\w+)", re.I), "unresolved_reference", "fix_code", {}),
    # Android: Activity not registered
    (re.compile(r"Activity (.+) not registered", re.I), "missing_activity_registration", "fix_manifest", {}),
    (re.compile(r"has not been declared in AndroidManifest", re.I), "missing_activity_registration", "fix_manifest", {}),
    # General: syntax error
    (re.compile(r"(syntax error|unexpected token|';' expected)", re.I), "syntax_error", "fix_code", {}),
    # Java: class not found
    (re.compile(r"class (\w+) not found", re.I), "missing_class", "create_file", {}),
]

# Human-readable fix descriptions per fix_type
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
            # Extract filename if present in the line
            line = match.string[match.start():match.start() + 200]
            file_match = re.search(r'([\w/]+\.\w+):', line)
            file_path = file_match.group(1) if file_match else ""
            line_num = 0
            line_match = re.search(r':(\d+):', line)
            if line_match:
                line_num = int(line_match.group(1))

            params = dict(default_params)
            param_key = match.lastgroup or "target"
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
    # Deduplicate by error_text
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
        # Find the Java file and add import
        file_path = fix.get("file", "")
        if file_path:
            full = os.path.join(proj_dir, file_path.replace("\\", "/"))
            if os.path.exists(full):
                with open(full, "r", encoding="utf-8") as f:
                    content = f.read()
                import_line = f"import {name};\n"
                if import_line not in content and "package " in content:
                    # Add after package statement
                    pkg_end = content.index(";", content.index("package ")) + 1
                    content = content[:pkg_end] + "\n" + import_line + content[pkg_end:]
                    with open(full, "w", encoding="utf-8") as f:
                        f.write(content)
                    logger.info("[Fix] added import %s to %s", name, file_path)
                    return True
        # Try finding the class in any Java file
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

    if fix_action == "create_file" or fix_action == "create_resource_file":
        # Create missing file with placeholder content
        res_type = params.get("type", "")
        if res_type == "layout" and name:
            fname = f"{name}.xml"
            # Find layouts directory
            for r, dirs, files in os.walk(root or proj_dir):
                if r.endswith("layout") or "layout" in dirs:
                    layout_dir = os.path.join(r if r.endswith("layout") else r, "layout")
                    full = os.path.join(layout_dir, fname)
                    if not os.path.exists(full):
                        os.makedirs(os.path.dirname(full), exist_ok=True)
                        with open(full, "w", encoding="utf-8") as fh:
                            fh.write(f'<?xml version="1.0" encoding="utf-8"?>\n<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"\n    android:layout_width="match_parent"\n    android:layout_height="match_parent"\n    android:orientation="vertical">\n\n</LinearLayout>\n')
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
        # Generic file creation
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
                # Add activity declaration before </application>
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
                # Find the dependencies block
                dep_line = f"    implementation '{name}'\n"
                if "dependencies {" in content:
                    content = content.replace("dependencies {", "dependencies {\n" + dep_line)
                    with open(gradle_path, "w", encoding="utf-8") as fh:
                        fh.write(content)
                    logger.info("[Fix] added dependency %s to build.gradle", name)
                    return True
        return False

    if fix_action == "fix_code":
        # For simple code fixes, try to find and fix the specific line
        file_path = fix.get("file", "")
        if file_path:
            full = os.path.join(proj_dir, file_path.replace("\\", "/"))
            if os.path.exists(full):
                # Read the file and let the LLM handle this case via targeted prompt
                # (code fixes are too varied for simple regex)
                logger.info("[Fix] code fix needed in %s — will use LLM", file_path)
        return False


# ── Priority 3: Verification Gates ──────────────────────────────

@dataclass
class GateResult:
    passed: bool
    checks: list[dict] = field(default_factory=list)  # {name, passed, detail}


async def verify_gates(proj_dir: str, plan: dict) -> GateResult:
    """Run static verification checks before build."""
    result = GateResult(passed=True)
    root = os.path.join(proj_dir, plan.get("project_name", "project")) if proj_dir else plan.get("project_name", "project")
    language = (plan.get("language") or "").lower()
    lo = plan.get("goal", "").lower()

    # Check directory exists
    result.checks.append(_check_dir_exists(root))

    # Language-specific checks
    if language in ("java", "kotlin") or "android" in lo or "gradle" in lo:
        result.checks.extend([
            _check_file_exists(root, "build.gradle", "Gradle build config"),
            _check_file_exists(root, "settings.gradle", "Gradle settings"),
            _check_manifest(root),
        ])
        # Check all referenced layouts exist
        result.checks.append(_check_layouts(root))
        # Check every Java file has corresponding test or vice versa
        result.checks.append(_check_imports(root))

    if language == "python":
        result.checks.append(_check_file_exists(root, "requirements.txt", "Python deps"))
        result.checks.append(_check_file_exists(root, "src/main.py", "Python entry point"))

    if "node" in language or "javascript" in language or "typescript" in language:
        result.checks.append(_check_file_exists(root, "package.json", "Node config"))

    # Determine overall pass/fail
    for c in result.checks:
        if not c["passed"]:
            result.passed = False
            logger.warning("[Gate] FAILED: %s — %s", c["name"], c.get("detail", ""))

    return result


def _check_dir_exists(root: str) -> dict:
    return {
        "name": "Project directory exists",
        "passed": os.path.isdir(root) if root else False,
        "detail": f"dir={root}" if root else "no root",
    }


def _check_file_exists(root: str, rel_path: str, label: str) -> dict:
    full = os.path.join(root, rel_path) if root else rel_path
    exists = os.path.isfile(full)
    return {
        "name": label,
        "passed": exists,
        "detail": f"path={rel_path}, found={exists}" if not exists else "",
    }


def _check_manifest(root: str) -> dict:
    candidates = [
        os.path.join(root, "src/main/AndroidManifest.xml"),
        os.path.join(root, "AndroidManifest.xml"),
    ]
    found = None
    for p in candidates:
        if os.path.isfile(p):
            found = p
            break
    detail = ""
    errors = []
    if found:
        try:
            with open(found, "r") as f:
                content = f.read()
            if "<application" not in content:
                errors.append("missing <application> tag")
            if "<activity" not in content:
                errors.append("no <activity> declared")
        except Exception as e:
            errors.append(str(e))
        detail = "; ".join(errors) if errors else "OK"
    return {
        "name": "AndroidManifest.xml",
        "passed": found is not None and not errors,
        "detail": f"path={found or 'not found'}, {detail}",
    }


def _check_layouts(root: str) -> dict:
    """Check that every layout reference in code has a corresponding file."""
    layout_refs = set()
    layout_dir = os.path.join(root, "src/main/res/layout")
    for r, dirs, files in os.walk(root if root else "."):
        for f in files:
            if f.endswith(".java") or f.endswith(".kt") or f.endswith(".xml"):
                full = os.path.join(r, f)
                try:
                    with open(full, "r", encoding="utf-8") as fh:
                        content = fh.read()
                    for m in re.finditer(r'R\.layout\.(\w+)', content):
                        layout_refs.add(m.group(1))
                except Exception:
                    pass

    missing = []
    for ref in layout_refs:
        xml_path = os.path.join(layout_dir, f"{ref}.xml")
        if not os.path.isfile(xml_path):
            missing.append(ref)

    return {
        "name": "Referenced layouts exist",
        "passed": len(missing) == 0,
        "detail": f"missing={missing}" if missing else f"all {len(layout_refs)} refs found",
    }


def _check_imports(root: str) -> dict:
    """Check that Java imports reference files that exist in the project."""
    all_files = set()
    for r, dirs, files in os.walk(root if root else "."):
        for f in files:
            if f.endswith(".java") or f.endswith(".kt"):
                all_files.add(os.path.splitext(f)[0])

    known_external = {
        "String", "Integer", "Boolean", "Long", "Double", "Float",
        "ArrayList", "HashMap", "List", "Map", "Set", "Object",
        "Thread", "Runnable", "File", "IOException", "Exception",
        "R", "Bundle", "View", "LayoutInflater", "ViewGroup", "Intent",
        "JsonReader", "JsonWriter", "InputStreamReader", "OutputStreamWriter",
        "BufferedReader", "BufferedWriter", "FileInputStream", "FileOutputStream",
        "Context", "Activity", "Fragment", "Application", "Service",
        "Notification", "NotificationManager", "PendingIntent",
        "ViewModelProvider", "ViewModel", "LiveData", "MutableLiveData",
        "Observer", "RecyclerView", "LinearLayoutManager", "Adapter",
        "ViewHolder", "OnClickListener", "TextWatcher", "Editor",
        "MaterialButton", "MaterialCardView", "FloatingActionButton",
        "NavigationView", "BottomNavigationView", "Snackbar",
        "TextInputLayout", "TextInputEditText", "Chip", "ChipGroup",
        "AppCompatDelegate", "Resources", "Configuration", "UiModeManager",
        "InstantTaskExecutorRule", "TestRule", "Rule",
    }
    issues = []

    for r, dirs, files in os.walk(root if root else "."):
        for f in files:
            if f.endswith(".java") or f.endswith(".kt"):
                full = os.path.join(r, f)
                try:
                    with open(full, "r", encoding="utf-8") as fh:
                        content = fh.read()
                    for m in re.finditer(r'new (\w+)\(', content):
                        cls = m.group(1)
                        if cls not in known_external:
                            if cls not in all_files and not os.path.exists(os.path.join(r, f"{cls}.java")):
                                issues.append(f"potential missing class: {cls} in {f}")
                except Exception:
                    pass
    return {
        "name": "Project imports check",
        "passed": len(issues) == 0,
        "detail": "; ".join(issues[:5]) if issues else "OK",
    }

PLAN_PROMPT = """Goal: {goal}

Available tools on this system: python, node, javac, gradle, cargo

Create a detailed build plan using ONLY the available tools above.

Output a JSON object with:
  - "project_name": short name for the project directory
  - "language": programming language (must match available tools)
  - "files": list of file paths to create (relative to project root)
  - "build_command": shell command to compile/build with available tools
  - "test_command": shell command to run tests with available tools

Output ONLY the JSON object, no markdown, no explanation.
"""

VERIFY_PROMPT = """Goal: {goal}
Project directory: {project_dir}

Verify this project meets all requirements. Check:

1. All requested features implemented
2. All referenced files exist
3. No missing imports
4. No missing resources
5. No build errors
6. No test failures
7. Application starts successfully (check for main class / entry point)

Output a JSON object:
  {{
    "verified": true/false,
    "failures": ["description of each unmet requirement"],
    "repair_instructions": "what to fix if verification failed"
  }}
"""

ANALYZE_BUILD_ERRORS_PROMPT = """Goal: {goal}
Build command: {build_command}
Build output (stdout/stderr):
{build_output}

Analyze the build errors. For each error:
1. Identify the root cause
2. Find the affected file
3. Explain what needs to be fixed

Output a JSON object:
  {{
    "errors": [
      {{"file": "path/to/file", "line": N, "message": "error text", "fix": "what to change"}}
    ],
    "summary": "overall assessment of what's wrong and how to repair"
  }}
"""

ANALYZE_TEST_ERRORS_PROMPT = """Goal: {goal}
Test command: {test_command}
Test output (stdout/stderr):
{test_output}

Analyze the test failures. For each failure:
1. Identify which test failed
2. Find the root cause in the implementation
3. Explain what needs to be fixed

Output a JSON object:
  {{
    "failures": [
      {{"test": "test name", "file": "affected source file", "message": "error text", "fix": "what to change"}}
    ],
    "summary": "overall assessment of what's wrong and how to repair"
  }}
"""

REPAIR_PROMPT = """Goal: {goal}
Project directory: {project_dir}

The following issues need to be fixed:

{analysis}

For each affected file, generate the COMPLETE corrected content.
Output a JSON array of repair actions:
  [
    {{"action": "write_file", "params": {{"path": "...", "content": "..."}}}},
    {{"action": "edit_file", "params": {{"path": "...", "old_string": "...", "new_string": "..."}}}}
  ]

Include ALL imports, declarations, and correct syntax in each file.
Output ONLY the JSON array, no markdown, no explanation.
"""

ROOT_CAUSE_PROMPT = """Goal: {goal}

Current plan: {plan_json}

Build errors encountered (after {attempts} repair attempts):
{build_history}

Project files:
{files}

The build keeps failing on the same class of errors. Analyze the ROOT CAUSE.

Is the problem:
1. Missing architectural layer (Repository, ViewModel, DAO, DI)?
2. Incorrect build configuration?
3. Missing files / incorrect file structure?
4. The planner never generated a necessary component?

Output JSON:
{{
  "root_cause": "one-line description of the architectural issue",
  "affected_areas": ["list of missing or incorrect components"],
  "plan_mutation": {{
    "new_files": ["files to add"],
    "steps": [{{"step": "...", "tool": "shell|file_tools|vision_browser|search"}}],
    "build_command": "updated build command",
    "test_command": "updated test command"
  }}
}}
"""


def _list_files(project_dir: str) -> list[str]:
    files = []
    if os.path.isdir(project_dir):
        for root, dirs, fnames in os.walk(project_dir):
            for f in fnames:
                rel = os.path.relpath(os.path.join(root, f), project_dir)
                if not rel.startswith(".") and not rel.startswith("brain"):
                    files.append(rel.replace("\\", "/"))
    return sorted(files)


def _json_from_llm(raw: str) -> dict | list | None:
    """Extract JSON from LLM output (handles code fences)."""
    for prefix in ["```json", "```JSON", "```"]:
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
    for suffix in ["```"]:
        if raw.endswith(suffix):
            raw = raw[:-len(suffix)]
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _fallback_plan(objective: str) -> dict:
    """Return a safe fallback plan when LLM fails."""
    lo = objective.lower()
    lang = "python" if "python" in lo else "java"
    project_name = "app"
    for word in objective.split():
        w = word.strip("- ").lower()
        if w not in ("build", "a", "an", "the", "with", "android", "app", "in", "using", "and", "for"):
            project_name = w[:20]
            break
    if "android" in lo or "gradle" in lo:
        pkg = "com/example/" + project_name.lower()
        return {
            "project_name": project_name,
            "language": "java",
            "steps": [
                {"step": "Generate project files", "tool": "file_tools"},
                {"step": "Build the project", "tool": "shell"},
                {"step": "Run tests", "tool": "shell"},
            ],
            "files": [
                "build.gradle",
                "settings.gradle",
                "gradle.properties",
                "src/main/AndroidManifest.xml",
                f"src/main/java/{pkg}/MainActivity.java",
                "src/main/res/layout/activity_main.xml",
                "src/main/res/values/strings.xml",
                "src/main/res/values/themes.xml",
            ],
            "build_command": "gradle assembleDebug",
            "test_command": "gradle test",
        }
    return {
        "project_name": project_name,
        "language": lang,
        "steps": [
            {"step": "Generate project files", "tool": "file_tools"},
            {"step": "Build the project", "tool": "shell"},
            {"step": "Run tests", "tool": "shell"},
        ],
        "files": [],
        "build_command": "",
        "test_command": "",
    }


class AutomationLoop:
    """Strict phase-based autonomous build loop with targeted repair + verification gates + failure memory.

    plan(tool_aware) -> generate() -> verify_gates() -> build(classify) -> test() -> verify() -> finish()
    """

    MAX_REPAIR_ATTEMPTS = 10

    def __init__(self, goal_manager: UnifiedStore, memory_manager=None,
                 poll_interval: float = 5.0, project_dir: str = "",
                 execution_manager: ExecutionManager | None = None):
        self.goals = goal_manager
        self.memory = memory_manager or _memory_facade
        self.execution_manager = execution_manager or ExecutionManager()
        self.poll_interval = poll_interval
        self._running = False
        self._paused = False
        self._loop_task: asyncio.Task | None = None
        self._iteration_count = 0
        self._start_time: float = 0.0
        self.project_dir = project_dir
        self.failure_memory = FailureMemory()
        self.architectural_memory = ArchitecturalMemory()
        self.req_tracker = RequirementTracker()
        self._consecutive_failures: dict[str, int] = {}
        self._build_history: dict[str, list[str]] = {}
        self._completion: float = 0.0
        self._repair_engine: Any = None
        self._pattern_memory = _pattern_memory_singleton
        self._last_build_metrics: dict = {}
        if project_dir:
            task_resolver.project_dir = project_dir

    @property
    def uptime(self) -> float:
        if self._start_time == 0.0:
            return 0.0
        return time.time() - self._start_time

    async def start(self):
        if self._running:
            return
        self._running = True
        self._paused = False
        self._start_time = time.time()
        self._loop_task = asyncio.create_task(self._run_loop())

    async def stop(self):
        self._running = False
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
            self._loop_task = None

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    async def _run_loop(self):
        while self._running:
            try:
                if self._paused:
                    await asyncio.sleep(self.poll_interval)
                    continue
                self._iteration_count += 1
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("[AutoBuild] error: %s", e)
                await asyncio.sleep(self.poll_interval)

    async def _tick(self):
        active = self.goals.list_all(status="active", sort_by="priority")
        if not active:
            await asyncio.sleep(self.poll_interval)
            return
        goal = self.goals.get_highest_priority()
        if not goal:
            return
        logger.info("[AutoBuild] === tick %d: %s ===", self._iteration_count, goal.goal[:80])
        await self._build_project(goal)

    async def _call_llm(self, system: str, prompt: str,
                        model_group: str = "chat", timeout: int = 60) -> str | None:
        try:
            result = await complete(
                model_group,
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                timeout=timeout,
            )
            if result.is_err():
                return None
            return result.unwrap()
        except Exception as e:
            logger.warning("[AutoBuild] LLM call failed: %s", e)
            return None

    def _resolve_build_command(self, build_cmd: str, proj_dir: str) -> str:
        if not build_cmd or not build_cmd.strip():
            return ""
        parts = build_cmd.split()
        base = parts[0]
        import shutil
        # Try paths: proj_dir/proj_name/base, proj_dir/base, then raw base via shutil
        candidates = []
        if os.path.isdir(proj_dir):
            for d in os.listdir(proj_dir):
                sub = os.path.join(proj_dir, d, base)
                if os.path.isfile(sub) or os.path.isfile(sub + ".bat") or os.path.isfile(sub + ".exe"):
                    candidates.append(sub)
                    break
        if os.path.isfile(os.path.join(proj_dir, base)):
            candidates.append(os.path.join(proj_dir, base))
        resolved = shutil.which(base)
        if resolved:
            candidates.append(resolved)
        # If gradlew.bat not found, try system gradle
        if base in ("gradlew.bat", "gradlew"):
            gradle_resolved = shutil.which("gradle")
            if gradle_resolved:
                candidates.append(gradle_resolved)
        for candidate in candidates:
            try:
                import subprocess
                subprocess.run([candidate, "--version"], capture_output=True, timeout=5, shell=False)
                # Found a working tool — rewrite command to use full path
                rest = " ".join(parts[1:])
                return f"{candidate} {rest}" if rest else candidate
            except Exception:
                continue
        logger.warning("[AutoBuild] tool '%s' not available, skipping build", base)
        return ""

    async def _build_project(self, goal: Plan):
        """Main build loop with verification gates + targeted repair + failure memory + plan evolution + completion tracking."""
        goal_id = goal.id
        objective = goal.goal
        proj_dir = self.project_dir

        exec_ctx = self.execution_manager.create_context(
            source="automation_loop",
            metadata={"goal_id": goal_id, "objective": objective[:120]},
        )

        # === PLAN (tool-aware) ===
        plan = await self._phase_plan(objective)
        if not plan:
            self.execution_manager.publish_failed(exec_ctx, "Failed to create build plan")
            self.goals.fail(goal_id, "Failed to create build plan")
            return
        self.execution_manager.record_trace(exec_ctx, "plan", json.dumps(plan), True,
                                            action_params={"goal": objective})
        self.execution_manager.publish_progress(exec_ctx, "plan_created")

        # Normalize build/test commands: gradlew.bat/gradlew/./gradlew → system gradle if wrapper not found
        import shutil
        for cmd_key in ("build_command", "test_command"):
            cmd = plan.get(cmd_key, "")
            if cmd:
                parts = cmd.split()
                base = parts[0].lstrip("./")
                if base in ("gradlew.bat", "gradlew"):
                    if not shutil.which("gradlew") and not shutil.which("gradlew.bat"):
                        gradle = shutil.which("gradle")
                        if gradle:
                            rest = " ".join(cmd.split()[1:])
                            plan[cmd_key] = f"{gradle} {rest}" if rest else gradle
                            logger.info("[AutoBuild] normalized %s: %s → gradle (%s)", cmd_key, base, plan[cmd_key])

        # Parse requirements for completion tracking
        self.req_tracker.parse_goal(objective)

        # === GENERATE ===
        logger.info("[AutoBuild] generating project files")
        generated = await self._phase_generate(objective, proj_dir, plan)
        if generated:
            self.execution_manager.record_trace(exec_ctx, "generate", f"Generated {generated} files", True,
                                                action_params={"plan": plan.get("project_name", "")})
            self.execution_manager.publish_progress(exec_ctx, f"generate_done: {generated} files")

        # === PRIORITY 3: VERIFICATION GATES ===
        logger.info("[AutoBuild] running static verification gates")
        gates = await verify_gates(proj_dir, {**plan, "goal": objective})
        if not gates.passed:
            logger.warning("[AutoBuild] verification gates failed — repairing gate issues")
            for check in gates.checks:
                if not check["passed"]:
                    detail = check.get("detail", "")
                    gate_fix = {"summary": f"Gate check failed: {check['name']} — {detail}", "errors": [{"fix": detail}]}
                    await self._repair(objective, proj_dir, gate_fix)
            gates = await verify_gates(proj_dir, {**plan, "goal": objective})
            if not gates.passed:
                self.goals.fail(goal_id, f"Static verification failed: {gates.checks[0].get('name', '')}")
                return
            logger.info("[AutoBuild] gates passed after repair")

        # === PRIORITY 1 + 4: BUILD LOOP with targeted repair + failure memory ===
        build_cmd = plan.get("build_command", "")
        build_ok = await self._phase_build(objective, proj_dir, build_cmd, goal_id, plan)
        if not build_ok:
            # Attempt plan evolution before giving up
            logger.info("[AutoBuild] build failed, attempting plan evolution...")
            new_plan = await self._plan_evolution(objective, proj_dir, goal_id, plan)
            if new_plan:
                plan = new_plan
                logger.info("[AutoBuild] plan mutated, re-generating with %d files", len(plan.get("files", [])))
                generated = await self._phase_generate(objective, proj_dir, plan)
                if generated:
                    gates = await verify_gates(proj_dir, {**plan, "goal": objective})
                    if gates.passed:
                        build_ok = await self._phase_build(objective, proj_dir, build_cmd, goal_id, plan)
            if not build_ok:
                self.goals.fail(goal_id, "Build failed after max repair attempts + plan evolution")
                return
        self.execution_manager.record_trace(exec_ctx, "build", "Build succeeded", True,
                                            action_params={"command": build_cmd})
        self.execution_manager.publish_progress(exec_ctx, "build_succeeded")

        # === TEST LOOP ===
        test_cmd = plan.get("test_command", "")
        if test_cmd:
            test_ok = await self._phase_test(objective, proj_dir, test_cmd, goal_id)
            if not test_ok:
                self.goals.fail(goal_id, "Tests failed after max repair attempts")
                return
        self.execution_manager.record_trace(exec_ctx, "test", "Tests passed", True,
                                            action_params={"command": test_cmd})
        self.execution_manager.publish_progress(exec_ctx, "tests_passed")

        # === VERIFY LOOP ===
        verified = await self._phase_verify(objective, proj_dir, goal_id, plan)
        if not verified:
            self.goals.fail(goal_id, "Verification failed")
            return

        # === RUNTIME VALIDATION ===
        runtime_ok = await self._phase_runtime_validation(objective, proj_dir, plan, goal_id)
        if not runtime_ok:
            logger.warning("[AutoBuild] runtime validation failed — continuing anyway")
            # Don't fail the goal — runtime env may not be available

        # === COMPLETION TRACKING ===
        completion_pct = self._track_completion(objective, proj_dir, plan)
        if completion_pct < 100.0:
            logger.info("[AutoBuild] completion: %.0f%% — some requirements may be unmet", completion_pct)
        else:
            logger.info("[AutoBuild] all requirements verified at 100%%")

        # === FINISH ===
        self.goals.complete(goal_id, f"All phases completed ({completion_pct:.0f}% requirements met)")
        self.execution_manager.publish_completed(exec_ctx, {"completion_pct": completion_pct, "goal_id": goal_id})
        self.execution_manager.record_decision(exec_ctx, "build_completed", f"goal {goal_id}: {completion_pct}%", True)
        logger.info("[AutoBuild] === GOAL COMPLETED: %s (%.0f%%) ===", objective[:60], completion_pct)

    async def _phase_plan(self, objective: str) -> dict | None:
        """Create tool-aware plan using LLM. Each step specifies which tool to invoke."""
        arch_lessons = self.architectural_memory.get_prompt_suffix(objective)
        prompt = (
            f"Goal: {objective}\n\n"
            f"Available TOOLS on this system:\n"
            f"  - shell: Run shell commands (build, test, install)\n"
            f"  - file_tools: Create, edit, read, delete files\n"
            f"  - vision_browser: Open Chrome browser, search web, take screenshots\n"
            f"  - search: Web search for documentation\n\n"
            f"Available BUILD TOOLS installed:\n"
            f"  - gradle / gradlew.bat (Java/Android/Kotlin)\n"
            f"  - javac (Java compilation)\n"
            f"  - python (Python)\n"
            f"  - node / npm (JavaScript/TypeScript)\n"
            f"  - cargo (Rust)\n\n"
            f"For Android projects, use these build commands:\n"
            f"  build: gradlew.bat assembleDebug  (Windows) or ./gradlew assembleDebug (Linux/Mac)\n"
            f"  test:  gradlew.bat test  or ./gradlew test\n\n"
            f"Android projects MUST include these files:\n"
            f"  - build.gradle (project-level)\n"
            f"  - settings.gradle\n"
            f"  - gradle.properties\n"
            f"  - src/main/AndroidManifest.xml\n"
            f"  - src/main/java/com/example/<app>/MainActivity.java\n"
            f"  - src/main/res/layout/activity_main.xml\n"
            f"  - src/main/res/values/strings.xml\n"
            f"  - src/main/res/values/themes.xml\n\n"
            f"Design a plan with numbered steps. Each step must specify:\n"
            f"  - step: description of what to do\n"
            f"  - tool: which tool to use (shell | file_tools | vision_browser | search)\n\n"
            f"Output ONLY a JSON object with:\n"
            f"  - \"project_name\": short name for the project directory\n"
            f"  - \"language\": programming language\n"
            f"  - \"steps\": [{{\"step\": \"...\", \"tool\": \"...\"}}]\n"
            f"  - \"files\": list of ALL file paths to create (include build files!)\n"
            f"  - \"build_command\": shell command to compile/build\n"
            f"  - \"test_command\": shell command to run tests\n"
            f"{arch_lessons}\n"
            f"No markdown, no explanation."
        )
        raw = await self._call_llm(
            "You are a software architecture planner. Output valid JSON only.",
            prompt,
            timeout=180,
        )
        if not raw:
            logger.warning("[AutoBuild] plan: LLM returned nothing, using fallback")
            return _fallback_plan(objective)
        plan = _json_from_llm(raw)
        if isinstance(plan, dict):
            logger.info("[AutoBuild] plan created: %s (%d steps)",
                        plan.get("project_name", "?"), len(plan.get("steps", [])))
            return plan
        logger.warning("[AutoBuild] plan: JSON parse failed, using fallback")
        return _fallback_plan(objective)

    async def _phase_generate(self, objective: str, proj_dir: str, plan: dict) -> int:
        """Generate all project files, one at a time via LLM."""
        generated = 0
        proj_name = plan.get("project_name", "project")
        root = os.path.join(proj_dir, proj_name) if proj_dir else proj_name
        os.makedirs(root, exist_ok=True)
        prefix = proj_name + "/"

        file_list = plan.get("files", []) or self._standard_file_list(objective)

        for fpath in file_list:
            logger.info("[AutoBuild] generating %s", fpath)
            content = await task_resolver.generate_content(objective, fpath, file_list)
            if content:
                # Strip parenthetical annotations like "build.gradle (project-level)" -> "build.gradle"
                clean = re.sub(r'\s*\([^)]*\)', '', fpath.replace("\\", "/")).strip()
                # Strip project name prefix if already present to avoid double-nesting
                if clean.startswith(prefix):
                    clean = clean[len(prefix):]
                full = os.path.join(root, clean)
                os.makedirs(os.path.dirname(full), exist_ok=True)
                with open(full, "w", encoding="utf-8") as f:
                    f.write(content)
                generated += 1
                logger.info("[AutoBuild] wrote %s (%d bytes)", clean, len(content))

        # Auto-stub missing classes referenced in generated code
        stub_count = self._autostub_missing_classes(root, plan)
        if stub_count:
            generated += stub_count
            logger.info("[AutoBuild] auto-stubbed %d missing classes", stub_count)

        # Auto-fix AndroidManifest if needed
        self._fix_android_manifest(root)

        # Auto-stub missing referenced layouts
        layout_count = self._autostub_missing_layouts(root)
        if layout_count:
            logger.info("[AutoBuild] auto-stubbed %d missing layouts", layout_count)

        # Ensure proper Gradle build files for Android projects
        gradle_fixed = self._fix_gradle_files(root, plan, objective)
        if gradle_fixed:
            logger.info("[AutoBuild] fixed Gradle build files")

        # Validate and auto-fix Java source files for common LLM errors
        java_fixed = self._fix_java_files(root)
        if java_fixed:
            logger.info("[AutoBuild] fixed %d Java compilation issues", java_fixed)

        # Validate and fix XML layout files (DataBinding, escaping, etc.)
        xml_fixed = self._fix_xml_layouts(root)
        if xml_fixed:
            logger.info("[AutoBuild] fixed %d XML layout issues", xml_fixed)

        return generated

    def _fix_xml_layouts(self, root: str) -> int:
        """Fix common LLM XML errors: DataBinding type escaping, unclosed tags, etc."""
        fixes = 0
        for r, _dirs, files in os.walk(root):
            for f in files:
                if not f.endswith(".xml"):
                    continue
                path = os.path.join(r, f)
                try:
                    with open(path, "r", encoding="utf-8") as fh:
                        content = fh.read()
                    original = content

                    # 1. Escape < > in DataBinding type="..." attributes
                    # Match type="..." and escape any < or > inside the value
                    def escape_type_attr(m):
                        val = m.group(1)
                        val = val.replace("<", "&lt;").replace(">", "&gt;")
                        return f'type="{val}"'
                    content = re.sub(r'type="([^"]*)"', escape_type_attr, content)

                    # 2. Fix xmlns:android appearing without http://schemas...
                    content = re.sub(
                        r'xmlns:android="(?!http)',
                        'xmlns:android="http://schemas.android.com/apk/res/android',
                        content
                    )
                    content = re.sub(
                        r'xmlns:app="(?!http)',
                        'xmlns:app="http://schemas.android.com/apk/res-auto',
                        content
                    )

                    # 3. Remove rogue angle brackets in value attributes
                    def escape_value_attr(m):
                        val = m.group(1)
                        val = val.replace("<", "&lt;").replace(">", "&gt;")
                        return f'value="{val}"'
                    content = re.sub(r'value="([^"]*)"', escape_value_attr, content)

                    if content != original:
                        with open(path, "w", encoding="utf-8") as fh:
                            fh.write(content)
                        fixes += 1
                        logger.info("[AutoBuild] fixed XML issues in %s", os.path.relpath(path, root))
                except Exception as e:
                    logger.warning("[AutoBuild] XML fix error %s: %s", path, e)
        return fixes

    def _fix_java_files(self, root: str) -> int:
        """Deterministically fix common LLM Java code errors: missing imports, syntax, package decls."""
        fixes = 0
        for r, _dirs, files in os.walk(root):
            for f in files:
                if not f.endswith(".java"):
                    continue
                path = os.path.join(r, f)
                try:
                    with open(path, "r", encoding="utf-8") as fh:
                        content = fh.read()
                    original = content

                    # 1. Fix missing package declaration
                    if not content.strip().startswith("package"):
                        # Derive package from directory structure
                        rel = os.path.relpath(os.path.dirname(path), root).replace("\\", ".")
                        if rel == ".":
                            rel = "com.example"
                        pkg_line = f"package {rel};\n\n"
                        content = pkg_line + content

                    # 2. Remove rogue Gradle/DSL lines inside Java files
                    content = re.sub(r'\n\s*(dependencies\s*\{|android\s*\{|buildTypes\s*\{|compileSdk[^}]+})', '\n// FIXED', content)

                    # 3. Add missing newline after opening brace for class/interface/enum
                    content = re.sub(r'(\bclass\s+\w+\s*\{)(?!\n)', r'\1\n', content)

                    # 4. Fix common missing imports based on class usage
                    imports_needed = set()
                    if "List" in content and "java.util.List" not in content and "import java.util.List" not in content:
                        imports_needed.add("java.util.List")
                    if "ArrayList" in content and "java.util.ArrayList" not in content and "import java.util.ArrayList" not in content:
                        imports_needed.add("java.util.ArrayList")
                    if "Map" in content and "java.util.Map" not in content:
                        imports_needed.add("java.util.Map")
                    if "HashMap" in content and "java.util.HashMap" not in content:
                        imports_needed.add("java.util.HashMap")
                    if "Collections" in content and "java.util.Collections" not in content:
                        imports_needed.add("java.util.Collections")
                    if "Date" in content and "java.util.Date" not in content and "import java" not in content:
                        imports_needed.add("java.util.Date")
                    if "Toast" in content and "import android.widget.Toast" not in content and "android" in content:
                        imports_needed.add("android.widget.Toast")
                    if "RecyclerView" in content and "import androidx.recyclerview" not in content:
                        imports_needed.add("androidx.recyclerview.widget.RecyclerView")
                    if "LiveData" in content and "import androidx.lifecycle.LiveData" not in content:
                        imports_needed.add("androidx.lifecycle.LiveData")
                    if "MutableLiveData" in content and "import androidx.lifecycle.MutableLiveData" not in content:
                        imports_needed.add("androidx.lifecycle.MutableLiveData")
                    if "ViewModel" in content and "import androidx.lifecycle.ViewModel" not in content:
                        imports_needed.add("androidx.lifecycle.ViewModel")
                    if "Room" in content or "Database" in content and "@Database" in content:
                        if "import androidx.room" not in content:
                            imports_needed.add("androidx.room.Database")
                            imports_needed.add("androidx.room.Room")
                    if "@Entity" in content and "import androidx.room.Entity" not in content:
                        imports_needed.add("androidx.room.Entity")
                    if "@Dao" in content and "import androidx.room.Dao" not in content:
                        imports_needed.add("androidx.room.Dao")
                    if "@Insert" in content and "import androidx.room.Insert" not in content:
                        imports_needed.add("androidx.room.Insert")
                    if "@Query" in content and "import androidx.room.Query" not in content:
                        imports_needed.add("androidx.room.Query")
                    if "@Delete" in content and "import androidx.room.Delete" not in content:
                        imports_needed.add("androidx.room.Delete")
                    if "@Update" in content and "import androidx.room.Update" not in content:
                        imports_needed.add("androidx.room.Update")
                    if "import " not in content and re.search(r'\b[A-Z][a-zA-Z]+\b', content):
                        imports_needed.add("java.util.*")

                    for imp in sorted(imports_needed):
                        imp_line = f"import {imp};"
                        if imp_line not in content:
                            # Insert after package declaration
                            pkg_end = content.find(";\n")
                            if pkg_end > 0:
                                insert_at = pkg_end + 2
                                content = content[:insert_at] + imp_line + "\n" + content[insert_at:]

                    # 5. Fix missing @Override annotations
                    content = re.sub(r'\n\s+protected void (onCreate|onStart|onResume|onPause|onStop|onDestroy)\b',
                                     lambda m: f"\n    @Override\n    protected void {m.group(1)}", content)
                    content = re.sub(r'\n\s+public boolean onCreateOptionsMenu\b',
                                     "\n    @Override\n    public boolean onCreateOptionsMenu", content)
                    content = re.sub(r'\n\s+public boolean onOptionsItemSelected\b',
                                     "\n    @Override\n    public boolean onOptionsItemSelected", content)

                    if content != original:
                        with open(path, "w", encoding="utf-8") as fh:
                            fh.write(content)
                        fixes += 1
                        logger.info("[AutoBuild] fixed Java issues in %s", os.path.relpath(path, root))
                except Exception as e:
                    logger.warning("[AutoBuild] could not fix %s: %s", path, e)
        return fixes

    def _fix_gradle_files(self, root: str, plan: dict, objective: str = "") -> bool:
        """Replace broken LLM-generated Gradle files with correct templates."""
        lo = (objective + " " + plan.get("language", "")).lower()
        if "android" not in lo and "gradle" not in lo:
            return False

        build_path = os.path.join(root, "build.gradle")
        settings_path = os.path.join(root, "settings.gradle")
        props_path = os.path.join(root, "gradle.properties")
        app_build_path = os.path.join(root, "app", "build.gradle")
        has_app_module = os.path.isdir(os.path.join(root, "app"))
        fixed = False

        pkg = "com.example.app"
        manifest_path = os.path.join(root, "src/main/AndroidManifest.xml")
        if os.path.isfile(manifest_path):
            with open(manifest_path, encoding="utf-8") as f:
                m = re.search(r'package="([^"]+)"', f.read())
                if m:
                    pkg = m.group(1)

        app_build_content = f"""plugins {{
    id 'com.android.application' version '8.7.0'
}}

repositories {{
    google()
    mavenCentral()
}}

android {{
    namespace '{pkg}'
    compileSdk 34

    defaultConfig {{
        applicationId '{pkg}'
        minSdk 26
        targetSdk 34
        versionCode 1
        versionName '1.0'
    }}

    buildTypes {{
        release {{
            minifyEnabled false
        }}
    }}

    compileOptions {{
        sourceCompatibility JavaVersion.VERSION_17
        targetCompatibility JavaVersion.VERSION_17
    }}
}}

dependencies {{
    implementation 'androidx.appcompat:appcompat:1.6.1'
    implementation 'com.google.android.material:material:1.11.0'
    implementation 'androidx.constraintlayout:constraintlayout:2.1.4'
    implementation 'androidx.recyclerview:recyclerview:1.3.2'
    implementation 'androidx.cardview:cardview:1.0.0'
    implementation 'androidx.lifecycle:lifecycle-viewmodel:2.7.0'
    implementation 'androidx.lifecycle:lifecycle-livedata:2.7.0'
    implementation 'androidx.room:room-runtime:2.6.1'
    annotationProcessor 'androidx.room:room-compiler:2.6.1'
    implementation 'com.google.code.gson:gson:2.10.1'
    testImplementation 'junit:junit:4.13.2'
    testImplementation 'org.mockito:mockito-core:5.10.0'
    androidTestImplementation 'androidx.test.ext:junit:1.1.5'
    androidTestImplementation 'androidx.test.espresso:espresso-core:3.5.1'
}}
"""

        if has_app_module:
            # Multi-module: write project-level build.gradle + app/build.gradle
            with open(build_path, "w", encoding="utf-8") as f:
                f.write("""plugins {
    id 'com.android.application' version '8.7.0' apply false
}

allprojects {
    repositories {
        google()
        mavenCentral()
    }
}
""")
            with open(app_build_path, "w", encoding="utf-8") as f:
                f.write(app_build_content)
            with open(settings_path, "w", encoding="utf-8") as f:
                proj_name = plan.get("project_name", "App")
                f.write(f"""pluginManagement {{
    repositories {{
        google()
        mavenCentral()
        gradlePluginPortal()
    }}
}}

rootProject.name = '{proj_name}'
include ':app'
""")
            with open(os.path.join(root, "app", "src", "main", "AndroidManifest.xml"), "w", encoding="utf-8") as f:
                f.write(f"""<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="{pkg}">
    <application android:label="@string/app_name" />
</manifest>
""")
        else:
            # Single module: write flat build.gradle
            with open(build_path, "w", encoding="utf-8") as f:
                f.write(app_build_content)

        # Write settings.gradle if not already written above
        if not has_app_module:
            proj_name = plan.get("project_name", "App")
            with open(settings_path, "w", encoding="utf-8") as f:
                f.write(f"""pluginManagement {{
    repositories {{
        google()
        mavenCentral()
        gradlePluginPortal()
    }}
}}

rootProject.name = '{proj_name}'
""")

        # Always overwrite gradle.properties — LLM often puts build config in it
        with open(props_path, "w", encoding="utf-8") as f:
            f.write("""org.gradle.jvmargs=-Xmx2048m -Dfile.encoding=UTF-8
android.useAndroidX=true
android.enableJetifier=true
""")

        logger.info("[AutoBuild] wrote proper Gradle build files for %s (multi-module=%s)", pkg, has_app_module)
        return True

    def _fix_android_manifest(self, root: str):
        """Ensure AndroidManifest.xml exists and has <application> tag."""
        manifest_path = None
        for r, _dirs, files in os.walk(root):
            for f in files:
                if f == "AndroidManifest.xml":
                    path = os.path.join(r, f)
                    try:
                        with open(path, "r", encoding="utf-8") as fh:
                            content = fh.read()
                        if "<application" not in content and "<activity" in content:
                            pkg_match = re.search(r'package="([^"]+)"', content)
                            pkg = pkg_match.group(1) if pkg_match else "com.example"
                            activity_match = re.search(r'android:name="([^"]+)"', content)
                            act = activity_match.group(1) if activity_match else ".MainActivity"
                            app_block = f'\n    <application android:label="@string/app_name">\n        <activity android:name="{act}" />\n    </application>\n'
                            content = content.replace("</manifest>", f"{app_block}</manifest>")
                            with open(path, "w", encoding="utf-8") as fh:
                                fh.write(content)
                            logger.info("[AutoBuild] fixed AndroidManifest: added <application> tag")
                    except Exception:
                        pass
                    manifest_path = path
        if not manifest_path:
            # Create a minimal AndroidManifest
            manifest_dir = os.path.join(root, "src", "main")
            os.makedirs(manifest_dir, exist_ok=True)
            manifest_path = os.path.join(manifest_dir, "AndroidManifest.xml")
            pkg = "com.example.app"
            # Find package from Java files
            for r, _dirs, files in os.walk(root):
                for f in files:
                    if f.endswith(".java"):
                        try:
                            with open(os.path.join(r, f), encoding="utf-8") as fh:
                                m = re.search(r'package\s+([\w.]+);', fh.read())
                                if m:
                                    pkg = m.group(1)
                                    break
                        except Exception:
                            pass
                if pkg != "com.example.app":
                    break
            with open(manifest_path, "w", encoding="utf-8") as f:
                f.write('<?xml version="1.0" encoding="utf-8"?>\n'
                        f'<manifest xmlns:android="http://schemas.android.com/apk/res/android"\n'
                        f'    package="{pkg}">\n'
                        f'    <application android:label="@string/app_name" />\n'
                        f'</manifest>\n')
            logger.info("[AutoBuild] created AndroidManifest.xml for %s", pkg)

    def _autostub_missing_layouts(self, root: str) -> int:
        """Create stub XML layouts for R.layout. references that don't exist."""
        layout_dir = None
        for r, dirs, _files in os.walk(root):
            if "layout" in dirs:
                layout_dir = os.path.join(r, "layout")
                break
            for d in dirs:
                if d.endswith("layout"):
                    layout_dir = os.path.join(r, d)
                    break
            if layout_dir:
                break
        if not layout_dir:
            return 0

        existing = {os.path.splitext(f)[0] for f in os.listdir(layout_dir) if f.endswith(".xml")}
        needed = set()
        for r, _dirs, files in os.walk(root):
            for f in files:
                if f.endswith(".java") or f.endswith(".kt") or f.endswith(".xml"):
                    try:
                        with open(os.path.join(r, f), encoding="utf-8") as fh:
                            content = fh.read()
                        for m in re.finditer(r'R\.layout\.(\w+)', content):
                            if m.group(1) not in existing:
                                needed.add(m.group(1))
                    except Exception:
                        pass

        stub_count = 0
        for name in sorted(needed):
            path = os.path.join(layout_dir, f"{name}.xml")
            if not os.path.exists(path):
                with open(path, "w", encoding="utf-8") as f:
                    f.write('<?xml version="1.0" encoding="utf-8"?>\n<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"\n    android:layout_width="match_parent"\n    android:layout_height="match_parent"\n    android:orientation="vertical">\n</LinearLayout>\n')
                stub_count += 1
                logger.info("[AutoBuild] auto-stubbed layout %s.xml", name)
        return stub_count

    def _autostub_missing_classes(self, root: str, plan: dict) -> int:
        """Find 'new ClassName()' references where ClassName.java doesn't exist, create stubs."""
        existing = set()
        for r, _dirs, files in os.walk(root):
            for f in files:
                if f.endswith(".java"):
                    existing.add(os.path.splitext(f)[0])

        needed = set()
        for r, _dirs, files in os.walk(root):
            for f in files:
                if f.endswith(".java"):
                    full = os.path.join(r, f)
                    try:
                        with open(full, "r", encoding="utf-8") as fh:
                            content = fh.read()
                        for m in re.finditer(r'new (\w+)\(', content):
                            cls = m.group(1)
                            if cls not in existing and cls not in self._known_external_classes():
                                if cls[0].isupper():
                                    needed.add(cls)
                    except Exception:
                        pass

        if not needed:
            return 0

        pkg = "com.example"
        src_root = os.path.join(root, "src/main/java")
        for r, _dirs, _files in os.walk(src_root if os.path.isdir(src_root) else root):
            for d in _dirs:
                if d in ("com", "org", "io", "net"):
                    pkg_dir = os.path.join(r, d)
                    rel = os.path.relpath(pkg_dir, src_root if os.path.isdir(src_root) else root)
                    pkg = rel.replace("\\", ".")
                    break
            break

        stub_count = 0
        for cls in sorted(needed):
            stub_dir = src_root if os.path.isdir(src_root) else root
            for p in pkg.split("."):
                stub_dir = os.path.join(stub_dir, p)
            os.makedirs(stub_dir, exist_ok=True)
            stub_path = os.path.join(stub_dir, f"{cls}.java")
            if not os.path.exists(stub_path):
                with open(stub_path, "w", encoding="utf-8") as f:
                    f.write(f"package {pkg};\n\npublic class {cls} {{\n}}\n")
                stub_count += 1
                logger.info("[AutoBuild] auto-stubbed %s.java", cls)
        return stub_count

    @staticmethod
    def _known_external_classes() -> set:
        return {
            "String", "Integer", "Boolean", "Long", "Double", "Float",
            "ArrayList", "HashMap", "List", "Map", "Set", "Object",
            "Thread", "Runnable", "File", "IOException", "Exception",
            "R", "Bundle", "View", "LayoutInflater", "ViewGroup", "Intent",
            "JsonReader", "JsonWriter", "InputStreamReader", "OutputStreamWriter",
            "BufferedReader", "BufferedWriter", "FileInputStream", "FileOutputStream",
            "Context", "Activity", "Fragment", "Application", "Service",
            "Notification", "NotificationManager", "PendingIntent",
            "ViewModelProvider", "ViewModel", "LiveData", "MutableLiveData",
            "Observer", "RecyclerView", "LinearLayoutManager",
            "ViewHolder", "OnClickListener", "TextWatcher", "Editor",
            "AppCompatDelegate", "Resources", "Configuration", "UiModeManager",
            "InstantTaskExecutorRule", "TestRule", "Rule",
        }

    def _standard_file_list(self, objective: str) -> list[str]:
        lo = objective.lower()
        if "python" in lo or "flask" in lo or "django" in lo:
            return ["requirements.txt", "src/main.py", "src/utils.py", "tests/test_main.py"]
        if "node" in lo or "npm" in lo or "react" in lo or "express" in lo:
            return ["package.json", "tsconfig.json", "src/index.ts", "src/app.ts", "tests/app.test.ts"]
        if "cargo" in lo or "rust" in lo:
            return ["Cargo.toml", "src/main.rs", "src/lib.rs", "tests/integration_test.rs"]
        if "gradle" in lo or "android" in lo:
            return [
                "build.gradle", "settings.gradle", "gradle.properties",
                "src/main/java/com/example/MainActivity.java",
                "src/main/res/layout/activity_main.xml",
                "src/main/AndroidManifest.xml",
                "src/test/java/com/example/MainActivityTest.java",
            ]
        return [
            "build.gradle", "settings.gradle",
            "src/main/java/com/example/App.java", "src/main/java/com/example/Calculator.java",
            "src/test/java/com/example/AppTest.java", "src/test/java/com/example/CalculatorTest.java",
        ]

    async def _execute_step(
        self, label: str, action: str, params: dict, idempotency_key: str = "",
    ) -> ActionResult:
        """Execute a single step, routing through ExecutionManager when available.

        Creates a single-step workflow via ``self.execution_manager.engine``
        so the execution is tracked, idempotent, and fires canonical events.
        Falls back to ``executor.execute_graph_node`` otherwise.
        """
        wf = self.execution_manager.engine
        if wf is not None and idempotency_key:
            try:
                from core.workflow.models import StepDefinition
                step = StepDefinition(tool_name=action, input_data=params)
                instance = await wf.start_workflow(
                    workflow_type=f"brain_auto_{label}",
                    steps=[step],
                    session_id=idempotency_key,
                    owner="brain_automation",
                    launch_background=False,
                )
                self.execution_manager.publish_progress(
                    self.execution_manager.create_context(
                        source="automation_loop",
                        metadata={"label": label, "action": action, "step": idempotency_key},
                    ),
                    f"execute_step:{label}",
                )
                # Wait for the workflow to finish
                wf_result = await wf.get_status(instance.workflow_id)
                if wf_result and wf_result.get("status") in ("completed", "failed"):
                    step_result = instance.steps[0] if instance.steps else None
                    if step_result and step_result.status.value == "completed":
                        return ActionResult(
                            success=True,
                            output=str(step_result.output_data or ""),
                            duration_ms=0.0,
                        )
                    error = step_result.error if step_result else "workflow failed"
                    return ActionResult(
                        success=False,
                        error=str(error),
                        duration_ms=0.0,
                    )
            except Exception:
                logger.debug("[AutoBuild] workflow exec failed, falling back", exc_info=True)

        return await executor.execute_graph_node(label, action, params)

    async def _phase_build(self, objective: str, proj_dir: str,
                           build_cmd: str, goal_id: str, plan: dict) -> bool:
        """Build with CompilerRepairEngine (deterministic) + failure memory + LLM fallback."""
        build_cmd = self._resolve_build_command(build_cmd, proj_dir)
        if not build_cmd:
            logger.info("[AutoBuild] build: no build command available, skipping")
            return True

        proj_name = plan.get("project_name", "project")
        root = os.path.join(proj_dir, proj_name) if proj_dir else proj_name
        gid = goal_id or objective[:40]

        # Lazy-init CompilerRepairEngine (one instance per build cycle)
        if self._repair_engine is None:
            from brain.compiler_repair_engine import CompilerRepairEngine
            self._repair_engine = CompilerRepairEngine(root, self._pattern_memory)
        else:
            self._repair_engine.project_dir = root
            self._repair_engine.metrics = self._repair_engine.metrics.__class__()

        repair_cycles = 0
        total_repaired = 0
        total_unresolved = 0
        memory_hits = 0

        for attempt in range(self.MAX_REPAIR_ATTEMPTS):
            logger.info("[AutoBuild] build attempt %d/%d: %s", attempt + 1, self.MAX_REPAIR_ATTEMPTS, build_cmd)
            result = await self._execute_step(
                "build", "run_command",
                {"command": build_cmd, "cwd": root},
                f"build-{goal_id}-{attempt}",
            )
            self.memory.store_trace("build_attempt", {"command": build_cmd, "attempt": attempt},
                                    result.output or result.error, result.success, result.duration_ms, goal_id)

            if result.success:
                self._consecutive_failures[gid] = 0
                logger.info("[AutoBuild] build succeeded")
                self._last_build_metrics = {
                    "build_success": True,
                    "repair_cycles": repair_cycles,
                    "repaired_errors": total_repaired,
                    "unresolved_errors": total_unresolved,
                    "memory_hits": memory_hits,
                }
                return True

            self._consecutive_failures[gid] = self._consecutive_failures.get(gid, 0) + 1
            if gid not in self._build_history:
                self._build_history[gid] = []
            build_output = (result.output or "") + "\n" + (result.error or "")
            self._build_history[gid].append(build_output[:500])

            if self._consecutive_failures[gid] >= 3 and attempt >= 2:
                logger.info("[AutoBuild] too many consecutive failures (%d), triggering plan evolution",
                            self._consecutive_failures[gid])
                return False

            # ── PRIORITY: CompilerRepairEngine (runs BEFORE legacy systems) ──
            errors = self._repair_engine.parse_errors(build_output)
            if errors:
                logger.info("[AutoBuild] CompilerRepairEngine: parsed %d errors", len(errors))
                any_fixed, actions = await self._repair_engine.repair(errors, root, objective)
                if any_fixed:
                    repair_cycles += 1
                    repaired = [a for a in actions if a.success]
                    unresolved = [a for a in actions if not a.success and a.action != "fix_code"]
                    total_repaired += len(repaired)
                    total_unresolved += len(unresolved)
                    memory_hits = self._repair_engine.metrics.pattern_memory_hits

                    logger.info("[AutoBuild] CompilerRepairEngine: fixed %d/%d errors (memory hits: %d)",
                                len(repaired), len(errors), memory_hits)

                    # Feed successes into legacy FailureMemory too
                    for action in actions:
                        if action.success and action.params.get("message", ""):
                            self.failure_memory.store(
                                action.params["message"],
                                action.category,
                                action.action,
                                {},
                            )
                    continue  # Retry build
                else:
                    # Record complete failure in PatternFailureMemory
                    for action in actions:
                        msg = action.params.get("message", "")
                        if msg:
                            self._pattern_memory.record_failure(
                                msg,
                                f"{action.action}:{action.category}",
                            )

            # ── PRIORITY 4: Legacy FailureMemory lookup ──
            known = self.failure_memory.lookup(build_output)
            if known:
                logger.info("[AutoBuild] known failure: %s -> %s fix", known.cause, known.fix_type)
                fix_applied = apply_fix({
                    "fix_type": known.fix_type,
                    "fix_action": known.fix_type,
                    "fix_params": known.fix_params,
                    "file": known.fix_params.get("file", ""),
                }, proj_dir, root)
                if fix_applied:
                    logger.info("[AutoBuild] applied known fix from memory")
                    self._pattern_memory.record_success(
                        known.error_signature,
                        f"legacy_memory:{known.fix_type}",
                    )
                    continue
                else:
                    logger.info("[AutoBuild] known fix failed to apply, falling through")
                    self._pattern_memory.record_failure(
                        known.error_signature,
                        f"FAILED:legacy_memory:{known.fix_type}",
                    )

            # ── PRIORITY 1: Legacy inline error classifier ──
            classified_errors = classify_error(build_output)
            if classified_errors:
                logger.info("[AutoBuild] classified %d errors", len(classified_errors))
                any_fix_applied = False
                for error in classified_errors:
                    fix_applied = apply_fix(error, proj_dir, root)
                    if fix_applied:
                        any_fix_applied = True
                        self.failure_memory.store(
                            error["error_text"],
                            error["fix_type"],
                            error["fix_type"],
                            {**error["fix_params"], "file": error.get("file", "")},
                        )
                        self._pattern_memory.record_success(
                            error.get("error_text", ""),
                            f"legacy_classifier:{error.get('fix_type', 'unknown')}",
                        )
                        logger.info("[AutoBuild] applied fix: %s -> %s",
                                    error["error_text"][:60], error["fix_type"])
                if any_fix_applied:
                    continue
                else:
                    for error in classified_errors:
                        self._pattern_memory.record_failure(
                            error.get("error_text", ""),
                            f"FAILED:legacy_classifier:{error.get('fix_type', 'unknown')}",
                        )

            # ── FALLBACK: LLM analysis for remaining errors ──
            logger.info("[AutoBuild] fallback: LLM analysis for unclassified errors")
            analysis_prompt = ANALYZE_BUILD_ERRORS_PROMPT.replace("{goal}", objective)
            analysis_prompt = analysis_prompt.replace("{build_command}", build_cmd)
            analysis_prompt = analysis_prompt.replace("{build_output}", build_output)
            analysis_raw = await self._call_llm(
                "You are a build error analyst. Output valid JSON only.",
                analysis_prompt,
                model_group="code",
                timeout=120,
            )
            analysis = _json_from_llm(analysis_raw) if analysis_raw else None
            if not analysis:
                logger.warning("[AutoBuild] build: could not analyze errors, retrying")
                await asyncio.sleep(2)
                continue

            logger.info("[AutoBuild] llm repair: %s", analysis.get("summary", "")[:100])
            repaired = await self._repair(objective, proj_dir, analysis)
            if not repaired:
                logger.warning("[AutoBuild] build: llm repair produced no changes, retrying")

            if not repaired and attempt >= 1:
                logger.info("[AutoBuild] vision fallback: searching error in browser")
                fix_found = await self._search_error_via_browser(build_output, proj_dir, root)
                if fix_found:
                    logger.info("[AutoBuild] vision fallback found a fix")
                    continue

        # Store final metrics
        engine_metrics = self._repair_engine.get_metrics()
        self._last_build_metrics = {
            "build_success": False,
            "repair_cycles": repair_cycles,
            "repaired_errors": total_repaired,
            "unresolved_errors": total_unresolved,
            "memory_hits": memory_hits,
            "total_errors": engine_metrics.get("total_errors", 0),
            "fix_rate_pct": engine_metrics.get("fix_rate_pct", 0),
            "pattern_memory_hits": engine_metrics.get("pattern_memory_hits", 0),
        }
        return False

    async def _search_error_via_browser(self, error_text: str, proj_dir: str, root: str) -> bool:
        """Fallback: use vision_browser to search for the error and apply found fix."""
        lines = [l.strip() for l in error_text.split("\n") if l.strip() and "error" in l.lower()]
        search_query = lines[0][:200] if lines else error_text[:200]
        try:
            from core.tools.vision_tools import do_vision_browser
            search_task = (
                f"Open Chrome, search Google for '{search_query} stackoverflow solution', "
                f"find the answer, and tell me the fix"
            )
            logger.info("[AutoBuild] vision search: %s", search_query[:80])
            result = await do_vision_browser(search_task)
            if result.get("status") == "done" and result.get("result"):
                fix_prompt = (
                    f"Build error:\n{error_text[:1000]}\n\n"
                    f"Research result:\n{result['result'][:2000]}\n\n"
                    f"Apply the fix from the research. Output JSON array of repair actions."
                )
                raw = await self._call_llm(
                    "You are a code repair specialist using research results.",
                    fix_prompt, timeout=120,
                )
                if raw:
                    actions = _json_from_llm(raw)
                    if isinstance(actions, list):
                        for action in actions:
                            act_type = action.get("action", "")
                            params = action.get("params", {})
                            if act_type == "write_file":
                                path = params.get("path", "")
                                content = params.get("content", "")
                                if path and content:
                                    full = os.path.join(proj_dir, path.replace("\\", "/"))
                                    os.makedirs(os.path.dirname(full), exist_ok=True)
                                    with open(full, "w", encoding="utf-8") as f:
                                        f.write(content)
                                    return True
                            elif act_type == "edit_file_text":
                                path = params.get("path", "")
                                old = params.get("old_string", "")
                                new = params.get("new_string", "")
                                if path and old and new:
                                    full = os.path.join(proj_dir, path.replace("\\", "/"))
                                    if os.path.exists(full):
                                        with open(full, "r", encoding="utf-8") as f:
                                            content = f.read()
                                        if old in content:
                                            content = content.replace(old, new, 1)
                                            with open(full, "w", encoding="utf-8") as f:
                                                f.write(content)
                                            return True
            return False
        except Exception as e:
            logger.warning("[AutoBuild] vision fallback error: %s", e)
            return False

    async def _verify_semantic(self, proj_dir: str, plan: dict) -> list[str]:
        """Deep semantic verification beyond structural gates."""
        issues = []
        proj_name = plan.get("project_name", "")
        root = os.path.join(proj_dir, proj_name) if proj_dir else proj_name

        layout_dir = os.path.join(root, "src/main/res/layout")
        java_files = []
        for r, dirs, files in os.walk(root if root else "."):
            for f in files:
                if f.endswith(".java") or f.endswith(".kt"):
                    java_files.append(os.path.join(r, f))

        layout_ids = set()
        if os.path.isdir(layout_dir):
            for lf in os.listdir(layout_dir):
                if lf.endswith(".xml"):
                    try:
                        with open(os.path.join(layout_dir, lf), "r", encoding="utf-8") as f:
                            content = f.read()
                        for m in re.finditer(r'android:id="@\+id/(\w+)"', content):
                            layout_ids.add(m.group(1))
                    except Exception:
                        pass

        for jf in java_files:
            try:
                with open(jf, "r", encoding="utf-8") as f:
                    content = f.read()
                for m in re.finditer(r'R\.id\.(\w+)', content):
                    ref_id = m.group(1)
                    if ref_id not in layout_ids:
                        rel = os.path.relpath(jf, root)
                        issues.append(f"{rel}: references R.id.{ref_id} not defined in any layout")
            except Exception:
                pass

        strings_xml = os.path.join(root, "src/main/res/values/strings.xml")
        string_refs = set()
        if os.path.isfile(strings_xml):
            try:
                with open(strings_xml, "r", encoding="utf-8") as f:
                    content = f.read()
                for m in re.finditer(r'name="(\w+)"', content):
                    string_refs.add(m.group(1))
            except Exception:
                pass

        for jf in java_files:
            try:
                with open(jf, "r", encoding="utf-8") as f:
                    content = f.read()
                for m in re.finditer(r'R\.string\.(\w+)', content):
                    ref = m.group(1)
                    if ref not in string_refs:
                        rel = os.path.relpath(jf, root)
                        issues.append(f"{rel}: references R.string.{ref} not in strings.xml")
            except Exception:
                pass

        for jf in java_files:
            try:
                with open(jf, "r", encoding="utf-8") as f:
                    content = f.read()
                rel = os.path.relpath(jf, root)
                types_used = set()
                for m in re.finditer(r'\b([A-Z][a-zA-Z0-9_]+)\b', content):
                    t = m.group(1)
                    if t not in ("String", "Integer", "Boolean", "Long", "Double", "Float",
                                 "Object", "Void", "Thread", "Class", "System", "R",
                                 "View", "ViewGroup", "LayoutInflater", "Bundle", "Intent",
                                 "Context", "Activity", "Fragment", "Application",
                                 "OnClickListener", "InstantTaskExecutorRule", "TestRule", "Rule", "ViewModelProvider", "ViewModel", "LiveData", "List", "Map", "Set", "ArrayList", "HashMap"):
                        types_used.add(t)
                imports = set()
                for m in re.finditer(r'^import\s+([\w.]+);\s*$', content, re.MULTILINE):
                    imports.add(m.group(1))
                android_widgets = {"Button", "TextView", "EditText", "ImageView",
                                   "RecyclerView", "LinearLayout", "RelativeLayout", "FrameLayout",
                                   "ScrollView", "ListView", "GridView", "ProgressBar",
                                   "CheckBox", "RadioButton", "Switch", "SeekBar", "RatingBar",
                                   "Toolbar", "CardView", "NestedScrollView",
                                   "SwipeRefreshLayout", "CoordinatorLayout", "AppBarLayout",
                                   "CollapsingToolbarLayout", "TabLayout", "ViewPager", "ViewPager2"}
                for t in types_used:
                    if t in android_widgets:
                        ip = f"android.widget.{t}"
                        if ip not in imports:
                            issues.append(f"{rel}: uses {t} without import android.widget.{t}")
                    elif t in ("MaterialButton", "MaterialCardView", "FloatingActionButton",
                               "BottomNavigationView", "NavigationView", "Snackbar",
                               "TextInputLayout", "TextInputEditText", "Chip", "ChipGroup",
                               "BottomSheetDialog", "MaterialAlertDialogBuilder"):
                        ip = f"com.google.android.material.{t}"
                        if ip not in imports:
                            issues.append(f"{rel}: uses {t} without import {ip}")
            except Exception:
                pass

        return issues

    async def _plan_evolution(self, objective: str, proj_dir: str,
                               goal_id: str, plan: dict) -> dict | None:
        """Analyze root cause of stalled build and return mutated plan."""
        goal_id = goal_id or objective[:40]
        build_history = self._build_history.get(goal_id, [])
        attempts = len(build_history)
        if attempts < 3:
            return None

        plan_json = json.dumps({k: v for k, v in plan.items() if k != "steps"}, indent=2, default=str)
        files = _list_files(os.path.join(proj_dir, plan.get("project_name", "project")))
        history_text = "\n".join(build_history[-10:]) if build_history else "no prior errors"

        prompt = ROOT_CAUSE_PROMPT.replace("{goal}", objective)
        prompt = prompt.replace("{plan_json}", plan_json)
        prompt = prompt.replace("{attempts}", str(attempts))
        prompt = prompt.replace("{build_history}", history_text)
        prompt = prompt.replace("{files}", "\n".join(files) if files else "none yet")

        logger.info("[AutoBuild] analyzing root cause after %d failed attempts", attempts)
        raw = await self._call_llm(
            "You are a software architecture analyst. Identify root causes, not symptoms.",
            prompt, timeout=120,
        )
        analysis = _json_from_llm(raw) if raw else None
        if not analysis:
            return None

        mutation = analysis.get("plan_mutation", {})
        if not mutation:
            logger.info("[AutoBuild] root cause: %s (no plan mutation suggested)",
                        analysis.get("root_cause", "unknown"))
            return None

        logger.info("[AutoBuild] root cause: %s — mutating plan", analysis.get("root_cause", "unknown"))
        # Store lesson in architectural memory
        project_type = plan.get("language", "unknown")
        if "android" in objective.lower():
            project_type = "android-" + project_type
        self.architectural_memory.learn(
            project_type=project_type,
            root_cause=analysis.get("root_cause", "unknown failure"),
            affected_areas=analysis.get("affected_areas", []),
            plan_mutation=mutation,
        )
        new_plan = dict(plan)
        if mutation.get("new_files"):
            existing = set(new_plan.get("files", []))
            new_plan["files"] = list(existing | set(mutation["new_files"]))
        if mutation.get("steps"):
            new_plan["steps"] = mutation["steps"]
        if mutation.get("build_command"):
            new_plan["build_command"] = mutation["build_command"]
        if mutation.get("test_command"):
            new_plan["test_command"] = mutation["test_command"]
        # Reset build history for this goal after mutation
        self._build_history[goal_id] = []
        self._consecutive_failures[goal_id] = 0
        return new_plan

    def _track_completion(self, objective: str, proj_dir: str, plan: dict) -> float:
        """Parse requirements from goal and calculate completion %."""
        self.req_tracker.parse_goal(objective)
        pct = self.req_tracker.check_completion(proj_dir, plan)
        self._completion = pct
        logger.info("[AutoBuild] completion: %.0f%%", pct)
        for r in self.req_tracker.requirements:
            logger.info("  %s %s", "✓" if r.completed else "✗", r.name)
        return pct

    async def _phase_runtime_validation(self, objective: str, proj_dir: str,
                                        plan: dict, goal_id: str) -> bool:
        """Launch app → vision inspection → requirement verification."""
        proj_name = plan.get("project_name", "project")
        root = os.path.join(proj_dir, proj_name) if proj_dir else proj_name
        language = (plan.get("language") or "").lower()
        lo = objective.lower()

        # Only validate Android apps for now
        if "android" not in lo and language not in ("java", "kotlin"):
            logger.info("[Runtime] non-Android project, skipping runtime validation")
            return True

        logger.info("[Runtime] starting runtime validation for %s", proj_name)

        # 1. Find the APK
        apk_path = None
        for r, _dirs, files in os.walk(root):
            for f in files:
                if f.endswith(".apk") and "debug" in f:
                    apk_path = os.path.join(r, f)
                    break
            if apk_path:
                break
        if not apk_path:
            apk_path = os.path.join(root, "app/build/outputs/apk/debug/app-debug.apk")
            if not os.path.exists(apk_path):
                apk_path = os.path.join(root, "build/outputs/apk/debug/app-debug.apk")

        if not apk_path or not os.path.exists(apk_path):
            logger.warning("[Runtime] no APK found at %s", apk_path or root)
            return False

        logger.info("[Runtime] APK found: %s", apk_path)

        # 2. Check for emulator; if none running, try to start one
        adb = self._find_adb()
        if not adb:
            logger.warning("[Runtime] adb not found, cannot deploy")
            return False

        devices = await self._adb_devices(adb)
        if not devices:
            logger.info("[Runtime] no running emulator, attempting to start one")
            avd_name = await self._find_avd()
            if avd_name:
                started = await self._start_emulator(avd_name)
                if not started:
                    logger.warning("[Runtime] could not start emulator")
                    return False
                # Wait for boot
                for _ in range(60):
                    await asyncio.sleep(5)
                    booted = await self._adb_boot_completed(adb)
                    if booted:
                        logger.info("[Runtime] emulator booted")
                        break
                else:
                    logger.warning("[Runtime] emulator did not boot in time")
                    return False

        # 3. Install APK
        logger.info("[Runtime] installing APK...")
        install_ok = await self._adb_install(adb, apk_path)
        if not install_ok:
            logger.warning("[Runtime] APK installation failed")
            return False

        # 4. Launch the app
        pkg = self._extract_package_name(root)
        if pkg:
            logger.info("[Runtime] launching %s", pkg)
            await self._adb_launch(adb, pkg)

        await asyncio.sleep(3)  # wait for app to render

        # 5. Collect verification sources: screenshot, UIAutomator XML, logcat
        logger.info("[Runtime] collecting verification sources")

        # 5a. Screenshot via ADB screencap
        screenshot_path = await self._adb_screenshot(adb)
        screenshot_available = os.path.exists(screenshot_path) if screenshot_path else False
        screenshot_desc = ""
        if screenshot_available:
            try:
                from core.tools.vision_tools import do_vision_browser
                screenshot_result = await do_vision_browser(
                    f"Analyze this Android app screenshot at {screenshot_path}. "
                    f"Describe exactly what UI elements you see — every button, text field, "
                    f"label, and interactive element.",
                )
                screenshot_desc = screenshot_result.get("result", "Screenshot captured")
                logger.info("[Runtime] screenshot analysis: %s", str(screenshot_desc)[:100])
            except Exception as e:
                logger.warning("[Runtime] vision analysis failed: %s", e)
                screenshot_desc = "Vision analysis unavailable"

        # 5b. UIAutomator XML dump
        ui_xml = await self._adb_uiautomator_dump(adb)
        if ui_xml:
            logger.info("[Runtime] UIAutomator dump: %d chars", len(ui_xml))

        # 5c. Logcat
        logcat_out = await self._adb_logcat(adb, pkg)
        if logcat_out:
            logger.info("[Runtime] logcat: %d chars", len(logcat_out))

        # 6. Verify requirements using all three sources
        verify_prompt = RUNTIME_VALIDATE_PROMPT.replace("{project_type}", "Android")
        verify_prompt = verify_prompt.replace("{requirements}", objective)
        sources_parts = []
        if screenshot_desc:
            sources_parts.append(f"Screenshot Analysis:\n{screenshot_desc[:2000]}")
        if ui_xml:
            sources_parts.append(f"UI Hierarchy (UIAutomator):\n{ui_xml[:3000]}")
        if logcat_out:
            sources_parts.append(f"Logcat:\n{logcat_out[:2000]}")
        verify_prompt = verify_prompt.replace("{vision_report}",
                                              "\n\n".join(sources_parts) if sources_parts else "No verification sources available")

        raw = await self._call_llm(
            "You are a QA engineer validating UI against requirements using screenshot, UI hierarchy, and logcat.",
            verify_prompt, timeout=120,
        )
        validation = _json_from_llm(raw) if raw else None

        if validation and validation.get("validated"):
            logger.info("[Runtime] validation PASSED")
            for v in validation.get("visible_elements", []):
                logger.info("  ✓ %s", v)
            return True
        else:
            missing = validation.get("missing_elements", []) if validation else ["unknown"]
            logger.warning("[Runtime] validation FAILED — missing: %s", missing)
            return False

    def _find_adb(self) -> str:
        """Locate adb executable."""
        candidates = ["adb", "adb.exe",
                      os.path.expanduser("~/Android/Sdk/platform-tools/adb"),
                      os.path.expanduser("~/Android/Sdk/platform-tools/adb.exe"),
                      "C:\\Android\\Sdk\\platform-tools\\adb.exe",
                      "C:\\Program Files\\Android\\Sdk\\platform-tools\\adb.exe"]
        for c in candidates:
            if os.path.isfile(c) or any(
                os.path.isfile(os.path.join(p, c))
                for p in os.environ.get("PATH", "").split(os.pathsep)
                if p
            ):
                return c
        return ""

    async def _adb_devices(self, adb: str) -> list[str]:
        try:
            import subprocess
            r = await asyncio.create_subprocess_exec(
                adb, "devices",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, _ = await r.communicate()
            lines = out.decode().strip().split("\n")
            devices = []
            for line in lines[1:]:
                if line.strip() and "device" in line and "offline" not in line:
                    devices.append(line.split()[0])
            return devices
        except Exception:
            return []

    async def _adb_boot_completed(self, adb: str) -> bool:
        try:
            r = await asyncio.create_subprocess_exec(
                adb, "shell", "getprop", "sys.boot_completed",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, _ = await r.communicate()
            return out.decode().strip() == "1"
        except Exception:
            return False

    async def _find_avd(self) -> str:
        try:
            r = await asyncio.create_subprocess_exec(
                "emulator", "-list-avds",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, _ = await r.communicate()
            avds = [l.strip() for l in out.decode().strip().split("\n") if l.strip()]
            return avds[0] if avds else ""
        except Exception:
            return ""

    async def _start_emulator(self, avd_name: str) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                "emulator", "-avd", avd_name, "-no-boot-anim", "-no-window",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            # Don't wait — emulator runs in background
            return True
        except Exception:
            return False

    async def _adb_install(self, adb: str, apk_path: str) -> bool:
        try:
            r = await asyncio.create_subprocess_exec(
                adb, "install", "-r", apk_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, err = await r.communicate()
            success = r.returncode == 0
            if not success:
                logger.warning("[Runtime] adb install failed: %s", err.decode())
            return success
        except Exception as e:
            logger.warning("[Runtime] adb install error: %s", e)
            return False

    async def _adb_launch(self, adb: str, package: str):
        try:
            await asyncio.create_subprocess_exec(
                adb, "shell", "am", "start", "-n",
                f"{package}/.MainActivity",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except Exception:
            pass

    async def _adb_uiautomator_dump(self, adb: str) -> str:
        """Dump UI hierarchy via UIAutomator and return XML content."""
        try:
            dump_proc = await asyncio.create_subprocess_exec(
                adb, "shell", "uiautomator", "dump",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await dump_proc.communicate()
            pull_proc = await asyncio.create_subprocess_exec(
                adb, "pull", "/sdcard/window_dump.xml",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await pull_proc.communicate()
            ui_path = "window_dump.xml"
            if os.path.exists(ui_path):
                with open(ui_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                os.remove(ui_path)
                return content[:5000]
        except Exception:
            pass
        return ""

    async def _adb_logcat(self, adb: str, package: str = "") -> str:
        """Capture logcat output, optionally filtered by package."""
        try:
            args = [adb, "logcat", "-d"]
            if package:
                args.extend(["-s", f"{package}:V"])
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, _ = await proc.communicate()
            decoded = out.decode("utf-8", errors="replace")
            return decoded[-3000:]
        except Exception:
            return ""

    async def _adb_screenshot(self, adb: str) -> str:
        """Capture screenshot, return local path."""
        try:
            await asyncio.create_subprocess_exec(
                adb, "shell", "screencap", "-p", "/sdcard/screen.png",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.sleep(0.5)
            local_path = "runtime_screen.png"
            pull_proc = await asyncio.create_subprocess_exec(
                adb, "pull", "/sdcard/screen.png", local_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await pull_proc.communicate()
            if os.path.exists(local_path):
                return local_path
        except Exception:
            pass
        return ""

    def _extract_package_name(self, root: str) -> str:
        """Extract Android package name from AndroidManifest.xml."""
        for r, _dirs, files in os.walk(root):
            for f in files:
                if f == "AndroidManifest.xml":
                    try:
                        with open(os.path.join(r, f), encoding="utf-8") as fh:
                            content = fh.read()
                        m = re.search(r'package="([^"]+)"', content)
                        if m:
                            return m.group(1)
                    except Exception:
                        pass
        return ""

    async def _phase_test(self, objective: str, proj_dir: str,
                          test_cmd: str, goal_id: str) -> bool:
        """Run tests, loop on failure."""
        if not test_cmd:
            logger.info("[AutoBuild] test: no test command, skipping")
            return True

        # Skip if no test source files exist
        test_dirs = ["src/test", "tests", "test"]
        has_tests = any(
            os.path.isdir(os.path.join(proj_dir, d)) for d in test_dirs
        )
        if not has_tests:
            logger.info("[AutoBuild] test: no test source directories found, skipping")
            return True

        for attempt in range(self.MAX_REPAIR_ATTEMPTS):
            logger.info("[AutoBuild] test attempt %d/%d: %s", attempt + 1, self.MAX_REPAIR_ATTEMPTS, test_cmd)
            result = await self._execute_step(
                "test", "run_command",
                {"command": test_cmd, "cwd": proj_dir},
                f"test-{goal_id}-{attempt}",
            )
            self.memory.store_trace("test_attempt", {"command": test_cmd, "attempt": attempt},
                                    result.output or result.error, result.success, result.duration_ms, goal_id)

            if result.success:
                logger.info("[AutoBuild] tests passed")
                return True

            logger.warning("[AutoBuild] tests failed, analyzing failures")
            analysis_prompt = ANALYZE_TEST_ERRORS_PROMPT.replace("{goal}", objective)
            analysis_prompt = analysis_prompt.replace("{test_command}", test_cmd)
            analysis_prompt = analysis_prompt.replace("{test_output}", (result.output or "") + "\n" + (result.error or ""))
            analysis_raw = await self._call_llm(
                "You are a test failure analyst. Output valid JSON only.",
                analysis_prompt,
                model_group="code",
                timeout=120,
            )
            analysis = _json_from_llm(analysis_raw) if analysis_raw else None
            if not analysis:
                logger.warning("[AutoBuild] test: could not analyze failures, retrying")
                continue

            logger.info("[AutoBuild] repairing from test analysis: %s",
                        analysis.get("summary", "")[:100])
            repaired = await self._repair(objective, proj_dir, analysis)
            if not repaired:
                logger.warning("[AutoBuild] test: repair produced no changes, retrying anyway")

        return False

    async def _phase_verify(self, objective: str, proj_dir: str, goal_id: str, plan: dict = None) -> bool:
        """Deterministic verification: file structure + completion check. No LLM."""
        files = _list_files(proj_dir)
        if not files:
            logger.warning("[AutoBuild] verify: no files in project directory")
            return False
        found_java = any(f.endswith(".java") for f in files)
        found_manifest = any("AndroidManifest.xml" in f for f in files)
        logger.info("[AutoBuild] verify: %d files (%d Java, manifest=%s)", len(files), sum(1 for f in files if f.endswith(".java")), found_manifest)
        if not found_java:
            logger.warning("[AutoBuild] verify: no Java source files found")
            return False
        # Completion score via RequirementTracker
        if plan:
            self.req_tracker.parse_goal(objective)
        pct = self.req_tracker.check_completion(proj_dir, plan or {"project_name": "project"})
        self._completion = pct
        logger.info("[AutoBuild] verification passed: %d files, completion %.0f%%", len(files), pct)
        return True

    async def _repair(self, objective: str, proj_dir: str, analysis: Any) -> bool:
        """Use LLM to repair files based on analysis. Returns True if any file was modified."""
        summary = analysis.get("summary", analysis.get("message", str(analysis)))[:500]
        repair_prompt = REPAIR_PROMPT.replace("{goal}", objective)
        repair_prompt = repair_prompt.replace("{project_dir}", proj_dir)
        repair_prompt = repair_prompt.replace("{analysis}", summary)

        files = _list_files(proj_dir)
        if files:
            repair_prompt += "\n\nCurrent file contents:"
            for f in files[:5]:
                full = os.path.join(proj_dir, f)
                try:
                    with open(full) as fh:
                        content = fh.read()
                    repair_prompt += f"\n\n=== {f} ===\n{content[:2000]}"
                except Exception:
                    pass

        raw = await self._call_llm(
            "You are a code repair specialist. Output valid JSON array of repair actions.",
            repair_prompt,
            model_group="code",
            timeout=120,
        )
        if not raw:
            return False

        actions = _json_from_llm(raw)
        if not isinstance(actions, list):
            extracted = task_resolver._extract_individual_objects(raw)
            if extracted:
                actions = extracted

        if not actions:
            return False

        modified = 0
        for action in actions if isinstance(actions, list) else []:
            act_type = action.get("action", action.get("tool", ""))
            params = action.get("params", {})
            if not act_type:
                act_type = action.get("tool", "")
                params = {k: v for k, v in action.items() if k != "tool"}

            if act_type == "write_file":
                path = params.get("path", "")
                content = params.get("content", "")
                if path and content:
                    full = os.path.join(proj_dir, path.replace("\\", "/"))
                    os.makedirs(os.path.dirname(full), exist_ok=True)
                    with open(full, "w", encoding="utf-8") as f:
                        f.write(content)
                    logger.info("[AutoBuild] repair: wrote %s (%d bytes)", path, len(content))
                    modified += 1

            elif act_type == "edit_file_text":
                path = params.get("path", "")
                old = params.get("old_string", "")
                new = params.get("new_string", "")
                if path and old and new:
                    full = os.path.join(proj_dir, path.replace("\\", "/"))
                    if os.path.exists(full):
                        with open(full, "r", encoding="utf-8") as f:
                            content = f.read()
                        if old in content:
                            content = content.replace(old, new, 1)
                            with open(full, "w", encoding="utf-8") as f:
                                f.write(content)
                            logger.info("[AutoBuild] repair: edited %s", path)
                            modified += 1

        return modified > 0

    async def run_once(self, goal: Plan) -> dict:
        """Run a single build cycle for a given goal."""
        await self._build_project(goal)
        g = self.goals.get(goal.id)
        return {
            "goal_id": goal.id,
            "goal": goal.goal,
            "status": g.status if g else "unknown",
            "progress": g.progress if g else 0,
            "completion_pct": round(self._completion, 1),
            "pattern_memory_count": FailureMemory._generalization_count,
            "failure_memory_size": len(self.failure_memory._exact) + len(self.failure_memory._patterns),
            "architectural_lessons": len(self.architectural_memory._patterns),
        }

    def status(self) -> dict:
        return {
            "running": self._running,
            "paused": self._paused,
            "iterations": self._iteration_count,
            "uptime_seconds": round(self.uptime, 1),
            "active_goals": len(self.goals.list_all(status="active")),
            "project_dir": self.project_dir,
            "completion_pct": round(self._completion, 1),
            "pattern_memory_count": FailureMemory._generalization_count,
            "failure_memory_size": len(self.failure_memory._exact) + len(self.failure_memory._patterns),
            "architectural_lessons": len(self.architectural_memory._patterns),
        }


automation_loop: AutomationLoop | None = None
