"""api/website_routes.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
JARVIS Website Generator — REST API Routes
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Mount in main FastAPI app:

    from api.website_routes import router as website_router
    app.include_router(website_router)

Endpoints:
  POST /website/generate   → {job_id}  (background generation)
  GET  /website/status/{job_id}        → progress + result
  GET  /website/jobs                   → list all jobs
  POST /website/preview    → start preview for existing dir
  POST /website/stop       → kill preview server(s)
  GET  /website/styles     → list available style presets
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("website_routes")

router = APIRouter(prefix="/website", tags=["website-generator"])

# ─── In-memory job store ──────────────────────────────────────────────────────
# {job_id: {status, progress, result, error, created_at, topic, pages, style}}
_jobs: Dict[str, Dict] = {}


# ─── Request / Response models ────────────────────────────────────────────────
class GenerateRequest(BaseModel):
    topic:      str            = Field(...,  example="Coffee Shop")
    pages:      List[str]      = Field(default=["index","about","services","contact"])
    style:      str            = Field(default="modern",
                                       description="modern|corporate|creative|dark|elegant|tech|warm|minimal")
    output_dir: Optional[str]  = Field(default=None, description="Optional output path")


class PreviewRequest(BaseModel):
    directory: str = Field(..., description="Absolute path to generated site directory")


class StopRequest(BaseModel):
    port: Optional[int] = Field(default=None, description="Port to stop; omit to stop all")


# ─── Background worker ────────────────────────────────────────────────────────
async def _run_generation(job_id: str, topic: str, pages: List[str],
                           style: str, output_dir: Optional[str]) -> None:
    job = _jobs[job_id]
    job["status"]   = "running"
    job["progress"] = 5

    try:
        from tools.website_generator import generate_site_async  # type: ignore

        # Fake incremental progress updates while waiting
        async def _tick():
            ticks = [10, 20, 35, 55, 70, 85]
            for t in ticks:
                await asyncio.sleep(4)
                if job["status"] == "running":
                    job["progress"] = t

        tick_task = asyncio.create_task(_tick())

        result = await generate_site_async(
            topic      = topic,
            pages      = pages,
            output_dir = output_dir,
            style      = style,
        )
        tick_task.cancel()

        job["status"]     = "done"
        job["progress"]   = 100
        job["result"]     = result
        job["finished_at"] = datetime.utcnow().isoformat()
        logger.info("[website_routes] job %s done — %s", job_id, result.get("preview_url"))

    except Exception as exc:
        logger.exception("[website_routes] job %s failed: %s", job_id, exc)
        job["status"]   = "failed"
        job["progress"] = 0
        job["error"]    = str(exc)


# ─── Endpoints ────────────────────────────────────────────────────────────────
@router.post("/generate", summary="Start website generation job")
async def generate_website(req: GenerateRequest, background_tasks: BackgroundTasks):
    """
    Kick off async website generation.
    Returns immediately with a job_id — poll /website/status/{job_id}.
    """
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "job_id":     job_id,
        "status":     "queued",
        "progress":   0,
        "result":     None,
        "error":      None,
        "topic":      req.topic,
        "pages":      req.pages,
        "style":      req.style,
        "created_at": datetime.utcnow().isoformat(),
    }

    background_tasks.add_task(
        _run_generation, job_id, req.topic, req.pages, req.style, req.output_dir
    )

    return {
        "job_id":     job_id,
        "status":     "queued",
        "message":    f"Generation started for topic='{req.topic}'. Poll /website/status/{job_id}",
        "poll_url":   f"/website/status/{job_id}",
    }


@router.get("/status/{job_id}", summary="Poll generation job status")
async def job_status(job_id: str):
    """
    Returns:
      status:   queued | running | done | failed
      progress: 0-100
      result:   full result dict when done
      error:    error message when failed
    """
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return job


@router.get("/jobs", summary="List all website generation jobs")
async def list_jobs():
    """Return all jobs (most recent first)."""
    return {
        "jobs": sorted(
            [
                {k: v for k, v in j.items() if k != "result"}
                for j in _jobs.values()
            ],
            key=lambda x: x.get("created_at", ""),
            reverse=True,
        )
    }


@router.post("/preview", summary="Start preview server for existing site")
async def preview_site(req: PreviewRequest):
    """Serve an already-generated site directory and return the URL."""
    from tools.website_generator import start_preview  # type: ignore
    try:
        port = start_preview(req.directory)
        return {
            "preview_url": f"http://localhost:{port}",
            "port": port,
            "directory": req.directory,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/stop", summary="Stop preview server(s)")
async def stop_preview(req: StopRequest = StopRequest()):
    """Stop one preview server (by port) or all if port is omitted."""
    from tools.website_generator import stop_preview as _stop  # type: ignore
    result = _stop(req.port)
    return result


@router.get("/styles", summary="List available style presets")
async def list_styles():
    from tools.website_generator import STYLE_HINTS  # type: ignore
    return {
        "styles": [
            {"name": k, "description": v}
            for k, v in STYLE_HINTS.items()
        ]
    }
