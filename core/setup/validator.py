"""Post-setup validation — verify everything works together."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

from core.setup.report import ComponentStatus, ValidationResult

logger = logging.getLogger(__name__)

OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
SERVER_BASE = os.getenv("JARVIS_SERVER", "http://127.0.0.1:8000")


def validate_server() -> ValidationResult:
    for path in ["/health", "/api/system/status", "/"]:
        try:
            with urllib.request.urlopen(f"{SERVER_BASE}{path}", timeout=3) as resp:
                if resp.status < 500:
                    return ValidationResult("Server", ComponentStatus.OK, f"responding at {SERVER_BASE}")
        except (urllib.error.URLError, OSError):
            continue
    return ValidationResult("Server", ComponentStatus.ERROR,
                            f"not reachable at {SERVER_BASE}")


def validate_ollama() -> ValidationResult:
    try:
        with urllib.request.urlopen(f"{OLLAMA_BASE}/api/tags", timeout=3) as resp:
            if resp.status == 200:
                return ValidationResult("Ollama", ComponentStatus.OK, "running")
        return ValidationResult("Ollama", ComponentStatus.ERROR, "not responding")
    except (urllib.error.URLError, OSError):
        return ValidationResult("Ollama", ComponentStatus.ERROR, "not reachable")


def validate_planner() -> ValidationResult:
    try:
        with urllib.request.urlopen(f"{SERVER_BASE}/api/plans", timeout=3) as resp:
            if resp.status < 500:
                return ValidationResult("Planner", ComponentStatus.OK, "available")
        return ValidationResult("Planner", ComponentStatus.ERROR, "unavailable")
    except (urllib.error.URLError, OSError):
        return ValidationResult("Planner", ComponentStatus.SKIPPED, "server not running")


def validate_capabilities() -> ValidationResult:
    try:
        with urllib.request.urlopen(f"{SERVER_BASE}/api/features", timeout=3) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode())
                count = len(data) if isinstance(data, list) else 0
                return ValidationResult("Capabilities", ComponentStatus.OK, f"{count} registered")
        return ValidationResult("Capabilities", ComponentStatus.ERROR, "unavailable")
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return ValidationResult("Capabilities", ComponentStatus.SKIPPED, "server not running")


def validate_learning() -> ValidationResult:
    try:
        with urllib.request.urlopen(f"{SERVER_BASE}/api/knowledge/statistics", timeout=3) as resp:
            if resp.status == 200:
                return ValidationResult("Learning", ComponentStatus.OK, "knowledge store available")
        return ValidationResult("Learning", ComponentStatus.ERROR, "unavailable")
    except (urllib.error.URLError, OSError):
        return ValidationResult("Learning", ComponentStatus.SKIPPED, "server not running")


def validate_memory() -> ValidationResult:
    try:
        with urllib.request.urlopen(f"{SERVER_BASE}/api/memory/stats", timeout=3) as resp:
            if resp.status == 200:
                return ValidationResult("Memory", ComponentStatus.OK, "available")
        return ValidationResult("Memory", ComponentStatus.ERROR, "unavailable")
    except (urllib.error.URLError, OSError):
        return ValidationResult("Memory", ComponentStatus.SKIPPED, "server not running")


def validate_all() -> list[ValidationResult]:
    return [
        validate_server(),
        validate_ollama(),
        validate_planner(),
        validate_capabilities(),
        validate_learning(),
        validate_memory(),
    ]
