"""cli_helpers.py — Utility helpers for the JARVIS CLI."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from cli_state import ROOT

logger = logging.getLogger(__name__)


def build_cli_context(prompt: str) -> dict:
    cwd = Path.cwd().resolve()
    context = {
        "platform": "cli",
        "cwd": str(cwd),
        "workspace_root": str(cwd),
        "approved": True,
        "local_only": __import__('os').getenv("JARVIS_LOCAL_ONLY", "1").lower() not in {"0", "false", "no"},
    }
    lowered = prompt.lower()
    if any(
        token in lowered
        for token in ("project", "repo", "repository", "codebase", "review", "architecture", "develop", "build", "implement", "fix", "debug")
    ):
        context["workspace_summary"] = workspace_snapshot(cwd)
    return context


def is_agentic_prompt(prompt: str) -> bool:
    lowered = prompt.lower()
    triggers = (
        "open ", "launch ", "review ", "analyze ", "understand ", "inspect ",
        "build ", "develop ", "implement ", "create ", "fix ", "debug ",
        "plan ", "search ", "send ", "vision ", "look at ", "read ", "list ",
    )
    return any(token in lowered for token in triggers)


def print_plan_preview(result: dict):
    plan = result.get("plan", {})
    analysis = result.get("analysis", {})
    steps = plan.get("steps", [])
    if not steps:
        return
    print("Plan:")
    intent = analysis.get("intent")
    if intent:
        print(f"  intent: {intent}")
    for index, step in enumerate(steps, start=1):
        print(f"  {index}. [{step.get('tool', 'unknown')}] {step.get('action', '')}")


def workspace_snapshot(root: Path) -> str:
    manifest_names = ["pyproject.toml", "requirements.txt", "package.json", "pubspec.yaml", "README.md", "setup.py"]
    manifests = [name for name in manifest_names if (root / name).exists()]
    top_entries = []
    try:
        entries = sorted(root.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
        for entry in entries[:12]:
            top_entries.append(entry.name + ("/" if entry.is_dir() else ""))
    except Exception as err:
        logging.getLogger(__name__).error("workspace_snapshot error: %s", err, exc_info=True)
        raise
    readme_excerpt = ""
    readme = root / "README.md"
    if readme.exists():
        try:
            readme_excerpt = readme.read_text(encoding="utf-8", errors="replace")[:400].replace("\n", " ").strip()
        except Exception as e:
            logger.warning("[cli_helpers] readme read failed: %s", e)
            readme_excerpt = ""
    return (
        f"Workspace root: {root}. "
        f"Top-level entries: {', '.join(top_entries) or 'none'}. "
        f"Manifests: {', '.join(manifests) or 'none'}. "
        f"README: {readme_excerpt or 'not available'}"
    )
