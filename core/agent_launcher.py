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
"""core/agent_launcher.py
Subprocess manager for CLI coding agents.
Launches agents in project directory, pipes I/O, handles auto-approval,
and API key rotation on 429 rate limits.
"""
import asyncio
import logging
import os
import re
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from core.api_key_vault import vault

logger = logging.getLogger("agent_launcher")

# Map agent name → vault service name for key rotation
AGENT_SERVICE_MAP: dict[str, str | None] = {
    "codex": "openai",
    "aider": "openai",
    "gemini": "gemini",
    "copilot": "github",
    "gh": "github",
    "jules": "anthropic",
    "opencode": None,
    "shell": None,
}

# Map agent name → env var to set before launch
AGENT_ENV_VAR_MAP: dict[str, str | None] = {
    "codex": "OPENAI_API_KEY",
    "aider": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "copilot": "GITHUB_TOKEN",
    "gh": "GITHUB_TOKEN",
    "jules": "ANTHROPIC_API_KEY",
    "opencode": None,
    "shell": None,
}

RATE_LIMIT_PATTERNS = [
    rb"429", rb"rate.limit", rb"rate_limit", rb"too many requests",
    rb"quota exceeded", rb"quota_exceeded", rb"insufficient_quota",
    rb"resource_exhausted", rb"status 429", rb"http 429",
    rb"API key exhausted", rb"api key limit", rb"exceeded your",
    rb"retry after", rb"retry_after", rb"try again later",
]

AGENT_COMMANDS = {
    "opencode": ["opencode", "run", "{task}", "--dir", "{workspace}", "--dangerously-skip-permissions"],
    "aider": ["aider", "--yes", "--no-autocommit", "--no-suggest-shell-commands", "--message", "{task}"],
    "codex": ["codex", "{task}", "--yes"],
    "gemini": ["gemini", "run", "{task}"],
    "copilot": ["copilot", "explain", "{task}"],
    "gh": ["gh", "{task}"],
    "jules": ["jules", "run", "{task}"],
    "shell": ["{task}"],
}

AUTO_APPROVE_PATTERNS = [
    rb"Continue\?.*\[y\/n\]", rb"Proceed\?.*\(Y\/n\)",
    rb"Are you sure\?.*\[y\/N\]", rb"Approve changes\?.*\[y\/n\]",
    rb"\[y\/n\]", rb"\(y\/n\)", rb"\(Y\/n\)",
    rb"Do you want to continue\?",
    rb"This will modify files.*Continue\?",
]

INTERACTIVE_PATTERNS = [
    rb"password:", rb"API key:", rb"token:", rb"secret:",
]

@dataclass
class AgentResult:
    agent: str
    exit_code: int
    stdout: str
    stderr: str
    duration: float
    timed_out: bool = False
    task: str = ""

@dataclass
class AgentSession:
    agent: str
    task: str
    workspace: str
    process: asyncio.subprocess.Process
    start_time: float
    stdout_lines: list = field(default_factory=list)

class AgentLauncher:
    def __init__(self, workspace: str, auto_approve: bool = True, max_key_retries: int = 3):
        self.workspace = Path(workspace).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.auto_approve = auto_approve
        self.max_key_retries = max_key_retries
        self.active_sessions: dict[str, AgentSession] = {}
        self._approval_count = 0
        self._key_retries: dict[str, int] = {}

    def _inject_key(self, agent: str):
        """Set env var for agent from vault before launch."""
        env_var = AGENT_ENV_VAR_MAP.get(agent)
        if not env_var:
            return
        service = AGENT_SERVICE_MAP.get(agent)
        if not service:
            return
        key = vault.get(service)
        if key and key != os.environ.get(env_var):
            os.environ[env_var] = key
            masked = key[:8] + "..." if len(key) > 8 else "****"
            logger.info(f"[LAUNCHER] Injected {env_var}={masked} for {agent}")

    def _check_rate_limit(self, line: bytes) -> str | None:
        """Check if line contains a rate limit indicator. Returns service name or None."""
        for pattern in RATE_LIMIT_PATTERNS:
            if re.search(pattern, line):
                for agent_name, service in AGENT_SERVICE_MAP.items():
                    if service:
                        srv_bytes = service.encode("utf-8")
                        if srv_bytes in line.lower():
                            return service
                # If no specific service found, return first likely match
                return "openai"
        return None

    def _rotate_key(self, agent: str) -> bool:
        """Rotate API key for agent's service. Returns True if rotation succeeded."""
        service = AGENT_SERVICE_MAP.get(agent)
        if not service:
            return False
        retries = self._key_retries.get(agent, 0)
        if retries >= self.max_key_retries:
            logger.warning(f"[LAUNCHER] Max key retries ({self.max_key_retries}) reached for {agent}")
            return False
        new_key = vault.rotate(service)
        if not new_key:
            logger.warning(f"[LAUNCHER] No keys left to rotate for {agent} ({service})")
            return False
        self._key_retries[agent] = retries + 1
        env_var = AGENT_ENV_VAR_MAP.get(agent)
        if env_var:
            os.environ[env_var] = new_key
            masked = new_key[:8] + "..." if len(new_key) > 8 else "****"
            logger.info(f"[LAUNCHER] Rotated {env_var}={masked} for {agent} (retry #{retries + 1})")
        return True

    def is_available(self, agent: str) -> bool:
        if agent == "shell":
            return True
        entry = AGENT_COMMANDS.get(agent)
        if not entry:
            return False
        cmd_name = entry[0]
        return shutil.which(cmd_name) is not None

    def build_command(self, agent: str, task: str) -> list[str]:
        template = AGENT_COMMANDS.get(agent)
        if not template:
            raise ValueError(f"Unknown agent: {agent}")
        cmd = []
        for part in template:
            expanded = part.replace("{task}", task).replace("{workspace}", str(self.workspace))
            cmd.append(expanded)
        if agent == "shell":
            if sys.platform == "win32":
                cmd = ["cmd", "/c"] + cmd
            else:
                cmd = ["sh", "-c"] + cmd
        return cmd

    async def launch(
        self,
        agent: str,
        task: str,
        timeout: int = 300,
        progress_callback: Callable | None = None,
    ) -> AgentResult:
        if not self.is_available(agent) and agent != "shell":
            return AgentResult(agent=agent, exit_code=-1, stdout="", stderr=f"{agent} not installed",
                               duration=0, task=task)

        # Inject API key from vault before each attempt
        self._inject_key(agent)

        rate_limited = False

        async def read_stream(stream, lines_list, is_stderr=False):
            nonlocal rate_limited
            while True:
                line = await stream.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace").rstrip()
                lines_list.append(decoded)
                if progress_callback:
                    await progress_callback(agent, decoded, is_stderr)
                if is_stderr:
                    detected = self._check_rate_limit(line)
                    if detected:
                        rate_limited = True
                        logger.warning(f"[LAUNCHER] Rate limit detected for {agent} ({detected}): {decoded[:80]}")
                if not is_stderr and self.auto_approve:
                    await self._check_auto_approve(proc, line)

        # Retry loop for rate limits (max max_key_retries attempts)
        attempt = 0
        while attempt <= self.max_key_retries:
            attempt += 1
            rate_limited = False
            cmd = self.build_command(agent, task)
            logger.info(f"[LAUNCHER] Starting {agent} in {self.workspace} (attempt {attempt}): {cmd}")

            start = datetime.now()
            session_id = f"{agent}_{int(start.timestamp())}_{attempt}"
            try:
                if agent == "shell":
                    shell_args = cmd[2:] if len(cmd) >= 3 and cmd[0] == "cmd" and cmd[1] == "/c" else cmd
                    cmd_str = shell_args[0] if len(shell_args) == 1 else " ".join(
                        f'"{a}"' if " " in a else a for a in shell_args
                    )
                    proc = await asyncio.create_subprocess_shell(
                        cmd_str,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        stdin=asyncio.subprocess.PIPE,
                        cwd=str(self.workspace.parent),
                    )
                else:
                    proc = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        stdin=asyncio.subprocess.PIPE,
                        cwd=str(self.workspace),
                    )
            except FileNotFoundError:
                return AgentResult(agent=agent, exit_code=-1, stdout="", stderr=f"Command not found: {cmd[0]}",
                                   duration=0, task=task)

            session = AgentSession(agent=agent, task=task, workspace=str(self.workspace),
                                    process=proc, start_time=start.timestamp())
            self.active_sessions[session_id] = session

            stdout_lines = []
            stderr_lines = []

            try:
                await asyncio.wait_for(
                    asyncio.gather(
                        read_stream(proc.stdout, stdout_lines),
                        read_stream(proc.stderr, stderr_lines, is_stderr=True),
                        return_exceptions=True,
                    ),
                    timeout=timeout,
                )
            except TimeoutError:
                proc.kill()
                duration = (datetime.now() - start).total_seconds()
                del self.active_sessions[session_id]
                return AgentResult(agent=agent, exit_code=-1, stdout="\n".join(stdout_lines),
                                   stderr="\n".join(stderr_lines) + "\n[TIMEOUT]",
                                   duration=duration, timed_out=True, task=task)

            await proc.wait()
            duration = (datetime.now() - start).total_seconds()
            del self.active_sessions[session_id]

            if rate_limited:
                logger.info(f"[LAUNCHER] Rate limited on attempt {attempt} — rotating key and retrying")
                if not self._rotate_key(agent):
                    logger.warning(f"[LAUNCHER] Key rotation failed for {agent} — giving up")
                    return AgentResult(agent=agent, exit_code=proc.returncode or -1,
                                       stdout="\n".join(stdout_lines),
                                       stderr="\n".join(stderr_lines) + "\n[RATE_LIMITED: no keys left]",
                                       duration=duration, task=task)
                continue  # Retry with new key

            return AgentResult(agent=agent, exit_code=proc.returncode or 0,
                               stdout="\n".join(stdout_lines),
                               stderr="\n".join(stderr_lines),
                               duration=duration, task=task)

        # Exhausted retries
        return AgentResult(agent=agent, exit_code=-1, stdout="", stderr=f"Exhausted {self.max_key_retries} retries due to rate limits",
                           duration=0, task=task)

    async def _check_auto_approve(self, proc: asyncio.subprocess.Process, line: bytes):
        for pattern in AUTO_APPROVE_PATTERNS:
            if re.search(pattern, line):
                self._approval_count += 1
                logger.info(f"[LAUNCHER] Auto-approve #{self._approval_count}")
                if proc.stdin and not proc.stdin.is_closing():
                    try:
                        proc.stdin.write(b"y\n")
                        await proc.stdin.drain()
                    except Exception as e:
                        logger.exception("[LAUNCHER] Auto-approve stdin write failed: %s", e)
                return
        for pattern in INTERACTIVE_PATTERNS:
            if re.search(pattern, line):
                logger.warning("[LAUNCHER] Agent asked for sensitive input — skipping")
                if proc.stdin and not proc.stdin.is_closing():
                    try:
                        proc.stdin.write(b"\n")
                        await proc.stdin.drain()
                    except Exception as e:
                        logger.exception("[LAUNCHER] Interactive stdin write failed: %s", e)
                return

    def cancel_all(self):
        for sid, session in self.active_sessions.items():
            try:
                session.process.kill()
            except Exception as e:
                logger.exception("[LAUNCHER] Kill failed for session %s: %s", sid, e)
        self.active_sessions.clear()

    def get_approval_count(self) -> int:
        return self._approval_count
