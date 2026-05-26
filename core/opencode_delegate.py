import os
import sys
import asyncio
from pathlib import Path
from typing import Optional


async def delegate_to_opencode(
    task: str,
    workspace: Optional[str] = None,
    context: Optional[dict] = None,
    timeout: int = 300,
) -> dict:
    if not _opencode_available():
        return {"error": "opencode not found on PATH", "success": False}

    workspace = workspace or str(Path.cwd().resolve())
    opencode_exe = _find_opencode_path() or "opencode"

    try:
        is_cmd = opencode_exe.endswith(".cmd") if opencode_exe else False

        if is_cmd:
            cmd = f'"{opencode_exe}" run "{task}" --dir "{workspace}" --dangerously-skip-permissions'
            proc = await asyncio.create_subprocess_shell(
                cmd,
                cwd=workspace,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        else:
            cmd = [
                opencode_exe, "run", task,
                "--dir", workspace,
                "--dangerously-skip-permissions",
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=workspace,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {
                "success": False,
                "error": f"Timeout after {timeout}s",
                "stdout": "",
                "stderr": "",
                "returncode": -1,
            }

        stdout_str = stdout.decode("utf-8", errors="replace") if stdout else ""
        stderr_str = stderr.decode("utf-8", errors="replace") if stderr else ""

        return {
            "success": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": stdout_str,
            "stderr": stderr_str,
        }
    except Exception as e:
        return {"error": str(e), "success": False}


def _opencode_available() -> bool:
    return _find_opencode_path() is not None


def _find_opencode_path() -> Optional[str]:
    # Prefer .cmd on Windows (create_subprocess_exec can't resolve PATHEXT)
    if sys.platform == "win32":
        npm_cmd = Path(os.environ.get("APPDATA", "")) / "npm" / "opencode.cmd"
        if npm_cmd.exists():
            return str(npm_cmd)
    try:
        import subprocess
        result = subprocess.run(
            ["opencode", "--version"],
            capture_output=True, timeout=10, check=True
        )
        if result.returncode == 0:
            return "opencode"
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        pass
    # Fallback: search with 'where' on Windows or 'which' on Unix
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["where", "opencode"], capture_output=True, text=True, timeout=10
            )
        else:
            result = subprocess.run(
                ["which", "opencode"], capture_output=True, text=True, timeout=10
            )
        if result.returncode == 0 and result.stdout.strip():
            path = result.stdout.strip().split("\n")[0].strip()
            return path if os.path.isfile(path) else path
    except Exception:
        pass
    return None


def _build_task_prompt(task: str, workspace: str, context: Optional[dict] = None) -> str:
    parts = []
    parts.append("# Task\n")
    parts.append(task)
    parts.append("")

    if context:
        ch = context.get("context_hub")
        if ch:
            formatted = ch.format_for_prompt(context)
            parts.append("## Context\n")
            parts.append(formatted)
            parts.append("")

        extra = context.get("extra_context", "")
        if extra:
            parts.append("## Additional Context\n")
            parts.append(extra)
            parts.append("")

    parts.append("## Output Requirements\n")
    parts.append("- Make changes directly to files in the workspace.")
    parts.append("- Use diff-based editing where possible.")
    parts.append("- Report what was done and any warnings.")
    parts.append("")

    parts.append(f"Workspace: {workspace}")
    parts.append("")

    return "\n".join(parts)


def is_opencode_task(prompt: str) -> bool:
    lowered = prompt.lower()
    triggers = [
        "refactor", "restructure", "rewrite", "migrate",
        "implement", "add feature", "create module", "build component",
        "fix bug", "debug", "optimize",
        "write tests", "add test", "test coverage",
        "set up", "scaffold", "boilerplate",
        "code review", "review code",
    ]
    return any(t in lowered for t in triggers)
