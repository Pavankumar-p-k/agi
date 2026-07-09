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
"""
core/routes/quality.py — Quality Assurance API.

NOTE: POST /api/quality/grade is defined in core/routes/admin.py (mounted).
This module exists for future quality-specific routes.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Quality Assurance"])


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


@router.get("/api/quality/health")
async def quality_health():
    """Health check for the quality grading subsystem."""
    try:
        llm_ok = await _ollama_ping()
        return {"status": "ok" if llm_ok else "degraded", "llm_available": llm_ok}
    except Exception as e:
        return {"status": "error", "error": str(e)}
