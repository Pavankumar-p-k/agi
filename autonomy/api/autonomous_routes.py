"""
api/autonomous_routes.py
═══════════════════════════════════════════════════════════════════
NEW API ROUTES — 4-layer autonomous system.

Mount on EXISTING gateway.py FastAPI app:
  from api.autonomous_routes import mount_autonomous_routes, inject_autonomous
  inject_autonomous(orchestrator=..., ...)
  mount_autonomous_routes(app)

Adds:
  POST /think              → Full 4-layer reasoning
  POST /plan               → L3 dry-run plan
  POST /execute            → L3 full execution
  POST /assist             → L2 code assistant
  GET  /memory/search      → SemanticStore semantic search
  POST /system/action      → L4 system control
  GET  /layers/status      → All 4 layer health
  GET  /executions/recent  → Audit log
  GET  /safety/blocks      → Recent safety blocks
"""
from __future__ import annotations
import logging, time
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("jarvis.api.autonomous")

# Injected references
_orchestrator = None
_brain        = None
_assistant    = None
_executor     = None
_controller   = None
_store        = None
_proactive    = None   # ProactiveWorker — injected separately


def inject_autonomous(orchestrator=None, brain=None, assistant=None,
                       executor=None, controller=None, store=None,
                       proactive=None):
    global _orchestrator,_brain,_assistant,_executor,_controller,_store,_proactive
    _orchestrator = orchestrator
    _brain        = brain
    _assistant    = assistant
    _executor     = executor
    _controller   = controller
    _store        = store
    _proactive    = proactive
    logger.info("[API] Autonomous routes injected ✓")


def mount_autonomous_routes(app):
    app.include_router(router)
    logger.info("[API] Autonomous routes mounted ✓")


router = APIRouter(tags=["autonomous"])


# ── Request models ────────────────────────────────────────────────

class ThinkReq(BaseModel):
    text:     str
    platform: str = "api"
    session:  str = ""

class PlanReq(BaseModel):
    goal:    str
    intent:  str  = "task"
    dry_run: bool = True

class ExecReq(BaseModel):
    goal:    str
    intent:  str  = "task"
    context: str  = ""
    dry_run: bool = False

class AssistReq(BaseModel):
    action:   str
    code:     str
    language: str  = "python"
    file:     str  = ""
    extra:    dict = {}

class SysActionReq(BaseModel):
    action: str
    params: dict = {}


# ── /think ────────────────────────────────────────────────────────

@router.post("/think")
async def think(req: ThinkReq):
    """Full 4-layer reasoning — routes to correct layer automatically."""
    if not _orchestrator:
        raise HTTPException(503, "Orchestrator not initialized")
    r = await _orchestrator.process(req.text, req.platform,
                                     session=req.session)
    return {
        "reply":       r.reply,
        "intent":      r.intent,
        "emotion":     r.emotion,
        "confidence":  r.confidence,
        "route":       r.route,
        "source":      r.source,
        "model":       r.model_used,
        "plan":        r.plan,
        "exec_output": r.exec_output,
        "latency_ms":  r.latency_ms,
    }


# ── /plan ─────────────────────────────────────────────────────────

@router.post("/plan")
async def plan(req: PlanReq):
    """Generate execution plan without running it."""
    if not _executor:
        raise HTTPException(503, "ExecutorLayer not initialized")
    r = await _executor.execute(req.goal, req.intent, dry_run=True)
    return {
        "goal":   req.goal,
        "output": r.output,
        "risk":   r.plan.estimated_risk if r.plan else 0,
        "steps":  [
            {"index": s.index, "description": s.description,
             "has_code": bool(s.code), "tool": s.tool}
            for s in (r.plan.steps if r.plan else [])
        ],
    }


# ── /execute ──────────────────────────────────────────────────────

@router.post("/execute")
async def execute(req: ExecReq):
    """Full L3 execution: plan → execute → verify → fix."""
    if not _executor:
        raise HTTPException(503, "ExecutorLayer not initialized")
    r = await _executor.execute(req.goal, req.intent,
                                  req.context, req.dry_run)
    return {
        "goal":        req.goal,
        "status":      r.status,
        "steps_done":  r.steps_done,
        "steps_total": r.steps_total,
        "output":      r.output,
        "error":       r.error,
        "latency_ms":  r.latency_ms,
        "audit_id":    r.audit_id,
    }


# ── /assist ───────────────────────────────────────────────────────

@router.post("/assist")
async def assist(req: AssistReq):
    """L2 code assistant: complete|explain|review|fix|refactor|test|docs."""
    if not _assistant:
        raise HTTPException(503, "AssistantLayer not initialized")
    r = await _assistant.handle(req.action, req.code,
                                  req.language, req.file, req.extra)
    return {
        "action":     r.action,
        "content":    r.content,
        "confidence": r.confidence,
        "files_used": r.files_used,
        "latency_ms": r.latency_ms,
        "model":      r.model_used,
    }


# ── /memory/search ────────────────────────────────────────────────

@router.get("/memory/search")
async def memory_search(q: str, top_k: int = 5,
                          category: str = ""):
    """Semantic search through JARVIS memory."""
    if not _store:
        raise HTTPException(503, "SemanticStore not initialized")
    results = _store.recall(q, top_k=top_k)
    if category:
        results = [r for r in results
                   if r.get("category") == category]
    return {"query": q, "results": results, "count": len(results)}


# ── /system/action ────────────────────────────────────────────────

@router.post("/system/action")
async def system_action(req: SysActionReq):
    """Direct L4 system action — all pass through SafetyGuard."""
    if not _controller:
        raise HTTPException(503, "ControllerLayer not initialized")
    r = await _controller.execute(req.action, **req.params)
    return {
        "action":      req.action,
        "success":     r.success,
        "output":      r.output,
        "error":       r.error,
        "duration_ms": r.duration_ms,
    }


# ── /layers/status ────────────────────────────────────────────────

@router.get("/layers/status")
async def layers_status():
    """Health of all 4 layers + memory + safety + proactive worker."""
    return {
        "layers": {
            "L1_brain":      _brain       is not None,
            "L2_assistant":  _assistant   is not None,
            "L3_executor":   _executor    is not None,
            "L4_controller": _controller  is not None,
            "orchestrator":  _orchestrator is not None,
        },
        "memory": {
            "online": _store is not None,
            "stats":  _store.stats() if _store else {},
        },
        "safety": {
            "recent_blocks": (
                _controller.recent_blocks(5) if _controller else [])
        },
        "proactive": (
            _proactive.status() if _proactive else {"running": False}
        ),
        "ts": time.time(),
    }


@router.get("/proactive/status")
async def proactive_status():
    """Proactive background worker status."""
    if not _proactive:
        raise HTTPException(503, "ProactiveWorker not initialized")
    return _proactive.status()


@router.post("/proactive/trigger")
async def proactive_trigger(trigger: str = "idle_recovery"):
    """Manually trigger a proactive monitor (for testing)."""
    if not _proactive:
        raise HTTPException(503, "ProactiveWorker not initialized")
    # Reset the cooldown so it fires on next tick
    _proactive._cooldowns.reset(trigger)
    return {"triggered": trigger, "next_check_in_sec": 30}


# ── /executions/recent ───────────────────────────────────────────

@router.get("/executions/recent")
async def recent_executions(n: int = 10):
    """Recent execution audit log from L3."""
    if not _executor:
        raise HTTPException(503, "ExecutorLayer not initialized")
    return {"executions": _executor.recent(n)}


# ── /safety/blocks ────────────────────────────────────────────────

@router.get("/safety/blocks")
async def safety_blocks(n: int = 10):
    """Recent actions blocked by SafetyGuard."""
    if not _controller:
        raise HTTPException(503, "ControllerLayer not initialized")
    return {"blocked": _controller.recent_blocks(n)}
