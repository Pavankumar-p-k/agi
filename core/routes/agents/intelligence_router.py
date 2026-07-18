# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.auth import User, verify_token

router = APIRouter(tags=["Intelligence & Memory"])

@router.post("/search")
async def search_route(req: dict, user: User = Depends(verify_token)):
    from tools.search_fallback import format_results, search
    from tools.search_tool import decision_gate
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

    from core.audit_log import audit_log
    from core.ssrf import assert_safe_url
    if instruction.startswith("http"):
        try:
            assert_safe_url(instruction)
        except ValueError as e:
            audit_log.log("ssrf_blocked", user_id=user.uid, path="/browse", method="POST", request_body={"instruction": instruction})
            raise HTTPException(400, str(e))

    from core.browser_manager import BrowserManager
    browser = BrowserManager.instance()

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
    import importlib as _il
    memory = _il.import_module("memory.memory_facade").memory
    results = memory.recall(q, limit=limit)
    return {"query": q, "results": results[:limit]}
