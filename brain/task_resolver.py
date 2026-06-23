"""TaskResolver — bridges high-level plan nodes to executable tool calls.

Given a high-level task description (from Planner's DAG), the resolver
uses the LLM to generate a concrete list of tool calls with parameters.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from core.llm_router import complete

logger = logging.getLogger(__name__)

_KNOWN_LANGS = {"java", "kotlin", "xml", "python", "javascript", "typescript",
                "html", "css", "json", "yaml", "toml", "ini", "bash", "sh",
                "groovy", "gradle", "rust", "go", "sql", "properties", "proto"}


def _extract_code_block(raw: str) -> str:
    """Extract code from markdown code blocks, regardless of position."""
    # If no code fences, just return stripped
    if "```" not in raw:
        return raw.strip()
    # Split by ``` and take the first block
    parts = raw.split("```")
    for i, part in enumerate(parts):
        if i % 2 == 1:  # odd indices are inside code blocks
            lines = part.split("\n")
            # Remove language tag from first line if present
            first_line = lines[0].strip().lower()
            if first_line in _KNOWN_LANGS:
                lines = lines[1:]
            return "\n".join(lines).strip()
    # Fallback: strip all fences
    return raw.replace("```", "").strip()


def _fallback_content(file_path: str) -> str:
    """Generate a minimal placeholder for a given file path."""
    ext = os.path.splitext(file_path)[1]
    if ext == ".java":
        pkg = "com.example"
        cls = os.path.splitext(os.path.basename(file_path))[0]
        return f"package {pkg};\n\npublic class {cls} {{\n    // TODO\n}}\n"
    if ext == ".py":
        return f"# {file_path}\n# TODO\n"
    if ext in (".xml", ".html"):
        return f"<!-- {file_path} -->\n"
    if ext == ".gradle":
        return "// TODO\n"
    return f"// {file_path}\n// TODO\n"

RESOLVE_SYSTEM = (
    "You are an autonomous AI that generates tool calls to complete tasks.\n"
    "Available tools:\n"
    "  create_directory(path) — creates a directory\n"
    "  write_file(path, content) — writes a file\n"
    "  run_command(command) — runs a shell command\n"
    "  compile_java(source_path) — compiles Java\n"
    "  run_tests(project_dir) — runs tests\n"
    "  build_project(project_dir) — builds the project\n\n"
    "Respond ONLY with a JSON array of tool call objects. Example:\n"
    '[{"tool": "create_directory", "params": {"path": "..."}}, {"tool": "write_file", "params": {"path": "...", "content": "..."}}]\n'
    "Use write_file sparingly — only for key source/config files.\n"
    "No markdown, no explanation. Keep the response short."
)


def _build_project_context(project_dir: str, goal: str,
                           existing_files: list[str],
                           previous_results: list[dict]) -> str:
    """Build a context string summarizing project state."""
    parts = [f"Goal: {goal}"]
    parts.append(f"Project root: {project_dir}")
    if existing_files:
        parts.append("Existing files:")
        for f in sorted(existing_files):
            parts.append(f"  - {f}")
    if previous_results:
        parts.append("Previous steps:")
        for pr in previous_results[-5:]:
            status = "OK" if pr.get("success") else "FAIL"
            parts.append(f"  [{status}] {pr.get('label', '?')}: {pr.get('output', '')[:80]}")
    parts.append("")
    return "\n".join(parts)


class TaskResolver:
    """Converts high-level task descriptions into executable tool calls."""

    def __init__(self, project_dir: str = ""):
        self.project_dir = project_dir
        self._existing_files: list[str] = []
        self._previous_results: list[dict] = []

    def update_context(self, existing_files: list[str],
                       previous_results: list[dict] | None = None):
        self._existing_files = existing_files
        if previous_results:
            self._previous_results = previous_results

    async def resolve(self, goal: str, task_label: str,
                      task_description: str) -> list[tuple[str, dict]]:
        """Resolve a high-level task into tool calls.

        Returns list of (tool_name, params) tuples.
        """
        context = _build_project_context(
            self.project_dir, goal,
            self._existing_files, self._previous_results,
        )

        prompt = (
            f"{context}\n"
            f"Task: {task_description or task_label}\n\n"
            f"Generate the tool calls needed to complete this task."
        )

        try:
            result = await complete(
                "code",
                [
                    {"role": "system", "content": RESOLVE_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                timeout=30,
            )

            if result.is_err():
                logger.warning("[TaskResolver] LLM failed for '%s': %s",
                               task_label, str(result._error if hasattr(result, '_error') else result))
                return []

            raw = result.unwrap()
            return self._parse_tool_calls(raw)

        except Exception as e:
            logger.warning("[TaskResolver] exception for '%s': %s", task_label, e)
            return []

    def _parse_tool_calls(self, raw: str) -> list[tuple[str, dict]]:
        """Parse LLM response into tool calls.

        Handles truncated JSON by extracting individually complete objects.
        """
        raw = raw.strip()
        # Strip code fences
        for prefix in ["```json", "```JSON", "```"]:
            if raw.startswith(prefix):
                raw = raw[len(prefix):]
        for suffix in ["```"]:
            if raw.endswith(suffix):
                raw = raw[:-len(suffix)]
        raw = raw.strip()

        # Replace backtick strings with quotes (common LLM mistake)
        raw = self._fix_backtick_strings(raw)

        start = raw.find("[")
        if start == -1:
            # Try single object
            start = raw.find("{")
            if start == -1:
                return []
            raw = "[" + raw[start:]
        else:
            raw = raw[start:]

        # Find the outermost balanced brackets
        balanced = self._find_balanced(raw)
        if not balanced:
            return []
        json_str, _ = balanced

        # Try parsing complete JSON
        data = None
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            # Parse failed — try extracting individual complete objects
            data = self._extract_individual_objects(json_str)

        if not data:
            return []

        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            return []

        result = []
        for call in data:
            tool = call.get("tool", "")
            params = call.get("params", {})
            if not tool:
                tool = call.get("action", call.get("name", ""))
            if tool:
                result.append((tool, params))

        if not result:
            logger.warning("[TaskResolver] no valid tool calls in response: %s", json_str[:200])

        return result

    def _fix_backtick_strings(self, text: str) -> str:
        """Replace backtick-wrapped multi-line strings with valid JSON string literals."""
        result = []
        i = 0
        while i < len(text):
            # Find next backtick pair
            start = text.find('`', i)
            if start == -1:
                result.append(text[i:])
                break
            # Append everything before the backtick
            result.append(text[i:start])
            # Find closing backtick
            end = text.find('`', start + 1)
            if end == -1:
                # No closing backtick — leave as is
                result.append(text[start:])
                break
            # Extract the inner content
            inner = text[start + 1:end]
            # Escape for JSON string: escape backslashes, quotes, newlines
            escaped = (
                inner
                .replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("\r\n", "\\n")
                .replace("\n", "\\n")
                .replace("\r", "\\n")
                .replace("\t", "\\t")
            )
            result.append('"')
            result.append(escaped)
            result.append('"')
            i = end + 1
        return "".join(result)

    def _find_balanced(self, text: str) -> tuple[str, int] | None:
        """Find outermost balanced [...] or {...} and return (content, end_pos)."""
        start_ch = text[0] if text else ""
        end_ch = {"[": "]", "{": "}"}.get(start_ch)
        if not end_ch:
            return None
        depth = 0
        for i, ch in enumerate(text):
            if ch == start_ch:
                depth += 1
            elif ch == end_ch:
                depth -= 1
                if depth == 0:
                    return text[:i + 1], i + 1
        return None

    def _extract_individual_objects(self, text: str) -> list[dict]:
        """Extract individually parseable JSON objects from broken JSON."""
        # Try: extract each complete {..} object individually
        # Skip outer [ ] brackets entirely
        result = []
        i = 0
        while i < len(text):
            if text[i] == "{":
                obj_text, end = self._find_balanced(text[i:]) or (None, 0)
                if obj_text and end > 0:
                    try:
                        data = json.loads(obj_text)
                        if isinstance(data, dict):
                            result.append(data)
                    except json.JSONDecodeError:
                        pass
                    i += end
                else:
                    i += 1
            else:
                i += 1
        return result

    async def generate_content(self, goal: str, file_path: str,
                                all_files: list[str] | None = None) -> str:
        """Generate file content for a specific file path using the LLM.

        Includes project context (goal + sibling files) for coherence.

        Returns the generated content string, or a placeholder if generation fails.
        """
        context = f"Project goal: {goal}\n\n"
        if all_files:
            context += "All project files:\n" + "\n".join(f"  - {f}" for f in all_files) + "\n\n"
        prompt = (
            f"{context}"
            f"Generate the COMPLETE content for this file: {file_path}\n"
            f"Include all imports, package declarations, and working code.\n"
            f"Output ONLY the file content inside a single code block. "
            f"Never include multiple code blocks or extra text."
        )
        try:
            result = await complete(
                "code",
                [
                    {"role": "system", "content": "You are a code generator. Output ONLY the file content inside a single code block."},
                    {"role": "user", "content": prompt},
                ],
                timeout=120,
            )
            if result.is_err():
                logger.warning("[TaskResolver] content gen failed for %s: %s",
                               file_path, str(result._error if hasattr(result, '_error') else result))
                return _fallback_content(file_path)
            raw = result.unwrap()
            return _extract_code_block(raw)
        except Exception as e:
            logger.warning("[TaskResolver] content gen exception for %s: %s", file_path, e)
            return _fallback_content(file_path)


task_resolver = TaskResolver()
