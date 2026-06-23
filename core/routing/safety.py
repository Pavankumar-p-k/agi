from __future__ import annotations
from enum import Enum


class SafetyLevel(Enum):
    SAFE = "safe"
    CONFIRM = "confirm"
    DANGEROUS = "dangerous"


# ── Dangerous patterns (require explicit override) ──
_DANGEROUS_SHELL_PATTERNS = [
    "rm -rf /", "rm -rf ~", "rm -rf --no-preserve-root",
    "format ", "mkfs.", "dd if=",
    ":(){ :|:& };:", "fork bomb",
    "chmod -R 000", "chown -R ",
    "> /dev/sda", "> /dev/hda",
    "shutdown", "reboot", "poweroff",
    "kill -9 1", "kill -9 -1",
]

_DANGEROUS_FILE_PATTERNS = [
    ".ssh/", ".gnupg/", "/etc/", "/sys/", "/proc/",
    "authorized_keys", "id_rsa", "id_ed25519",
]

# ── Confirm patterns (require user approval) ──
_CONFIRM_SHELL_PATTERNS = [
    "git reset --hard", "git push --force", "git rm",
    "rm ", "rmdir ", "del /s", "del /f",
    "kill ", "taskkill",
    "docker rm", "docker rmi", "docker system prune",
    "pip uninstall", "poetry remove", "npm uninstall",
    "drop table", "drop database", "delete from",
]

_CONFIRM_FILE_PATTERNS = [
    "delete", "remove", "overwrite",
]

# ── Safe patterns (always auto-execute) ──
_SAFE_FILE_PATTERNS = [
    "read ", "list ", "show ", "find ", "search ",
]

_SAFE_SHELL_PATTERNS = [
    "ls", "dir", "pwd", "echo", "cat ", "type ",
    "git status", "git diff", "git log", "git branch",
    "pip list", "pip freeze",
    "npm list", "npm audit",
    "poetry show", "poetry check",
]


def classify_tool(tool: str, args: str) -> SafetyLevel:
    """Classify a tool+args combo into a safety level."""
    lowered_args = args.lower()

    # Check dangerous first
    for pattern in _DANGEROUS_SHELL_PATTERNS:
        if pattern in lowered_args:
            return SafetyLevel.DANGEROUS

    for pattern in _DANGEROUS_FILE_PATTERNS:
        if pattern in lowered_args:
            return SafetyLevel.DANGEROUS

    # Check confirm
    if tool in ("delete_file", "rm", "remove"):
        return SafetyLevel.CONFIRM

    for pattern in _CONFIRM_SHELL_PATTERNS:
        if pattern in lowered_args:
            return SafetyLevel.CONFIRM

    for pattern in _CONFIRM_FILE_PATTERNS:
        if pattern in lowered_args:
            return SafetyLevel.CONFIRM

    # Check safe
    if tool in ("read_file", "list_files", "search_code", "semantic_search"):
        return SafetyLevel.SAFE

    if tool in ("shell", "shell_command"):
        for pattern in _SAFE_SHELL_PATTERNS:
            if lowered_args.startswith(pattern) or lowered_args.startswith(pattern.lstrip()):
                return SafetyLevel.SAFE
        return SafetyLevel.CONFIRM

    for pattern in _SAFE_FILE_PATTERNS:
        if pattern in lowered_args:
            return SafetyLevel.SAFE

    # Default to confirm for anything uncertain
    return SafetyLevel.CONFIRM
