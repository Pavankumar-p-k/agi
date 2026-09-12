"""Known-provider catalog and manifest utilities.

Completed from the committed contract in tests/unit/test_provider_ecosystem.py
(TestProviderStore).  A "known provider" is a connector JARVIS can recognize
and (when its CLI exists) register.  Manifests are the on-disk representation
written under ``_MANIFESTS_DIR``.
"""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any, Optional

from core.providers.registry import provider_registry

logger = logging.getLogger(__name__)

_MANIFESTS_DIR = Path.home() / ".jarvis" / "manifests"

KNOWN_PROVIDERS: dict[str, dict[str, Any]] = {
    "claude-code": {
        "provider_id": "claude_code",
        "name": "Claude Code",
        "version": "1.0.0",
        "capabilities": ["coding", "research", "review", "documentation"],
        "install_command": "npm install -g @anthropic-ai/claude-code",
        "health_command": "claude --version",
    },
    "codex": {
        "provider_id": "codex",
        "name": "Codex CLI",
        "version": "1.0.0",
        "capabilities": ["coding", "scaffold", "review", "testing"],
        "install_command": "npm install -g @openai/codex",
        "health_command": "codex --version",
    },
    "aider": {
        "provider_id": "aider",
        "name": "Aider",
        "version": "1.0.0",
        "capabilities": ["coding", "git"],
        "install_command": "pip install aider-chat",
        "health_command": "aider --version",
    },
    "cursor": {
        "provider_id": "cursor",
        "name": "Cursor",
        "version": "1.0.0",
        "capabilities": ["coding"],
        "install_command": "",
        "health_command": "cursor --version",
    },
    "gemini": {
        "provider_id": "gemini",
        "name": "Gemini CLI",
        "version": "1.0.0",
        "capabilities": ["coding", "research"],
        "install_command": "npm install -g @google/gemini-cli",
        "health_command": "gemini --version",
    },
    "opencode": {
        "provider_id": "opencode",
        "name": "OpenCode",
        "version": "1.0.0",
        "capabilities": ["coding"],
        "install_command": "npm install -g opencode",
        "health_command": "opencode --version",
    },
    "gh": {
        "provider_id": "github_cli",
        "name": "GitHub CLI",
        "version": "1.0.0",
        "capabilities": ["github", "version_control"],
        "install_command": "winget install GitHub.cli",
        "health_command": "gh --version",
    },
    "telegram": {
        "provider_id": "telegram",
        "name": "Telegram",
        "version": "1.0.0",
        "capabilities": ["messaging"],
        "install_command": "",
        "health_command": "",
    },
    "desktop": {
        "provider_id": "desktop",
        "name": "Desktop Controller",
        "version": "1.0.0",
        "capabilities": ["desktop"],
        "install_command": "",
        "health_command": "",
    },
    "email": {
        "provider_id": "email",
        "name": "Email",
        "version": "1.0.0",
        "capabilities": ["email", "send_email"],
        "install_command": "",
        "health_command": "",
    },
}


def list_known_providers() -> dict[str, dict[str, Any]]:
    return dict(KNOWN_PROVIDERS)


def get_known_provider(slug: str) -> Optional[dict[str, Any]]:
    info = KNOWN_PROVIDERS.get(slug)
    return dict(info) if info else None


def generate_manifest(slug: str) -> Optional[dict[str, Any]]:
    """Build a manifest dict for a known provider (None when unknown)."""
    info = KNOWN_PROVIDERS.get(slug)
    if info is None:
        return None
    return {
        "provider_id": info["provider_id"],
        "name": info["name"],
        "version": info["version"],
        "capabilities": list(info["capabilities"]),
        "slug": slug,
    }


def write_manifest(slug: str) -> bool:
    """Persist a manifest JSON for a known provider.  False when unknown."""
    manifest = generate_manifest(slug)
    if manifest is None:
        return False
    try:
        _MANIFESTS_DIR.mkdir(parents=True, exist_ok=True)
        (_MANIFESTS_DIR / f"{slug}.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8",
        )
        return True
    except Exception as exc:
        logger.debug("[provider_store] write manifest failed: %s", exc)
        return False


def health_command_exists(slug: str) -> bool:
    """True when the provider is known, declares a health_command, and that
    command's binary exists on PATH."""
    info = KNOWN_PROVIDERS.get(slug)
    if not info:
        return False
    command = str(info.get("health_command", "") or "").strip()
    if not command:
        return False
    binary = command.split()[0]
    return shutil.which(binary) is not None


def is_installed(slug: str) -> bool:
    """Installed = registered in the provider registry OR a manifest on disk."""
    try:
        info = KNOWN_PROVIDERS.get(slug, {})
        provider_id = info.get("provider_id", slug)
        if provider_registry.get(provider_id) is not None:
            return True
    except Exception:
        pass
    try:
        return (_MANIFESTS_DIR / f"{slug}.json").exists()
    except Exception:
        return False
