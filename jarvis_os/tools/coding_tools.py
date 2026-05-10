from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from ..contracts import ToolSpec
from ..utils import context_workspace_root, resolve_workspace_path
from ..runtime.exceptions import RuntimeBoundaryViolation

_CODE_SUFFIXES = {".py", ".js", ".ts", ".tsx", ".dart", ".json", ".md", ".yaml", ".yml"}
_SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "build", "dist", "__pycache__", ".dart_tool"}


def register_coding_tools(registry) -> None:
    registry.register(
        ToolSpec("generate_code", "Generate starter code from a prompt.", ["prompt"], category="coding"),
        lambda prompt, **_: _generate_code(registry, prompt),
    )
    registry.register(
        ToolSpec("analyze_code", "Analyze a file or directory for code metrics.", ["path"], category="coding", read_only=True),
        lambda path=".", context=None, **_: _analyze_code(path, context=context, default_root=registry.config.workspace_root),
    )
    registry.register(
        ToolSpec("debug_code", "Produce likely debugging guidance from code or an error.", ["text"], category="coding", read_only=True),
        lambda text, **_: _debug_code(text),
    )
    registry.register(
        ToolSpec("coding_agent_loop", "Inspect the workspace, edit files, and rerun tests until the request is satisfied.", ["prompt"], parameters={"prompt": {"type": "string", "required": True}, "path": {"type": "string", "required": False, "default": "."}, "test_command": {"type": "string", "required": False, "default": ""}, "max_attempts": {"type": "integer", "required": False, "default": 3}}, category="coding", permission="elevated", keywords=["fix", "implement", "tests", "patch", "retry"], examples=["fix failing tests", "implement feature in src/app.py"]),
        lambda prompt, path=".", test_command="", max_attempts=3, context=None, **_: _coding_agent_loop(registry, prompt, path=path, test_command=test_command, max_attempts=max_attempts, context=context),
    )
    registry.register(
        ToolSpec("run_python", "Run Python code or a script file.", ["code", "script_path"], category="coding", permission="elevated"),
        lambda code="", script_path="", context=None, **_: _run_python(code=code, script_path=script_path, context=context, default_root=registry.config.workspace_root),
    )
    registry.register(
        ToolSpec("git_status", "Show git status for the current workspace.", [], category="coding", read_only=True),
        lambda context=None, **_: _git_command(["git", "status", "--short"], context=context, default_root=registry.config.workspace_root),
    )
    registry.register(
        ToolSpec("git_commit", "Create a git commit.", ["message"], category="coding", permission="elevated"),
        lambda message, context=None, **_: _git_command(["git", "commit", "-m", message], context=context, default_root=registry.config.workspace_root),
    )
    registry.register(
        ToolSpec("git_push", "Push the current git branch.", [], category="coding", permission="elevated"),
        lambda context=None, **_: _git_command(["git", "push"], context=context, default_root=registry.config.workspace_root),
    )


def _generate_code(registry, prompt: str) -> dict:
    response = registry.models.generate(
        prompt=f"Generate production-grade starter code for: {prompt}",
        task="coding",
        system="Return concise code only when possible.",
    )
    if response.get("ok") and response.get("response"):
        return {"prompt": prompt, "code": response["response"]}
    raise RuntimeBoundaryViolation("Code generation unavailable: model backend did not return usable output.")


def _resolve_path(path: str, context: dict | None = None, default_root: Path | None = None) -> Path:
    return resolve_workspace_path(path, context=context, default_root=default_root)


def _analyze_code(path: str, context: dict | None = None, default_root: Path | None = None) -> dict:
    target = _resolve_path(path, context=context, default_root=default_root)
    if target.is_file():
        text = target.read_text(encoding="utf-8", errors="replace")
        return {
            "path": str(target),
            "lines": len(text.splitlines()),
            "characters": len(text),
            "tbd_count": text.lower().count("tbd"),
        }
    files = [item for item in target.rglob("*") if item.is_file() and item.suffix in {".py", ".js", ".ts", ".tsx", ".dart"}]
    return {"path": str(target), "files": len(files), "sample": [str(item) for item in files[:20]]}


def _debug_code(text: str) -> dict:
    lowered = text.lower()
    findings = []
    if "importerror" in lowered or "modulenotfounderror" in lowered:
        findings.append("Check the active environment and missing dependency installation.")
    if "keyerror" in lowered:
        findings.append("Guard dictionary lookups or verify the incoming payload shape.")
    if "typeerror" in lowered:
        findings.append("Validate argument types and function signatures around the failing call.")
    if not findings:
        findings.append("Capture the stack trace, isolate a repro, and add a failing test before changing code.")
    return {"analysis": findings, "summary": findings[0]}


def _coding_agent_loop(
    registry,
    prompt: str,
    *,
    path: str = ".",
    test_command: str = "",
    max_attempts: int = 3,
    context: dict | None = None,
) -> dict:
    target = _resolve_path(path, context=context, default_root=registry.config.workspace_root)
    workspace_root = target if target.is_dir() else target.parent
    active_test_command = test_command.strip() or _extract_test_command(prompt) or _detect_test_command(workspace_root)
    edit_requested = any(token in prompt.lower() for token in ("fix", "implement", "refactor", "patch", "update", "change", "build", "create"))
    attempts: list[dict] = []
    changed_files: list[str] = []
    git_status = _git_command(["git", "status", "--short"], context={"workspace_root": workspace_root}, default_root=workspace_root)

    for attempt_index in range(1, max(1, int(max_attempts)) + 1):
        test_result = _run_command(active_test_command, cwd=workspace_root) if active_test_command else {
            "success": True,
            "returncode": 0,
            "stdout": "",
            "stderr": "",
            "cwd": str(workspace_root),
            "command": "",
            "note": "No test command was provided or detected.",
        }
        attempt_record = {"attempt": attempt_index, "test": test_result}
        if test_result["success"] and not edit_requested and attempt_index == 1:
            attempts.append(attempt_record)
            return {
                "success": True,
                "prompt": prompt,
                "path": str(target),
                "workspace_root": str(workspace_root),
                "test_command": active_test_command,
                "attempts": attempts,
                "changed_files": changed_files,
                "summary": "Workspace checks already pass; no code edits were required.",
                "git_status": git_status,
            }

        proposal = _propose_edit(registry, prompt, target, workspace_root, test_result, changed_files)
        attempt_record["proposal"] = {"summary": proposal.get("summary", ""), "files": proposal.get("paths", [])}
        if not proposal.get("success", False):
            attempts.append(attempt_record)
            return {
                "success": False,
                "prompt": prompt,
                "path": str(target),
                "workspace_root": str(workspace_root),
                "test_command": active_test_command,
                "attempts": attempts,
                "changed_files": changed_files,
                "summary": proposal.get("error", "No patch could be produced."),
                "git_status": git_status,
            }

        apply_result = _apply_patch_plan(proposal["files"], workspace_root)
        attempt_record["patch"] = apply_result
        attempts.append(attempt_record)
        if not apply_result["success"]:
            return {
                "success": False,
                "prompt": prompt,
                "path": str(target),
                "workspace_root": str(workspace_root),
                "test_command": active_test_command,
                "attempts": attempts,
                "changed_files": changed_files,
                "summary": apply_result.get("error", "Patch application failed."),
                "git_status": git_status,
            }

        changed_files.extend(item for item in apply_result["changed_files"] if item not in changed_files)
        verification = _run_command(active_test_command, cwd=workspace_root) if active_test_command else _compile_changed_files(workspace_root, changed_files)
        attempt_record["verification"] = verification
        if verification["success"]:
            return {
                "success": True,
                "prompt": prompt,
                "path": str(target),
                "workspace_root": str(workspace_root),
                "test_command": active_test_command,
                "attempts": attempts,
                "changed_files": changed_files,
                "summary": proposal.get("summary", "Applied a workspace patch and verification passed."),
                "git_status": git_status,
            }

    final_error = attempts[-1].get("verification", attempts[-1]["test"]).get("stderr", "") if attempts else "No attempts were made."
    return {
        "success": False,
        "prompt": prompt,
        "path": str(target),
        "workspace_root": str(workspace_root),
        "test_command": active_test_command,
        "attempts": attempts,
        "changed_files": changed_files,
        "summary": final_error or "The coding loop exhausted its retries.",
        "git_status": git_status,
    }


def _extract_test_command(prompt: str) -> str:
    match = re.search(r"\b((?:python\s+-m\s+(?:pytest|unittest)[^\n\r]*)|(?:pytest[^\n\r]*)|(?:npm\s+test[^\n\r]*)|(?:flutter\s+test[^\n\r]*))", prompt, flags=re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _detect_test_command(workspace_root: Path) -> str:
    if (workspace_root / "tests").exists():
        return 'python -m unittest discover -s tests -p "test*.py"'
    if list(workspace_root.glob("test_*.py")):
        return 'python -m unittest discover -p "test*.py"'
    return ""


def _candidate_files(target: Path, workspace_root: Path) -> list[Path]:
    if target.is_file():
        return [target]
    files: list[Path] = []
    for item in workspace_root.rglob("*"):
        if item.is_dir() and item.name in _SKIP_DIRS:
            continue
        if not item.is_file():
            continue
        if any(part in _SKIP_DIRS for part in item.parts):
            continue
        if item.suffix.lower() in _CODE_SUFFIXES:
            files.append(item)
        if len(files) >= 8:
            break
    return files


def _propose_edit(registry, prompt: str, target: Path, workspace_root: Path, test_result: dict, changed_files: list[str]) -> dict:
    files = _candidate_files(target, workspace_root)
    if not files:
        return {"success": False, "error": "No candidate source files were found for the coding loop."}
    snippets = []
    for item in files:
        try:
            rel = item.relative_to(workspace_root).as_posix()
        except ValueError:
            rel = item.name
        text = item.read_text(encoding="utf-8", errors="replace")
        snippets.append(f"FILE: {rel}\n{text[:6000]}")
    model_prompt = (
        "You are editing a local repository.\n"
        "Return strict JSON only.\n"
        "Schema: {\"summary\": str, \"files\": [{\"path\": str, \"content\": str}]}\n"
        "Rewrite complete file contents for every changed file.\n"
        f"Goal:\n{prompt}\n\n"
        f"Workspace root: {workspace_root}\n"
        f"Existing changed files: {changed_files}\n"
        f"Verification stdout:\n{test_result.get('stdout', '')[-2000:]}\n\n"
        f"Verification stderr:\n{test_result.get('stderr', '')[-2000:]}\n\n"
        "Candidate files:\n"
        + "\n\n".join(snippets)
    )
    response = registry.models.generate(
        prompt=model_prompt,
        task="coding",
        system="Return valid JSON only. Do not use markdown fences.",
        options={"timeout_s": 20},
    )
    if not response.get("ok") or not response.get("response"):
        return {"success": False, "error": "The coding model did not return a usable patch."}
    payload = _parse_edit_payload(response["response"])
    if payload is None:
        return {"success": False, "error": "The coding model returned invalid patch JSON."}
    files_payload = payload.get("files", [])
    if not files_payload and payload.get("path") and "content" in payload:
        files_payload = [{"path": payload["path"], "content": payload["content"]}]
    normalized = []
    for item in files_payload:
        file_path = str(item.get("path", "")).strip()
        if not file_path:
            continue
        resolved = resolve_workspace_path(file_path, context={"workspace_root": workspace_root})
        normalized.append({"path": str(resolved), "content": str(item.get("content", ""))})
    if not normalized:
        return {"success": False, "error": "The coding model returned no writable files."}
    return {
        "success": True,
        "summary": str(payload.get("summary", "Applied coding loop patch.")),
        "files": normalized,
        "paths": [item["path"] for item in normalized],
    }


def _parse_edit_payload(text: str) -> dict | None:
    body = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", body, flags=re.DOTALL)
    if fenced:
        body = fenced.group(1)
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def _apply_patch_plan(files: list[dict], workspace_root: Path) -> dict:
    changed_files: list[str] = []
    for item in files:
        target = resolve_workspace_path(item["path"], context={"workspace_root": workspace_root})
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(item["content"], encoding="utf-8")
        changed_files.append(str(target))
    return {"success": True, "changed_files": changed_files}


def _compile_changed_files(workspace_root: Path, changed_files: list[str]) -> dict:
    python_files = [item for item in changed_files if item.endswith(".py")]
    if not python_files:
        return {
            "success": True,
            "returncode": 0,
            "stdout": "",
            "stderr": "",
            "cwd": str(workspace_root),
            "command": "",
            "note": "No Python files changed and no test command was available.",
        }
    command = "python -m py_compile " + " ".join(f'"{item}"' for item in python_files)
    return _run_command(command, cwd=workspace_root)


def _run_python(code: str = "", script_path: str = "", context: dict | None = None, default_root: Path | None = None) -> dict:
    if script_path:
        command = ["python", str(_resolve_path(script_path, context=context, default_root=default_root))]
    else:
        command = ["python", "-c", code]
    cwd = str(context_workspace_root(context, default_root))
    completed = subprocess.run(command, capture_output=True, text=True, timeout=60, cwd=cwd)
    return {
        "success": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
        "cwd": cwd,
    }


def _git_command(command: list[str], context: dict | None = None, default_root: Path | None = None) -> dict:
    cwd = str(context_workspace_root(context, default_root))
    completed = subprocess.run(command, capture_output=True, text=True, timeout=60, cwd=cwd)
    return {
        "success": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
        "cwd": cwd,
    }


def _run_command(command: str, *, cwd: Path) -> dict:
    if not command:
        return {"success": True, "returncode": 0, "stdout": "", "stderr": "", "cwd": str(cwd), "command": ""}
    if subprocess.os.name == "nt":
        args = ["powershell", "-NoProfile", "-Command", command]
    else:
        args = ["/bin/sh", "-lc", command]
    completed = subprocess.run(args, capture_output=True, text=True, timeout=120, cwd=str(cwd))
    return {
        "success": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
        "cwd": str(cwd),
        "command": command,
    }
