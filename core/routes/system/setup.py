"""FastAPI routes wrapping SetupEngine for the web setup wizard.

All setup logic lives in core/setup/ — these routes are a thin
HTTP bridge.  The welcome page calls GET /api/setup/status on
mount and renders whatever the engine returns.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Setup Wizard"])


# ── Request models ──────────────────────────────────────

class InstallRequest(BaseModel):
    component: str  # "playwright" | "model:<model_id>"


# ── Helpers ─────────────────────────────────────────────

def _engine():
    from core.setup.engine import SetupEngine
    return SetupEngine()


# ── Endpoints ───────────────────────────────────────────

@router.get("/api/setup/status")
async def get_setup_status() -> dict[str, Any]:
    """Return the full setup status snapshot from SetupEngine.

    Includes phase, hardware, installed models, per-component
    check results, and the recommended model.
    """
    try:
        return _engine().status()
    except Exception as e:
        logger.warning("Setup status failed: %s", e)
        return {"phase": "error", "error": str(e)}


@router.post("/api/setup/install")
async def install_component(body: InstallRequest) -> dict[str, Any]:
    """Install a specific component (playwright or model).

    Body:
      {"component": "playwright"}         → install Playwright
      {"component": "model:llama3.2:3b"}  → pull an Ollama model
    """
    engine = _engine()
    comp = body.component

    if comp == "playwright":
        result = engine.install_playwright()
    elif comp.startswith("model:"):
        model_id = comp[len("model:"):]
        result = engine.pull_model(model_id)
    else:
        return {"success": False, "error": f"Unknown component: {comp}"}

    return {
        "success": result.success,
        "component": comp,
        "detail": result.detail,
    }


@router.post("/api/setup/demo")
async def run_demo() -> dict[str, Any]:
    """Run the 20-second hello.html demo."""
    engine = _engine()
    result = engine.run_demo()
    return {
        "success": result.success,
        "duration_ms": result.duration_ms,
        "artifact_path": result.artifact_path,
        "detail": result.detail,
    }


@router.post("/api/setup/complete")
async def complete_setup() -> dict[str, Any]:
    """Mark setup as complete (phase → COMPLETE)."""
    engine = _engine()
    engine.complete()
    return {"success": True, "phase": engine.state.phase.value}
