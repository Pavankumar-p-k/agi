"""api/agent_routes.py — REST API for all JARVIS sub-agents."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Any
from core.sub_agents.registry import agent_registry

router = APIRouter(prefix="/agents", tags=["agents"])

class RunRequest(BaseModel):
    task: str
    mode: Optional[str] = None
    lang: Optional[str] = "auto"    # for FORGE
    url: Optional[str] = None       # for PHANTOM
    execute: bool = False            # for MAESTRO
    kwargs: Optional[dict[str, Any]] = None

@router.get("/")
async def list_agents():
    """List all available sub-agents."""
    return {"agents": agent_registry.list_agents()}

@router.post("/{agent_name}/run")
async def run_agent(agent_name: str, req: RunRequest):
    """Run a specific sub-agent."""
    try:
        kwargs = req.kwargs or {}
        if req.lang: kwargs["lang"] = req.lang
        if req.url: kwargs["url"] = req.url
        if req.execute: kwargs["execute"] = req.execute

        result = await agent_registry.run(
            agent_name.upper(), req.task,
            mode=req.mode, **kwargs
        )
        return result.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{agent_name}/modes")
async def agent_modes(agent_name: str):
    """Get available modes for a sub-agent."""
    cls = agent_registry.get(agent_name.upper())
    if not cls:
        raise HTTPException(status_code=404, detail=f"Agent {agent_name} not found")
    a = cls()
    return {"agent": a.NAME, "modes": a.AVAILABLE_MODES, "default_mode": a.DEFAULT_MODE}

class ParallelRequest(BaseModel):
    tasks: list[dict]   # [{"agent": "NEXUS", "task": "...", "mode": "research"}]

@router.post("/parallel")
async def run_parallel(req: ParallelRequest):
    """Run multiple agents in parallel."""
    results = await agent_registry.run_parallel(req.tasks)
    return {"results": [r.to_dict() for r in results]}

# Convenience shortcuts
@router.post("/nexus")
async def nexus(req: RunRequest):
    return await run_agent("nexus", req)

@router.post("/forge")
async def forge(req: RunRequest):
    return await run_agent("forge", req)

@router.post("/oracle")
async def oracle(req: RunRequest):
    return await run_agent("oracle", req)

@router.post("/maestro")
async def maestro(req: RunRequest):
    return await run_agent("maestro", req)

@router.post("/sentinel")
async def sentinel(req: RunRequest):
    return await run_agent("sentinel", req)
