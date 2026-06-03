"""core/file_agent.py
JARVIS File System Agent — read, write, edit (diff-based), organize, run commands.
Patterns inspired by Aider's EditBlockCoder and Claude Code's file tools.
"""

import os
import re
import json
import difflib
import shutil
import subprocess
import shlex
import logging
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Optional, List

from .llm_router import complete as llm_complete

logger = logging.getLogger("file_agent")

DANGEROUS_COMMANDS = [
    "rm -rf /", "rm -rf ~", "mkfs", "dd if=", "> /dev/sd",
    ":(){ :|:& };:", "chmod -R 000", "mv / /dev/null",
]

MAX_OUTPUT_LINES = 200
MAX_OUTPUT_CHARS = 10000


def confirm(prompt: str) -> bool:
    """Human-in-the-loop confirmation. Returns True if confirmed."""
    try:
        resp = input(f"{prompt} [y/N] ").strip().lower()
        return resp in ("y", "yes")
    except (KeyboardInterrupt, EOFError):
        return False


def format_diff(diff_lines: List[str], context: int = 3) -> str:
    """Format a diff into readable text."""
    return "\n".join(diff_lines)


class JarvisFileAgent:
    """Read, write, edit, list, organize, and run commands."""

    # ── Read ──

    async def read_file(self, path: str) -> str:
        """Read any file and return contents."""
        path = os.path.expanduser(path)
        if not os.path.isfile(path):
            raise FileNotFoundError(f"File not found: {path}")
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()

    # ── Write (with confirmation) ──

    async def write_file(self, path: str, content: str, skip_confirm: bool = False) -> dict:
        """Write content to file, create dirs if needed. Returns {path, size, diff}."""
        path = os.path.expanduser(path)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

        old_content = ""
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                old_content = f.read()

        if old_content == content:
            return {"path": path, "size": len(content), "changed": False, "diff": ""}

        diff = list(difflib.unified_diff(
            old_content.splitlines(keepends=True),
            content.splitlines(keepends=True),
            fromfile=f"a/{os.path.basename(path)}",
            tofile=f"b/{os.path.basename(path)}",
        ))

        if old_content and not skip_confirm:
            print(f"\nChanges to {path}:")
            print("".join(diff[:30]))
            if len(diff) > 30:
                print(f"... ({len(diff) - 30} more lines)")
            if not confirm("Apply these changes?"):
                return {"path": path, "size": 0, "changed": False, "diff": "", "cancelled": True}

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        # Phase 3: Emit hook
        try:
            from core.plugins.events import PluginEventBus
            import asyncio
            asyncio.create_task(PluginEventBus.instance().emit("on_file_saved", path=path, size=len(content)))
        except Exception:
            pass

        return {
            "path": path,
            "size": len(content),
            "changed": old_content != content,
            "diff": "".join(diff),
        }

    # ── Edit (SEARCH/REPLACE block) ──

    async def edit_file(self, path: str, search_text: str, replace_text: str,
                        skip_confirm: bool = False) -> dict:
        """Aider-style SEARCH/REPLACE edit. Finds search_text, replaces with replace_text.
        Uses difflib fuzzy matching if exact match not found.
        Returns {path, matches, replacements, diff, error}."""
        path = os.path.expanduser(path)
        if not os.path.isfile(path):
            return {"path": path, "error": f"File not found: {path}"}

        content = await self.read_file(path)

        # Try exact match first
        if search_text in content:
            new_content = content.replace(search_text, replace_text, 1)
            exact = True
        else:
            exact = False
            # Fuzzy match: find the closest block using difflib
            search_lines = search_text.splitlines()
            content_lines = content.splitlines()
            matcher = difflib.SequenceMatcher(None, content_lines, search_lines)
            match = matcher.find_longest_match(0, len(content_lines), 0, len(search_lines))

            if match.size < max(3, len(search_lines) * 0.3):
                return {
                    "path": path,
                    "error": f"Could not find matching text in {path}",
                    "exact_found": False,
                }

            start = match.a
            end = match.a + match.size
            replace_lines = replace_text.splitlines()
            new_lines = content_lines[:start] + replace_lines + content_lines[end:]
            new_content = "\n".join(new_lines)

        diff = list(difflib.unified_diff(
            content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{os.path.basename(path)}",
            tofile=f"b/{os.path.basename(path)}",
        ))

        if not skip_confirm:
            print(f"\nEditing {path}:")
            print("".join(diff[:30]))
            if len(diff) > 30:
                print(f"... ({len(diff) - 30} more lines)")
            if not confirm("Apply this edit?"):
                return {"path": path, "changed": False, "diff": "", "cancelled": True}

        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)

        return {
            "path": path,
            "exact_match": exact,
            "changed": content != new_content,
            "diff": "".join(diff),
        }

    # ── List files ──

    async def list_files(self, folder_path: str, pattern: str = "",
                         recursive: bool = False) -> list:
        """List files in a folder, optionally filtered by pattern."""
        folder_path = os.path.expanduser(folder_path)
        if not os.path.isdir(folder_path):
            return []
        files = []
        if recursive:
            for root, dirs, fnames in os.walk(folder_path):
                for f in fnames:
                    full = os.path.join(root, f)
                    if pattern and pattern not in f:
                        continue
                    stat = os.stat(full)
                    rel = os.path.relpath(full, folder_path)
                    files.append({
                        "name": rel,
                        "path": full,
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    })
        else:
            for f in os.listdir(folder_path):
                full = os.path.join(folder_path, f)
                if not os.path.isfile(full):
                    continue
                if pattern and pattern not in f:
                    continue
                stat = os.stat(full)
                files.append({
                    "name": f,
                    "path": full,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })
        return sorted(files, key=lambda x: x["name"])

    # ── Tree view ──

    async def tree_view(self, folder_path: str, max_depth: int = 2,
                        max_files: int = 50) -> str:
        """Return a directory tree as a string (like the `tree` command)."""
        folder_path = os.path.expanduser(folder_path)
        if not os.path.isdir(folder_path):
            return f"[Not a directory: {folder_path}]"

        lines = [f"{os.path.basename(folder_path) or folder_path}/"]
        count = [0]

        def _walk(dirpath: str, depth: int, prefix: str = ""):
            if count[0] >= max_files:
                return
            try:
                entries = sorted(os.listdir(dirpath))
            except PermissionError:
                lines.append(f"{prefix}  [permission denied]")
                return

            entries = [e for e in entries if not e.startswith(".")]
            for i, entry in enumerate(entries):
                if count[0] >= max_files:
                    lines.append(f"{prefix}  ... ({max_files}+ items)")
                    return
                full = os.path.join(dirpath, entry)
                is_last = (i == len(entries) - 1)
                connector = "└── " if is_last else "├── "
                is_dir = os.path.isdir(full)
                suffix = "/" if is_dir else ""
                size = ""
                if not is_dir:
                    try:
                        size = f" ({os.path.getsize(full)} bytes)"
                    except OSError:
                        pass
                lines.append(f"{prefix}{connector}{entry}{suffix}{size}")
                count[0] += 1
                if is_dir and depth < max_depth:
                    next_prefix = prefix + ("    " if is_last else "│   ")
                    _walk(full, depth + 1, next_prefix)

        _walk(folder_path, 0)
        return "\n".join(lines)

    # ── Run command ──

    async def run_command(self, cmd: str, cwd: Optional[str] = None,
                          timeout: int = 30, skip_confirm: bool = False) -> dict:
        """Run a shell command in a sandboxed subprocess. Returns {stdout, stderr, returncode, error}."""
        cwd = os.path.expanduser(cwd) if cwd else os.getcwd()

        # Security check
        cmd_lower = cmd.lower().strip()
        for dangerous in DANGEROUS_COMMANDS:
            if dangerous in cmd_lower:
                return {"error": f"Command blocked (dangerous pattern): {dangerous}"}

        if not skip_confirm:
            print(f"\nCommand to run: {cmd}")
            print(f"Working dir: {cwd}")
            if not confirm("Execute this command?"):
                return {"stdout": "", "stderr": "", "returncode": -1, "cancelled": True}

        try:
            import shlex as _shlex
            try:
                # Prefer running without a shell for safety
                if isinstance(cmd, str):
                    args = _shlex.split(cmd)
                else:
                    args = cmd
                result = subprocess.run(
                    args,
                    shell=False,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
            except (FileNotFoundError, OSError):
                # Fallback by invoking a platform shell interpreter without shell=True
                if isinstance(cmd, str):
                    if os.name == 'nt':
                        fallback_args = ["cmd", "/c", cmd]
                    else:
                        fallback_args = ["bash", "-lc", cmd]
                else:
                    if os.name == 'nt':
                        fallback_args = ["cmd", "/c"] + list(cmd)
                    else:
                        fallback_args = ["bash", "-lc", " ".join(map(str, cmd))]

                result = subprocess.run(
                    fallback_args,
                    shell=False,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )

            stdout = result.stdout[-MAX_OUTPUT_CHARS:] if result.stdout else ""
            stderr = result.stderr[-MAX_OUTPUT_CHARS:] if result.stderr else ""

            if len(result.stdout or "") > MAX_OUTPUT_CHARS:
                stdout = f"[truncated to {MAX_OUTPUT_CHARS} chars]\n" + stdout
            if len(result.stderr or "") > MAX_OUTPUT_CHARS:
                stderr = f"[truncated to {MAX_OUTPUT_CHARS} chars]\n" + stderr

            return {
                "stdout": stdout,
                "stderr": stderr,
                "returncode": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"error": f"Command timed out after {timeout}s", "stdout": "", "stderr": "", "returncode": -1}
        except Exception as e:
            return {"error": str(e), "stdout": "", "stderr": "", "returncode": -1}

    # ── Organize folder (existing, enhanced) ──

    async def organize_folder(self, folder_path: str, instruction: str,
                              skip_confirm: bool = False) -> dict:
        folder_path = os.path.expanduser(folder_path)
        if not os.path.isdir(folder_path):
            return {"error": f"Not a directory: {folder_path}"}

        if not skip_confirm:
            print(f"\nOrganize folder: {folder_path}")
            print(f"Instruction: {instruction}")
            if not confirm("Proceed with organization?"):
                return {"cancelled": True}

        entries = os.listdir(folder_path)
        files = [e for e in entries if os.path.isfile(os.path.join(folder_path, e))]
        dirs_ = [e for e in entries if os.path.isdir(os.path.join(folder_path, e))]
        prompt = f"""Folder: {folder_path}
Files: {json.dumps(files[:50])}
Subdirs: {json.dumps(dirs_[:20])}
Instruction: {instruction}

Generate a JSON plan to organize this folder. Return ONLY:
{{"actions":[{{"type":"move|rename|create_dir","source":"...","target":"...","dir_name":"..."}}],"summary":"one line summary"}}"""
        try:
            result = (await llm_complete("analysis", [{"role": "user", "content": prompt}])).unwrap_or("")
            content = result.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            plan = json.loads(content)
        except Exception as e:
            return {"moved": [], "renamed": [], "created": [], "summary": f"Planning failed: {e}"}

        return await self._execute_file_plan(folder_path, plan)

    async def _execute_file_plan(self, folder_path: str, plan: dict) -> dict:
        moved = []
        renamed = []
        created = []
        for action in plan.get("actions", []):
            try:
                t = action.get("type", "")
                if t == "create_dir":
                    target = os.path.join(folder_path, action["dir_name"])
                    os.makedirs(target, exist_ok=True)
                    created.append(action["dir_name"])
                elif t == "move":
                    src = os.path.join(folder_path, action["source"])
                    dst = os.path.join(folder_path, action["target"])
                    if os.path.exists(src):
                        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
                        shutil.move(src, dst)
                        moved.append(f"{action['source']} -> {action['target']}")
                elif t == "rename":
                    src = os.path.join(folder_path, action["source"])
                    dst = os.path.join(folder_path, action["target"])
                    if os.path.exists(src):
                        os.rename(src, dst)
                        renamed.append(f"{action['source']} -> {action['target']}")
            except Exception as e:
                logger.warning(f"[FILE_AGENT] Action failed: {action} - {e}")
        return {
            "moved": moved,
            "renamed": renamed,
            "created": created,
            "summary": plan.get("summary", f"Processed {len(moved)} moves, {len(renamed)} renames, {len(created)} dirs"),
        }

    # ── Generate document (existing) ──

    async def generate_document(self, template: str, data: dict, output_path: str,
                                skip_confirm: bool = False) -> dict:
        """Generate a document from template + data, save to path."""
        prompt = f"""Template: {template}
Data: {json.dumps(data, default=str)}
Generate the filled document. Return ONLY the final content, no explanation."""
        content = (await llm_complete("creative", [{"role": "user", "content": prompt}])).unwrap_or("")
        return await self.write_file(output_path, content.strip(), skip_confirm=skip_confirm)


file_agent = JarvisFileAgent()
