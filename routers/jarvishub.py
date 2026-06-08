"""JarvisHub — skill index API endpoint."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/api/jarvishub", tags=["jarvishub"])

SKILLS_LIBRARY = Path(__file__).resolve().parent.parent / "skills" / "library"
SKILLS_INSTALLED = Path(__file__).resolve().parent.parent / "skills" / "installed"


def _index_library() -> list[dict[str, Any]]:
    results = []
    if not SKILLS_LIBRARY.exists():
        return results
    for skill_json in SKILLS_LIBRARY.rglob("skill.json"):
        if "__pycache__" in str(skill_json):
            continue
        try:
            data = json.loads(skill_json.read_text(encoding="utf-8"))
            data["type"] = "library"
            data["source"] = str(skill_json.relative_to(SKILLS_LIBRARY.parent))
            path = skill_json.parent.name
            data["name"] = data.get("name", path)
            data["category"] = skill_json.parent.parent.name
            data.setdefault("loaded", False)
            data.setdefault("tool_count", 0)
            results.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    return results


def _index_installed() -> list[dict[str, Any]]:
    results = []
    if not SKILLS_INSTALLED.exists():
        return results
    try:
        from skills.manager import skill_manager
        skill_manager.load_all()
        for entry in skill_manager.list():
            entry["type"] = "installed"
            entry["loaded"] = True
            entry["tool_count"] = len(entry.get("tools", []))
            results.append(entry)
    except Exception:
        pass
    return results


@router.get("")
async def jarvishub_index() -> list[dict[str, Any]]:
    library = _index_library()
    installed = _index_installed()
    return library + installed
