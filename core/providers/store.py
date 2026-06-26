from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

from core.providers.registry import provider_registry

logger = logging.getLogger(__name__)

_PROVIDERS_DIR = Path.home() / ".jarvis" / "providers"
_MANIFESTS_DIR = _PROVIDERS_DIR / "manifests"
_ADAPTERS_DIR = _PROVIDERS_DIR / "adapters"

_KNOWN_PROVIDERS: dict[str, dict[str, Any]] = {
    "claude-code": {
        "provider_id": "claude_code",
        "name": "Claude Code",
        "version": "1.0.0",
        "capabilities": [
            {"name": "coding", "confidence": 0.97, "languages": ["python", "javascript", "typescript", "rust", "go", "java"]},
            {"name": "debugging", "confidence": 0.94},
            {"name": "refactoring", "confidence": 0.93},
            {"name": "testing", "confidence": 0.90},
        ],
        "health_command": "claude --version",
        "priority": 50,
        "permissions": ["filesystem", "git", "network"],
        "cost_model": "api",
        "install_hint": "npm install -g @anthropic/claude-code",
    },
    "codex": {
        "provider_id": "codex",
        "name": "Codex CLI",
        "version": "1.0.0",
        "capabilities": [
            {"name": "coding", "confidence": 0.88, "languages": ["python", "javascript", "typescript", "java", "kotlin"]},
            {"name": "codegen", "confidence": 0.91},
            {"name": "scaffold", "confidence": 0.90},
        ],
        "health_command": "codex --version",
        "priority": 60,
        "permissions": ["filesystem", "network"],
        "cost_model": "api",
        "install_hint": "npm install -g @openai/codex",
    },
    "jules": {
        "provider_id": "jules",
        "name": "Jules CLI",
        "version": "1.0.0",
        "capabilities": [
            {"name": "coding", "confidence": 0.85, "languages": ["python", "javascript", "typescript", "java"]},
            {"name": "refactoring", "confidence": 0.87},
            {"name": "research", "confidence": 0.82},
        ],
        "health_command": "jules --version",
        "priority": 70,
        "permissions": ["filesystem", "git", "network"],
        "cost_model": "api",
        "install_hint": "pip install jules-cli",
    },
    "aider": {
        "provider_id": "aider",
        "name": "Aider",
        "version": "1.0.0",
        "capabilities": [
            {"name": "coding", "confidence": 0.83, "languages": ["python", "javascript", "typescript", "go", "rust"]},
            {"name": "refactoring", "confidence": 0.86},
            {"name": "debugging", "confidence": 0.85},
        ],
        "health_command": "aider --version",
        "priority": 75,
        "permissions": ["filesystem", "git", "network"],
        "cost_model": "api",
        "install_hint": "pip install aider-chat",
    },
    "gemini-cli": {
        "provider_id": "gemini_cli",
        "name": "Gemini CLI",
        "version": "1.0.0",
        "capabilities": [
            {"name": "coding", "confidence": 0.80, "languages": ["python", "javascript", "typescript"]},
            {"name": "research", "confidence": 0.88},
            {"name": "explain", "confidence": 0.90},
        ],
        "health_command": "gemini --version",
        "priority": 80,
        "permissions": ["filesystem", "network"],
        "cost_model": "api",
        "install_hint": "npm install -g @google/gemini-cli",
    },
    "playwright": {
        "provider_id": "playwright",
        "name": "Playwright",
        "version": "1.0.0",
        "capabilities": [
            {"name": "browser", "confidence": 0.95, "languages": ["python", "javascript", "typescript"]},
            {"name": "testing", "confidence": 0.92},
        ],
        "health_command": "playwright --version",
        "priority": 50,
        "permissions": ["network", "filesystem"],
        "cost_model": "free",
        "install_hint": "pip install playwright && playwright install",
    },
    "docker": {
        "provider_id": "docker",
        "name": "Docker",
        "version": "1.0.0",
        "capabilities": [
            {"name": "deployment", "confidence": 0.95},
            {"name": "automation", "confidence": 0.90},
        ],
        "health_command": "docker --version",
        "priority": 40,
        "permissions": ["system", "network"],
        "cost_model": "free",
        "install_hint": "See https://docs.docker.com/get-docker/",
    },
    "telegram": {
        "provider_id": "telegram",
        "name": "Telegram",
        "version": "1.0.0",
        "capabilities": [
            {"name": "messaging", "confidence": 0.95},
            {"name": "notifications", "confidence": 0.95},
        ],
        "health_command": "",
        "priority": 50,
        "permissions": ["network"],
        "cost_model": "free",
        "install_hint": "Set TELEGRAM_BOT_TOKEN in .env",
    },
    "vercel": {
        "provider_id": "vercel",
        "name": "Vercel",
        "version": "1.0.0",
        "capabilities": [
            {"name": "deployment", "confidence": 0.93},
        ],
        "health_command": "vercel --version",
        "priority": 50,
        "permissions": ["network"],
        "cost_model": "api",
        "install_hint": "npm install -g vercel && vercel login",
    },
    "supabase": {
        "provider_id": "supabase",
        "name": "Supabase",
        "version": "1.0.0",
        "capabilities": [
            {"name": "database", "confidence": 0.94},
            {"name": "storage", "confidence": 0.90},
        ],
        "health_command": "supabase --version",
        "priority": 50,
        "permissions": ["network"],
        "cost_model": "api",
        "install_hint": "npm install -g supabase && supabase login",
    },
}


def list_known_providers() -> dict[str, dict[str, Any]]:
    return dict(_KNOWN_PROVIDERS)


def get_known_provider(provider_id: str) -> dict[str, Any] | None:
    return _KNOWN_PROVIDERS.get(provider_id)


def generate_manifest(provider_id: str) -> dict[str, Any] | None:
    info = _KNOWN_PROVIDERS.get(provider_id)
    if not info:
        return None
    return {
        "provider_id": info["provider_id"],
        "name": info["name"],
        "version": info["version"],
        "priority": info["priority"],
        "capabilities": info["capabilities"],
        "health_command": info["health_command"],
        "permissions": info["permissions"],
        "cost_model": info["cost_model"],
    }


def write_manifest(provider_id: str) -> bool:
    manifest = generate_manifest(provider_id)
    if not manifest:
        logger.warning("[ProviderStore] Unknown provider: %s", provider_id)
        return False
    _MANIFESTS_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = _MANIFESTS_DIR / f"{provider_id}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    logger.info("[ProviderStore] Wrote manifest for %s to %s", provider_id, manifest_path)
    return True


def is_installed(provider_id: str) -> bool:
    manifest_path = _MANIFESTS_DIR / f"{provider_id}.json"
    if manifest_path.exists():
        return True
    pid_lookup = info.get("provider_id", "") if (info := _KNOWN_PROVIDERS.get(provider_id)) else provider_id
    from core.providers.registry import provider_registry
    return provider_registry.get(pid_lookup) is not None


def health_command_exists(provider_id: str) -> bool:
    info = _KNOWN_PROVIDERS.get(provider_id)
    if not info:
        return False
    cmd = info.get("health_command", "").split()[0] if info.get("health_command") else ""
    if not cmd:
        return False
    return shutil.which(cmd) is not None
