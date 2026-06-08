"""core/skill_loader.py
Loads all SKILL.md files from skills/ at startup.
Matches user messages against trigger phrases.
Routes matched messages to the corresponding handler without hitting Ollama.
"""
from __future__ import annotations

import ast
import importlib
import logging
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"

_skills: list[dict] | None = None


def _parse_skill_header(path: Path) -> dict | None:
    """Parse YAML-like header block from a SKILL.md file.
    Handles both inline lists [a, b, c] and YAML block lists:
      key:
        - item1
        - item2
    """
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    end = text.find("---", 3)
    if end == -1:
        return None
    block = text[3:end].strip()
    meta = {}
    current_key: str | None = None
    current_list: list[str] = []

    def _flush():
        nonlocal current_key, current_list
        if current_key and current_list:
            meta[current_key] = current_list
        current_key = None
        current_list = []

    def _set_val(key: str, val):
        if isinstance(val, str) and val.startswith("[") and val.endswith("]"):
            try:
                val = ast.literal_eval(val)
            except Exception as _e:
                logger.debug("skill_loader parse header failed: %s", _e)
                val = [v.strip().strip('"').strip("'") for v in val.strip("[]").split(",")]
        meta[key] = val

    for line in block.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("- "):
            if current_key:
                item = stripped[2:].strip().strip('"').strip("'")
                current_list.append(item)
            continue
        if ":" not in line:
            continue
        _flush()
        key, _, val = line.partition(":")
        current_key = key.strip()
        val = val.strip()
        if val:
            _set_val(current_key, val)
            current_key = None
    _flush()
    return meta


def _load_skills() -> list[dict]:
    """Scan skills/*.md, parse headers, import handlers."""
    global _skills
    if _skills is not None:
        return _skills
    _skills = []
    if not SKILLS_DIR.exists():
        return _skills
    for md_file in sorted(SKILLS_DIR.glob("*.md")):
        meta = _parse_skill_header(md_file)
        if not meta or not meta.get("name"):
            continue
        name = meta["name"]
        triggers = meta.get("triggers", [])
        py_file = SKILLS_DIR / f"{name}.py"
        if not py_file.exists():
            logger.warning("[SKILL] %s.md has no handler %s.py", name, name)
            continue
        try:
            mod = importlib.import_module(f"skills.{name}")
            handler: Callable | None = getattr(mod, "handle", None)
            if handler is None:
                logger.warning("[SKILL] %s.py has no async handle() function", name)
                continue
            _skills.append({
                "name": name,
                "description": meta.get("description", ""),
                "triggers": triggers,
                "handler": handler,
                "examples": meta.get("examples", []),
            })
            logger.info("[SKILL] Loaded: %s — %s", name, meta.get("description", ""))
        except Exception as e:
            logger.warning("[SKILL] Failed to load %s: %s", name, e)
    logger.info("[SKILL] %d skill(s) loaded", len(_skills))
    return _skills


def match_skill(message: str) -> Callable | None:
    """
    Match message against all skill triggers.
    Returns handler function or None.
    """
    text = (message or "").lower().strip()
    for skill in _load_skills():
        for trigger in skill["triggers"]:
            if trigger.lower() in text:
                logger.debug("[SKILL] '%s' matched trigger '%s' → %s", text[:40], trigger, skill["name"])
                return skill["handler"]
    return None


async def run_skill(handler: Callable, message: str) -> str:
    """Execute skill handler with message, return response string."""
    try:
        result = handler(message)
        if hasattr(result, "__await__"):
            result = await result
        return str(result)
    except Exception as e:
        logger.warning("[SKILL] Handler error: %s", e)
        return f"Skill error: {e}"
