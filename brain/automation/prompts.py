from __future__ import annotations

import json
import logging
import os
import re

logger = logging.getLogger(__name__)

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

ANALYZE_BUILD_ERRORS_PROMPT = """Goal: {goal}
Project type: {project_type}
Build command: {build_cmd}
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


def list_project_files(project_dir: str) -> list[str]:
    files = []
    if os.path.isdir(project_dir):
        for root, dirs, fnames in os.walk(project_dir):
            for f in fnames:
                rel = os.path.relpath(os.path.join(root, f), project_dir)
                if not rel.startswith(".") and not rel.startswith("brain"):
                    files.append(rel.replace("\\", "/"))
    return sorted(files)


def json_from_llm(raw: str) -> dict | list | None:
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


def fallback_plan(objective: str) -> dict:
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
