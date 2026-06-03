"""core/agent_registry.py
Defines all 6 CLI coding agents — capabilities, invocation,
auto-install, and API key configuration.
"""

import shutil
import subprocess
import asyncio
import os
import sys
import logging
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv

# Load .env so API key checks work
_env_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(_env_path)

logger = logging.getLogger("agent_registry")


@dataclass
class Agent:
    name: str
    cmd: Optional[str]
    label: str
    capabilities: list[str] = field(default_factory=list)
    install_cmd: str = ""
    env_vars: list[str] = field(default_factory=list)
    post_install_check: str = ""

    def is_available(self) -> bool:
        if self.cmd is None:
            return True
        return shutil.which(self.cmd.split()[0]) is not None

    def needs_api_key(self) -> bool:
        return any(os.getenv(v) is None or os.getenv(v) == "" for v in self.env_vars)

    def missing_api_keys(self) -> list[str]:
        return [v for v in self.env_vars if not os.getenv(v)]

    async def install(self) -> bool:
        if not self.install_cmd or self.is_available():
            return True
        logger.info(f"[AGENTS] Installing {self.label} via: {self.install_cmd}")
        try:
            import shlex
            install_args = shlex.split(self.install_cmd)
            proc = await asyncio.create_subprocess_exec(
                *install_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            if proc.returncode == 0:
                logger.info(f"[AGENTS] {self.label} installed successfully")
                return True
            else:
                logger.warning(f"[AGENTS] {self.label} install failed (exit {proc.returncode}): {stderr.decode()[:200]}")
                return False
        except asyncio.TimeoutError:
            logger.warning(f"[AGENTS] {self.label} install timed out")
            return False
        except Exception as e:
            logger.warning(f"[AGENTS] {self.label} install error: {e}")
            return False

    def config_instructions(self) -> str:
        missing = self.missing_api_keys()
        if not missing:
            logger.debug("[AGENTS] config_instructions: no missing keys for %s", self.name)
            return None
        if self.name == "codex":
            return f"Set OPENAI_API_KEY in .env (get from https://platform.openai.com/api-keys)"
        if self.name == "gemini":
            return f"Set GEMINI_API_KEY in .env (currently {'set' if os.getenv('GEMINI_API_KEY') else 'MISSING'})"
        if self.name == "copilot":
            return f"Set GITHUB_TOKEN in .env with 'read:user' + 'repo' scopes"
        if self.name == "aider":
            return f"Aider needs an API key. Set OPENAI_API_KEY or ANTHROPIC_API_KEY in .env"
        if self.name == "jules":
            return f"Set ANTHROPIC_API_KEY in .env for Jules CLI"
        return f"Configure {self.label}: missing {', '.join(missing)}"


AGENTS: dict[str, Agent] = {
    "codex": Agent(
        name="codex",
        cmd="codex",
        label="Codex CLI",
        capabilities=["generate", "scaffold", "new_file"],
        install_cmd="npm install -g @openai/codex",
        env_vars=["OPENAI_API_KEY"],
    ),
    "aider": Agent(
        name="aider",
        cmd="aider",
        label="Aider",
        capabilities=["modify", "refactor", "edit", "add_feature"],
        install_cmd="pip install aider-chat",
        env_vars=["OPENAI_API_KEY"],
    ),
    "opencode": Agent(
        name="opencode",
        cmd="opencode",
        label="OpenCode",
        capabilities=["multi_step", "plan", "refactor", "complex"],
        install_cmd="npm install -g @opencode/cli",
        env_vars=[],
    ),
    "gemini": Agent(
        name="gemini",
        cmd="gemini",
        label="Gemini CLI",
        capabilities=["research", "explain", "test", "analyze", "document"],
        install_cmd="npm install -g @google/gemini-cli",
        env_vars=["GEMINI_API_KEY"],
    ),
    "copilot": Agent(
        name="copilot",
        cmd="copilot",
        label="Copilot CLI",
        capabilities=["suggest", "explain", "inline", "quick_fix"],
        install_cmd="npm install -g @githubnext/copilot-cli",
        env_vars=["GITHUB_TOKEN"],
    ),
    "gh": Agent(
        name="gh",
        cmd="gh",
        label="GitHub CLI",
        capabilities=["repo_create", "repo_view", "pr", "clone"],
        install_cmd="",  # requires manual installer from https://cli.github.com/
        env_vars=["GITHUB_TOKEN"],
    ),
    "jules": Agent(
        name="jules",
        cmd="jules",
        label="Jules CLI",
        capabilities=["scaffold", "modify", "refactor", "research", "multi_step"],
        install_cmd="pip install jules-cli",
        env_vars=["ANTHROPIC_API_KEY"],
    ),
    "shell": Agent(
        name="shell",
        cmd=None,
        label="Shell",
        capabilities=["run", "test", "git", "install", "build", "deploy"],
        install_cmd="",
        env_vars=[],
    ),
}


def get_agent(name: str) -> Optional[Agent]:
    return AGENTS.get(name)


def get_agents_for_capability(capability: str) -> list[Agent]:
    return [a for a in AGENTS.values() if capability in a.capabilities]


def get_best_agent(task_type: str) -> str:
    mapping = {
        "generate": "codex",
        "scaffold": "codex",
        "new_file": "codex",
        "modify": "aider",
        "refactor": "aider",
        "edit": "aider",
        "add_feature": "aider",
        "multi_step": "opencode",
        "complex": "opencode",
        "research": "gemini",
        "explain": "gemini",
        "test": "gemini",
        "analyze": "gemini",
        "document": "gemini",
        "suggest": "copilot",
        "inline": "copilot",
        "quick_fix": "copilot",
        "repo_create": "gh",
        "repo_view": "gh",
        "clone": "gh",
        "run": "shell",
        "build": "shell",
        "install": "shell",
        "deploy": "shell",
    }
    return mapping.get(task_type, "shell")


def check_available_agents() -> list[str]:
    available = []
    for name, agent in AGENTS.items():
        if agent.is_available():
            available.append(name)
    return available


def check_missing_agents() -> list[str]:
    return [name for name, agent in AGENTS.items() if name != "shell" and not agent.is_available()]


def check_unconfigured_agents() -> list[str]:
    """Agents that are installed but missing required API keys."""
    return [name for name, agent in AGENTS.items() if agent.is_available() and agent.needs_api_key()]


def get_config_report() -> dict:
    report = {}
    for name, agent in AGENTS.items():
        if name == "shell":
            continue
        status = "available" if agent.is_available() else "missing"
        keys_ok = not agent.needs_api_key()
        missing_keys = agent.missing_api_keys()
        report[name] = {
            "label": agent.label,
            "status": status,
            "api_keys_configured": keys_ok,
            "missing_keys": missing_keys,
            "install_cmd": agent.install_cmd,
            "config_help": agent.config_instructions(),
        }
    return report


async def auto_install_missing() -> list[str]:
    installed = []
    for name in check_missing_agents():
        agent = AGENTS[name]
        if agent.install_cmd:
            success = await agent.install()
            if success:
                installed.append(name)
        else:
            logger.warning(f"[AGENTS] {agent.label} has no auto-install cmd — install manually")
    return installed


def write_env_file(missing_vars: list[str], env_path: Optional[str] = None) -> str:
    """Return instructions for the user on what to add to .env.

    If env_path is provided, append the instructions to that file and return the
    path written. Otherwise return the instruction string.
    """
    instructions = []
    for var in missing_vars:
        if var == "OPENAI_API_KEY":
            instructions.append(f"{var}=sk-...  # Get from https://platform.openai.com/api-keys")
        elif var == "GEMINI_API_KEY":
            instructions.append(f"{var}=...  # Get from https://aistudio.google.com/apikey")
        elif var == "GITHUB_TOKEN":
            instructions.append(f"{var}=ghp_...  # Get from https://github.com/settings/tokens")
        elif var == "ANTHROPIC_API_KEY":
            instructions.append(f"{var}=sk-ant-...  # Get from https://console.anthropic.com/")
    content = "\n".join(instructions)
    if env_path:
        try:
            with open(env_path, "a", encoding="utf-8") as f:
                f.write("\n" + content + "\n")
            return str(env_path)
        except Exception:
            logger.warning(f"[AGENTS] Failed to write env tips to {env_path}")
    return content
