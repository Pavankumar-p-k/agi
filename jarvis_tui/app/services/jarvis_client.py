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

from __future__ import annotations

import json
import os
from collections.abc import AsyncGenerator
from typing import Any

import httpx


class JarvisClient:
    """
    Service to communicate with the JARVIS FastAPI backend.
    """
    def __init__(self, base_url: str | None = None):
        if base_url is None:
            base_url = os.environ.get("JARVIS_SERVER", "http://127.0.0.1:8000")
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=60.0)

    async def execute_prompt(self, prompt: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Sends a prompt to the /api/agent/stream endpoint (as a simple POST for the TUI)."""
        # Note: The TUI expects a full response, so we point it to the non-streaming chat if possible,
        # but since we want to unify, we use /api/chat which is stateful and reliable.
        response = await self.client.post("/api/chat", json={
            "message": prompt,
            "session_id": "tui_session",
            "context": str(context or {})
        })
        response.raise_for_status()
        res_data = response.json()
        # Map /api/chat response to what the TUI expects
        return {"status": 200, "result": {"success": True, "reply": res_data.get("response", "")}}

    async def stream_events(self) -> AsyncGenerator[dict[str, Any], None]:
        """Streams events from the /ai_os/events SSE endpoint."""
        async with self.client.stream("GET", "/ai_os/events") as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[len("data: "):]
                    try:
                        yield json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

    async def get_status(self) -> dict[str, Any]:
        """Gets status from /ai_os/status."""
        response = await self.client.get("/ai_os/status")
        response.raise_for_status()
        return response.json()

    async def close(self):
        await self.client.aclose()
