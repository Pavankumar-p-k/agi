"""Write JARVIS configuration files."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from core.setup.report import InstallResult, SetupPhase, SetupState

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
JARVIS_CONFIG_DIR = Path.home() / ".jarvis"
DATA_DIR = JARVIS_CONFIG_DIR / "data"
SETTINGS_PATH = DATA_DIR / "settings.json"
SETUP_MARKER = DATA_DIR / ".setup_complete"
CLI_CONFIG_PATH = JARVIS_CONFIG_DIR / "config.json"


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    JARVIS_CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_settings() -> dict[str, Any]:
    if SETTINGS_PATH.exists():
        try:
            return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_settings(settings: dict[str, Any]) -> bool:
    try:
        ensure_dirs()
        current = load_settings()
        current.update(settings)
        SETTINGS_PATH.write_text(
            json.dumps(current, indent=2, default=str),
            encoding="utf-8",
        )
        return True
    except OSError as e:
        logger.warning("Failed to save settings: %s", e)
        return False


def set_default_model(model_id: str) -> InstallResult:
    ok = save_settings({
        "model": {"primary": model_id, "default": model_id},
        "llm": {"default_model": model_id},
    })
    return InstallResult(
        "Default model",
        ok,
        f"set to {model_id}" if ok else "failed to write settings",
    )


def set_ollama_url(url: str) -> InstallResult:
    ok = save_settings({"ollama": {"url": url}})
    return InstallResult("Ollama URL", ok, url if ok else "failed")


def configure_api_keys(keys: dict[str, str]) -> InstallResult:
    count = len(keys)
    settings = load_settings()
    existing = settings.get("api_keys", {})
    existing.update(keys)
    ok = save_settings({"api_keys": existing})
    return InstallResult(
        "API Keys",
        ok,
        f"{count} key(s) configured" if ok else "failed to save",
    )


def _state_to_dict(state: SetupState) -> dict[str, Any]:
    return {
        "phase": state.phase.value,
        "has_been_run": state.has_been_run,
        "installed_models": state.installed_models,
        "configured_ollama": state.configured_ollama,
        "configured_playwright": state.configured_playwright,
        "demo_ran": state.demo_ran,
        "updated_at": __import__("datetime").datetime.now().isoformat(),
    }


def save_setup_state(state: SetupState) -> None:
    ensure_dirs()
    try:
        SETUP_MARKER.write_text(
            json.dumps(_state_to_dict(state), indent=2),
            encoding="utf-8",
        )
    except OSError as e:
        logger.warning("Failed to save setup state: %s", e)


def mark_setup_complete(state: SetupState) -> None:
    state.phase = SetupPhase.COMPLETE
    state.has_been_run = True
    save_setup_state(state)


def mark_setup_in_progress(state: SetupState) -> None:
    state.phase = SetupPhase.IN_PROGRESS
    state.has_been_run = True
    save_setup_state(state)


def mark_setup_failed(state: SetupState) -> None:
    state.phase = SetupPhase.FAILED
    save_setup_state(state)


def load_setup_state() -> SetupState:
    if not SETUP_MARKER.exists():
        return SetupState()
    try:
        data = json.loads(SETUP_MARKER.read_text(encoding="utf-8"))

        # backward compat: old files had "completed": true
        if "completed" in data and "phase" not in data:
            phase = SetupPhase.COMPLETE if data["completed"] else SetupPhase.NOT_STARTED
        else:
            phase = SetupPhase(data.get("phase", "not_started"))

        return SetupState(
            phase=phase,
            has_been_run=data.get("has_been_run", phase != SetupPhase.NOT_STARTED),
            installed_models=data.get("installed_models", []),
            configured_ollama=data.get("configured_ollama", False),
            configured_playwright=data.get("configured_playwright", False),
            demo_ran=data.get("demo_ran", False),
        )
    except (json.JSONDecodeError, OSError, ValueError):
        return SetupState()
