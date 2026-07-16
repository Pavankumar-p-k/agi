import logging
logger = logging.getLogger(__name__)
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

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..auth import User, verify_token

router = APIRouter(tags=["Utilities & Code"])


async def _ollama_ping() -> bool:
    """Check Ollama connectivity without importing llm_router."""
    try:
        import httpx
        from core.config_registry import config
        url = config.get("ollama.base_url", "http://localhost:11434")
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"{url}/api/tags")
        return r.status_code == 200
    except Exception:
        return False

@router.get("/api/system/status")
async def get_system_status():
    """Canonical system health and model status."""
    from core.config_registry import config
    ollama_ok = await _ollama_ping()
    model = config.get("llm.chat_model")
    return {
        "status": "online",
        "ollama": "reachable" if ollama_ok else "unreachable",
        "model": model,
        "model_router": {
            "models": [model.split("/", 1)[1] if "/" in model else model] if model and ollama_ok else [],
        },
        "version": "0.1.0",
    }


class CodeReviewRequest(BaseModel):
    code: str
    language: str
    context: str | None = None

@router.post("/api/code/review")
async def code_review(
    req: CodeReviewRequest,
    user: User = Depends(verify_token),
):
    """Review code for bugs, security issues, and style problems."""
    from core.pipeline.internal_client import prompt as llm_prompt
    prompt_text = (
        f"Review this {req.language} code for:\n"
        f"1. Bugs and logic errors\n"
        f"2. Security vulnerabilities\n"
        f"3. Performance issues\n"
        f"4. Code style improvements\n\n"
        f"Context: {req.context or 'N/A'}\n\n"
        f"```{req.language}\n{req.code}\n```\n\n"
        f"Format: For each issue found, state: SEVERITY (critical/major/minor), what, where, fix."
    )
    try:
        review = await llm_prompt(prompt_text, user_id=user.username if user else "__system__")
        return {"review": review, "language": req.language}
    except Exception as e:
        logger.error("Utility route failed: %s", e, exc_info=True)
        return {"error": "Operation failed", "language": req.language}
