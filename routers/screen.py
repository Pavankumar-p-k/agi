"""
routers/screen.py
-----------------
Screen understanding API for the Electron dot's Win+J feature.

Endpoints:
  POST /api/screen/understand   - analyze a screenshot, return plain-English summary
  POST /api/screen/ask          - ask a question about the current screen context
  GET  /api/screen/status       - is vision model available?

Add to core/main.py:
  from routers.screen import router as screen_router
  app.include_router(screen_router)
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/screen", tags=["screen"])

# ─────────────────────────────────────────────
# Vision model helper
# ─────────────────────────────────────────────

async def _vision_model() -> str | None:
    """Get the configured vision model, or None if not set up."""
    try:
        from core.settings import get_settings_store
        store = get_settings_store()
        model = store.get("vision_model") or store.get("llm.vision_model")
        if model:
            return model
    except Exception as e:
        logger.warning("[routers.screen] capture_screen failed: %s", e)

    # Fallback: check which vision model is installed (best first)
    try:
        import httpx, os
        base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{base}/api/tags")
            models = [m["name"] for m in r.json().get("models", [])]
            for candidate in ["moondream:latest", "moondream", "llava:7b", "llava"]:
                if any(candidate in m for m in models):
                    return candidate
    except Exception as e:
        logger.warning("[routers.screen] process_screen failed: %s", e)

    return None


async def _ask_vision(image_b64: str, prompt: str) -> str:
    """Send image + prompt to vision model via Ollama."""
    import httpx, os
    base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    model = await _vision_model()
    if not model:
        return "No vision model installed. Go to Settings → Models and install LLaVA."

    payload = {
        "model": model,
        "prompt": prompt,
        "images": [image_b64],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 512, "num_gpu": 99},
    }

    try:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(f"{base}/api/generate", json=payload)
            data = r.json()
            return data.get("response", "").strip()
    except Exception as e:
        logger.exception("Vision model call failed")
        return f"Vision model error: {e}"


# ─────────────────────────────────────────────
# Prompts
# ─────────────────────────────────────────────

UNDERSTAND_PROMPT = """You are JARVIS, an AI assistant looking at the user's screen.

Analyze what is visible and respond in 2-3 SHORT sentences:
1. What the user is currently looking at / doing
2. One immediately useful insight or suggestion (only if genuinely helpful)

Be CONCISE. No bullet points. No markdown. Plain English only.
If you see an error, explain it simply and suggest the fix.
If you see code, identify what it does and any obvious issues.
If you see a document or browser, summarize what's on screen."""

ASK_PROMPT = """You are JARVIS. The user is looking at their screen (screenshot provided) and has a question.

Answer their question based on what you see on screen.
Be concise and direct. 2-3 sentences max unless more detail is needed.
No markdown, no bullet points. Plain English."""


# ─────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────

class UnderstandRequest(BaseModel):
    screenshot_b64: str          # base64 encoded PNG/JPEG
    context: str | None = None   # optional: what the user typed after pressing Win+J


class AskRequest(BaseModel):
    screenshot_b64: str
    question: str


# ─────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────

@router.get("/status")
async def screen_status():
    """Check if screen understanding is available."""
    model = await _vision_model()
    return {
        "ok": True,
        "available": model is not None,
        "model": model,
        "message": (
            f"Screen understanding active ({model})"
            if model
            else "No vision model. Install LLaVA in Settings → Models."
        ),
    }


@router.post("/understand")
async def understand_screen(req: UnderstandRequest):
    """
    Main endpoint — called when user presses Win+J.
    Takes screenshot, returns plain-English summary in <2s on GPU.
    """
    # Strip data URI prefix if present
    img = req.screenshot_b64
    if "," in img:
        img = img.split(",", 1)[1]

    if req.context:
        # User typed something after pressing Win+J — use it as context
        prompt = f"{ASK_PROMPT}\n\nUser's question: {req.context}"
    else:
        prompt = UNDERSTAND_PROMPT

    answer = await _ask_vision(img, prompt)

    return {
        "ok": True,
        "answer": answer,
        "model": await _vision_model(),
    }


@router.post("/ask")
async def ask_about_screen(req: AskRequest):
    """Ask a specific question about what's on screen."""
    img = req.screenshot_b64
    if "," in img:
        img = img.split(",", 1)[1]

    prompt = f"{ASK_PROMPT}\n\nUser's question: {req.question}"
    answer = await _ask_vision(img, prompt)

    return {
        "ok": True,
        "answer": answer,
        "question": req.question,
    }
