from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from core.providers.base import (
    ExecutionProvider,
    ExecutionResult,
    ProviderCapabilities,
    ProviderHealth,
    ProviderHealthStatus,
)

logger = logging.getLogger(__name__)


class GitHubProvider(ExecutionProvider):
    provider_id = "github"
    name = "GitHub Integration"
    version = "1.0.0"
    priority = 10
    installed = True

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            capability_names=[
                "github",
                "git",
                "version_control",
                "pull_request",
                "code_review",
                "repository",
                "ci_cd",
            ],
            features=[
                "clone",
                "push",
                "pull",
                "branch",
                "pr_create",
                "pr_merge",
                "issue_list",
                "repo_info",
                "commit",
                "release",
            ],
        )

    async def health(self) -> ProviderHealth:
        try:
            result = subprocess.run(
                ["git", "--version"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return ProviderHealth(
                    status=ProviderHealthStatus.HEALTHY,
                    latency_ms=0.0,
                    last_checked=time.time(),
                )
        except Exception as e:
            logger.debug("[GitHubProvider] Health check failed: %s", e)
        return ProviderHealth(
            status=ProviderHealthStatus.DEGRADED,
            error="Git CLI unavailable",
            last_checked=time.time(),
        )

    async def execute(self, task: dict[str, Any], context: dict[str, Any] | None = None) -> ExecutionResult:
        start = time.monotonic()
        action = task.get("action", task.get("capability", "repo_info"))
        repo_path = task.get("repo_path", task.get("path", os.getcwd()))
        repo_url = task.get("repo_url", task.get("url", ""))
        branch = task.get("branch", "main")
        message = task.get("message", "")
        pr_title = task.get("pr_title", task.get("title", ""))
        pr_body = task.get("pr_body", task.get("body", ""))
        issue_number = task.get("issue_number", 0)
        tag_name = task.get("tag_name", "")

        try:
            if action in ("repo_info", "status"):
                return await self._git_status(repo_path, start)
            elif action == "clone":
                return self._git_clone(repo_url, repo_path, branch, start)
            elif action == "pull":
                return self._git_pull(repo_path, branch, start)
            elif action == "push":
                return self._git_push(repo_path, branch, start)
            elif action == "branch":
                return self._git_branch(repo_path, start)
            elif action == "commit":
                return await self._git_commit(repo_path, message, start)
            elif action == "log":
                return self._git_log(repo_path, task.get("count", 10), start)
            elif action == "diff":
                return self._git_diff(repo_path, task.get("ref", ""), start)
            elif action == "pr_list":
                return await self._gh_pr_list(repo_path, task.get("state", "open"), start)
            elif action == "pr_create":
                return await self._gh_pr_create(repo_path, pr_title, pr_body, branch, task.get("base", "main"), start)
            elif action == "pr_merge":
                return await self._gh_pr_merge(repo_path, issue_number, start)
            elif action == "issue_list":
                return await self._gh_issue_list(repo_path, task.get("state", "open"), start)
            elif action == "release":
                return await self._gh_release(repo_path, tag_name, message, start)
            else:
                elapsed = (time.monotonic() - start) * 1000
                return ExecutionResult(
                    success=False, output="",
                    error=f"Unknown github action: {action}", exit_code=1,
                    duration_ms=elapsed, metadata={"provider": "github"},
                )
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            logger.exception("[GitHubProvider] Action %s failed: %s", action, e)
            return ExecutionResult(
                success=False, output="", error=str(e), exit_code=1,
                duration_ms=elapsed, metadata={"provider": "github"},
            )

    def _git(self, args: list[str], cwd: str | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git"] + args,
            capture_output=True, text=True, timeout=60,
            cwd=cwd,
        )

    async def _git_status(self, repo_path: str, start: float) -> ExecutionResult:
        r = self._git(["status", "--short", "--branch"], repo_path)
        elapsed = (time.monotonic() - start) * 1000
        return ExecutionResult(
            success=r.returncode == 0,
            output=r.stdout[:8000],
            error=r.stderr[:2000] if r.returncode != 0 else "",
            exit_code=r.returncode,
            duration_ms=elapsed,
            metadata={"provider": "github", "action": "status"},
        )

    def _git_clone(self, url: str, path: str, branch: str, start: float) -> ExecutionResult:
        cmd = ["clone", "--depth", "1"]
        if branch:
            cmd.extend(["--branch", branch])
        cmd.extend([url, path])
        r = self._git(cmd)
        elapsed = (time.monotonic() - start) * 1000
        return ExecutionResult(
            success=r.returncode == 0,
            output=r.stdout[:5000],
            error=r.stderr[:2000] if r.returncode != 0 else "",
            exit_code=r.returncode,
            duration_ms=elapsed,
            metadata={"provider": "github", "action": "clone"},
        )

    def _git_pull(self, repo_path: str, branch: str, start: float) -> ExecutionResult:
        r = self._git(["pull", "origin", branch], repo_path)
        elapsed = (time.monotonic() - start) * 1000
        return ExecutionResult(
            success=r.returncode == 0,
            output=r.stdout[:5000],
            error=r.stderr[:2000] if r.returncode != 0 else "",
            exit_code=r.returncode,
            duration_ms=elapsed,
            metadata={"provider": "github", "action": "pull"},
        )

    def _git_push(self, repo_path: str, branch: str, start: float) -> ExecutionResult:
        r = self._git(["push", "origin", branch], repo_path)
        elapsed = (time.monotonic() - start) * 1000
        return ExecutionResult(
            success=r.returncode == 0,
            output=r.stdout[:5000],
            error=r.stderr[:2000] if r.returncode != 0 else "",
            exit_code=r.returncode,
            duration_ms=elapsed,
            metadata={"provider": "github", "action": "push"},
        )

    def _git_branch(self, repo_path: str, start: float) -> ExecutionResult:
        r = self._git(["branch", "-a"], repo_path)
        elapsed = (time.monotonic() - start) * 1000
        return ExecutionResult(
            success=r.returncode == 0,
            output=r.stdout[:5000],
            error=r.stderr[:2000] if r.returncode != 0 else "",
            exit_code=r.returncode,
            duration_ms=elapsed,
            metadata={"provider": "github", "action": "branch"},
        )

    async def _git_commit(self, repo_path: str, message: str, start: float) -> ExecutionResult:
        r_add = self._git(["add", "-A"], repo_path)
        if r_add.returncode != 0:
            elapsed = (time.monotonic() - start) * 1000
            return ExecutionResult(
                success=False, output="",
                error=f"git add failed: {r_add.stderr[:2000]}",
                exit_code=r_add.returncode, duration_ms=elapsed,
                metadata={"provider": "github", "action": "commit"},
            )
        r = self._git(["commit", "-m", message or "update"], repo_path)
        elapsed = (time.monotonic() - start) * 1000
        return ExecutionResult(
            success=r.returncode == 0,
            output=r.stdout[:5000],
            error=r.stderr[:2000] if r.returncode != 0 else "",
            exit_code=r.returncode,
            duration_ms=elapsed,
            metadata={"provider": "github", "action": "commit"},
        )

    def _git_log(self, repo_path: str, count: int, start: float) -> ExecutionResult:
        r = self._git(["log", f"--max-count={count}", "--oneline", "--graph"], repo_path)
        elapsed = (time.monotonic() - start) * 1000
        return ExecutionResult(
            success=r.returncode == 0,
            output=r.stdout[:5000],
            error=r.stderr[:2000] if r.returncode != 0 else "",
            exit_code=r.returncode,
            duration_ms=elapsed,
            metadata={"provider": "github", "action": "log"},
        )

    def _git_diff(self, repo_path: str, ref: str, start: float) -> ExecutionResult:
        args = ["diff"]
        if ref:
            args.append(ref)
        r = self._git(args, repo_path)
        elapsed = (time.monotonic() - start) * 1000
        return ExecutionResult(
            success=r.returncode == 0,
            output=r.stdout[:10000],
            error=r.stderr[:2000] if r.returncode != 0 else "",
            exit_code=r.returncode,
            duration_ms=elapsed,
            metadata={"provider": "github", "action": "diff"},
        )

    async def _gh_pr_list(self, repo_path: str, state: str, start: float) -> ExecutionResult:
        try:
            r = subprocess.run(
                ["gh", "pr", "list", f"--state={state}", "--json", "number,title,state,headRefName,baseRefName,url",
                 "--limit", "30"],
                capture_output=True, text=True, timeout=30, cwd=repo_path,
            )
            elapsed = (time.monotonic() - start) * 1000
            if r.returncode == 0 and r.stdout.strip():
                prs = json.loads(r.stdout)
                lines = [f"#{p['number']} [{p['state']}] {p['title']} ({p['headRefName']}->{p['baseRefName']})" for p in prs]
                return ExecutionResult(
                    success=True,
                    output=f"Pull Requests ({len(prs)}):\n" + "\n".join(lines),
                    exit_code=0, duration_ms=elapsed,
                    metadata={"provider": "github", "action": "pr_list", "count": len(prs)},
                )
            return ExecutionResult(
                success=True, output="No pull requests found.",
                exit_code=0, duration_ms=elapsed,
                metadata={"provider": "github", "action": "pr_list"},
            )
        except FileNotFoundError:
            elapsed = (time.monotonic() - start) * 1000
            return ExecutionResult(
                success=False, output="",
                error="gh CLI not installed", exit_code=1,
                duration_ms=elapsed, metadata={"provider": "github"},
            )

    async def _gh_pr_create(self, repo_path: str, title: str, body: str, head: str, base: str, start: float) -> ExecutionResult:
        try:
            r = subprocess.run(
                ["gh", "pr", "create", "--title", title or "Update", "--body", body or "",
                 "--head", head, "--base", base],
                capture_output=True, text=True, timeout=30, cwd=repo_path,
            )
            elapsed = (time.monotonic() - start) * 1000
            return ExecutionResult(
                success=r.returncode == 0,
                output=r.stdout[:5000] if r.returncode == 0 else r.stderr[:2000],
                error=r.stderr[:2000] if r.returncode != 0 else "",
                exit_code=r.returncode, duration_ms=elapsed,
                metadata={"provider": "github", "action": "pr_create"},
            )
        except FileNotFoundError:
            elapsed = (time.monotonic() - start) * 1000
            return ExecutionResult(
                success=False, output="",
                error="gh CLI not installed", exit_code=1,
                duration_ms=elapsed, metadata={"provider": "github"},
            )

    async def _gh_pr_merge(self, repo_path: str, pr_number: int, start: float) -> ExecutionResult:
        try:
            r = subprocess.run(
                ["gh", "pr", "merge", str(pr_number), "--merge", "--subject", "Merged via JARVIS"],
                capture_output=True, text=True, timeout=30, cwd=repo_path,
            )
            elapsed = (time.monotonic() - start) * 1000
            return ExecutionResult(
                success=r.returncode == 0,
                output=r.stdout[:5000],
                error=r.stderr[:2000] if r.returncode != 0 else "",
                exit_code=r.returncode, duration_ms=elapsed,
                metadata={"provider": "github", "action": "pr_merge"},
            )
        except FileNotFoundError:
            elapsed = (time.monotonic() - start) * 1000
            return ExecutionResult(
                success=False, output="",
                error="gh CLI not installed", exit_code=1,
                duration_ms=elapsed, metadata={"provider": "github"},
            )

    async def _gh_issue_list(self, repo_path: str, state: str, start: float) -> ExecutionResult:
        try:
            r = subprocess.run(
                ["gh", "issue", "list", f"--state={state}", "--json", "number,title,state,labels,url",
                 "--limit", "30"],
                capture_output=True, text=True, timeout=30, cwd=repo_path,
            )
            elapsed = (time.monotonic() - start) * 1000
            if r.returncode == 0 and r.stdout.strip():
                issues = json.loads(r.stdout)
                lines = [f"#{i['number']} [{i['state']}] {i['title']}" for i in issues]
                return ExecutionResult(
                    success=True,
                    output=f"Issues ({len(issues)}):\n" + "\n".join(lines),
                    exit_code=0, duration_ms=elapsed,
                    metadata={"provider": "github", "action": "issue_list", "count": len(issues)},
                )
            return ExecutionResult(
                success=True, output="No issues found.",
                exit_code=0, duration_ms=elapsed,
                metadata={"provider": "github", "action": "issue_list"},
            )
        except FileNotFoundError:
            elapsed = (time.monotonic() - start) * 1000
            return ExecutionResult(
                success=False, output="",
                error="gh CLI not installed", exit_code=1,
                duration_ms=elapsed, metadata={"provider": "github"},
            )

    async def _gh_release(self, repo_path: str, tag: str, notes: str, start: float) -> ExecutionResult:
        try:
            r = subprocess.run(
                ["gh", "release", "create", tag, "--title", tag,
                 "--notes", notes or f"Release {tag}", "--generate-notes"],
                capture_output=True, text=True, timeout=30, cwd=repo_path,
            )
            elapsed = (time.monotonic() - start) * 1000
            return ExecutionResult(
                success=r.returncode == 0,
                output=r.stdout[:5000],
                error=r.stderr[:2000] if r.returncode != 0 else "",
                exit_code=r.returncode, duration_ms=elapsed,
                metadata={"provider": "github", "action": "release"},
            )
        except FileNotFoundError:
            elapsed = (time.monotonic() - start) * 1000
            return ExecutionResult(
                success=False, output="",
                error="gh CLI not installed", exit_code=1,
                duration_ms=elapsed, metadata={"provider": "github"},
            )

    async def handle_tool(
        self, tool_type: str, content: str, **kwargs: Any,
    ) -> ExecutionResult | None:
        if not tool_type.startswith("github_"):
            return None
        action_map: dict[str, str] = {
            "github_status": "status",
            "github_clone": "clone",
            "github_pull": "pull",
            "github_push": "push",
            "github_branch": "branch",
            "github_commit": "commit",
            "github_log": "log",
            "github_diff": "diff",
            "github_pr_list": "pr_list",
            "github_pr_create": "pr_create",
            "github_pr_merge": "pr_merge",
            "github_issue_list": "issue_list",
            "github_release": "release",
        }
        action = action_map.get(tool_type)
        if action is None:
            return None
        task: dict[str, Any] = {"action": action, **kwargs}
        if content.strip():
            if action == "clone":
                task["repo_url"] = content.strip()
            elif action == "commit":
                task["message"] = content.strip()
        return await self.execute(task)

    async def estimate_cost(self, task: dict[str, Any]) -> float:
        return 0.0

    async def estimate_latency(self, task: dict[str, Any]) -> float:
        return 500.0
