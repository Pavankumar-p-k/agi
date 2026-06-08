from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from ..auth import verify_token, User
from ..database import get_db

router = APIRouter(tags=["Intelligence & Memory"])

@router.post("/search")
async def search_route(req: dict, user: User = Depends(verify_token)):
    from tools.search_tool import decision_gate
    from tools.search_fallback import search, format_results
    query = req.get("query", "")
    if not query:
        raise HTTPException(400, "Query is required")
    
    # Check decision gate
    should_search = decision_gate.should_search(query, req.get("confidence", 1.0))
    if not should_search and not req.get("force", False):
        return {"searched": False, "reason": "Decision gate rejected search"}
    
    results = search(query, max_results=req.get("max_results", 5))
    scraped = "\n".join(r.get("content", "") for r in results)
    
    return {
        "searched": True,
        "results": results,
        "context": scraped,
        "formatted": format_results(results),
    }

class BrowseRequest(BaseModel):
    instruction: str = ""
    task: str = ""

@router.post("/browse")
async def browser_agent(req: BrowseRequest, user: User = Depends(verify_token)):
    instruction = req.instruction or req.task
    if not instruction:
        raise HTTPException(400, "instruction is required")
    
    from core.ssrf import assert_safe_url
    from core.audit_log import audit_log
    if instruction.startswith("http"):
        try:
            assert_safe_url(instruction)
        except ValueError as e:
            audit_log.log("ssrf_blocked", user_id=user.uid, path="/browse", method="POST", request_body={"instruction": instruction})
            raise HTTPException(400, str(e))
    
    from tools.browser_tool import JarvisBrowser
    browser = JarvisBrowser()
    
    result = await browser.execute(instruction)
    audit_log.log("browse", user_id=user.uid, path="/browse", method="POST", status=200, request_body={"instruction": instruction})
    return result

@router.get("/api/memory/search")
async def memory_search(
    q: str = Query("", description="Search query"),
    limit: int = Query(5, ge=1, le=50),
    user: User = Depends(verify_token),
):
    """Search JARVIS's tiered memory (hot/warm/cold)."""
    if not q:
        return {"results": []}
    from memory.memory_facade import memory
    results = memory.recall(q, limit=limit)
    return {"query": q, "results": results[:limit]}
