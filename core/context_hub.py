# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import logging
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class ContextHub:
    def __init__(self, workspace_root: str | None = None):
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else Path.cwd().resolve()

    async def gather(self, task_type: str = "auto", prompt: str = "") -> dict:
        context = {
            "workspace": await self._workspace_snapshot(),
            "git": await self._git_context(),
            "system": self._system_context(),
            "task_type": task_type,
            "prompt": prompt,
            "gathered_at": datetime.now(UTC).isoformat(),
        }
        if "test" in prompt.lower() or task_type == "test":
            context["test_framework"] = await self._detect_test_framework()
        if "depend" in prompt.lower() or "install" in prompt.lower():
            context["dependencies"] = self._detect_dependencies()
        return context

    async def _workspace_snapshot(self) -> dict:
        root = self.workspace_root
        result = {"root": str(root), "files": [], "manifests": {}}
        try:
            for entry in sorted(root.iterdir())[:30]:
                if entry.name.startswith(".") or entry.name == "__pycache__":
                    continue
                info = {"name": entry.name, "type": "dir" if entry.is_dir() else "file"}
                if entry.is_file():
                    info["size"] = entry.stat().st_size
                result["files"].append(info)
        except (PermissionError, OSError):
            pass
        for manifest_name in ("package.json", "Cargo.toml", "pyproject.toml", "go.mod", "Gemfile", "requirements.txt"):
            mf = root / manifest_name
            if mf.exists():
                try:
                    result["manifests"][manifest_name] = mf.read_text(encoding="utf-8", errors="replace")[:2000]
                except Exception as e:
                    logger.exception("[ContextHub] reading manifest %s: %s", manifest_name, e)
        readme = root / "README.md"
        if readme.exists():
            result["readme"] = readme.read_text(encoding="utf-8", errors="replace")[:1000]
        return result

    async def _git_context(self) -> dict:
        result = {"available": False, "branch": "", "status": "", "diff": "", "commits": []}
        try:
            subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=self.workspace_root, capture_output=True, timeout=5, check=True
            )
            result["available"] = True
        except (subprocess.CalledProcessError, FileNotFoundError, TimeoutError):
            return result
        try:
            branch = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=self.workspace_root, capture_output=True, text=True, timeout=5
            )
            result["branch"] = branch.stdout.strip()
        except Exception as e:
            logger.exception("[ContextHub] getting git branch: %s", e)
        try:
            status = subprocess.run(
                ["git", "status", "--short"],
                cwd=self.workspace_root, capture_output=True, text=True, timeout=5
            )
            result["status"] = status.stdout.strip()
        except Exception as e:
            logger.exception("[ContextHub] getting git status: %s", e)
        try:
            diff = subprocess.run(
                ["git", "diff", "--stat"],
                cwd=self.workspace_root, capture_output=True, text=True, timeout=5
            )
            result["diff"] = diff.stdout.strip()
        except Exception as e:
            logger.exception("[ContextHub] getting git diff: %s", e)
        try:
            log = subprocess.run(
                ["git", "log", "--oneline", "-10"],
                cwd=self.workspace_root, capture_output=True, text=True, timeout=5
            )
            result["commits"] = [l.strip() for l in log.stdout.strip().split("\n") if l.strip()]
        except Exception as e:
            logger.exception("[ContextHub] getting git log: %s", e)
        return result

    def _system_context(self) -> dict:
        return {
            "platform": sys.platform,
            "python": sys.version.split()[0],
            "cwd": str(Path.cwd().resolve()),
            "env": {
                k: v for k, v in sorted(os.environ.items())
                if not k.startswith("_") and not any(sec in k.lower() for sec in ("key", "token", "secret", "password", "auth"))
            },
        }

    def _detect_dependencies(self) -> list:
        deps = []
        root = self.workspace_root
        req = root / "requirements.txt"
        if req.exists():
            deps = [l.strip() for l in req.read_text().strip().split("\n") if l.strip() and not l.startswith("#")]
        return deps

    async def _detect_test_framework(self) -> str | None:
        root = self.workspace_root
        if (root / "pytest.ini").exists() or (root / "pyproject.toml").exists():
            try:
                content = (root / "pyproject.toml").read_text()
                if "pytest" in content:
                    return "pytest"
            except Exception as e:
                logger.exception("[ContextHub] detecting test framework: %s", e)
        if (root / "jest.config.js").exists() or (root / "jest.config.ts").exists():
            return "jest"
        if (root / "Cargo.toml").exists():
            return "cargo test"
        if (root / "go.mod").exists():
            return "go test"
        return None

    def format_for_prompt(self, ctx: dict, max_chars: int = 4000) -> str:
        parts = []
        ws = ctx.get("workspace", {})
        parts.append(f"[Workspace: {ws.get('root', '?')}]")
        files = ws.get("files", [])
        if files:
            parts.append(f"Top files ({len(files)}): {', '.join(f['name'] for f in files[:15])}")
        manifests = ws.get("manifests", {})
        for name, content in manifests.items():
            parts.append(f"[{name}]\n{content[:800]}")
        git = ctx.get("git", {})
        if git.get("available"):
            parts.append(f"[Git: {git.get('branch', '?')}]")
            if git.get("status"):
                parts.append(f"Changes:\n{git['status'][:500]}")
            if git.get("diff"):
                parts.append(f"Diff stats:\n{git['diff'][:300]}")
            if git.get("commits"):
                parts.append(f"Recent: {' | '.join(git['commits'][:5])}")
        sys_info = ctx.get("system", {})
        parts.append(f"[{sys_info.get('platform', '?')} | Python {sys_info.get('python', '?')}]")
        result = "\n".join(parts)
        if len(result) > max_chars:
            result = result[:max_chars] + "\n...[truncated]"
        return result
