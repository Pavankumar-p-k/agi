from __future__ import annotations

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

import json
import logging
import os
from collections.abc import AsyncGenerator
from typing import Any

logger = logging.getLogger(__name__)

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
        """Gets status from /health or /api/system/status."""
        try:
            response = await self.client.get("/api/system/status")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError:
            response = await self.client.get("/health")
            return response.json()

    async def get_features(self) -> dict[str, Any]:
        """Gets features from /api/features."""
        response = await self.client.get("/api/features")
        response.raise_for_status()
        return response.json()

    async def get_feature_report(self) -> dict[str, Any]:
        """Gets feature report from /api/features/report."""
        response = await self.client.get("/api/features/report")
        response.raise_for_status()
        return response.json()

    async def toggle_feature(self, slug: str, enabled: bool) -> dict[str, Any]:
        """Toggles a feature."""
        response = await self.client.post(f"/api/features/{slug}/toggle", json={"enabled": enabled})
        response.raise_for_status()
        return response.json()

    async def get_integrations(self) -> dict[str, Any]:
        """Gets integrations from /api/integrations."""
        response = await self.client.get("/api/integrations")
        response.raise_for_status()
        return response.json()

    async def connect_integration(self, name: str, credentials: dict) -> dict[str, Any]:
        """Connects an integration."""
        response = await self.client.post(f"/api/integrations/{name}/connect", json={"credentials": credentials})
        response.raise_for_status()
        return response.json()

    async def disconnect_integration(self, name: str) -> dict[str, Any]:
        """Disconnects an integration."""
        response = await self.client.post(f"/api/integrations/{name}/disconnect")
        response.raise_for_status()
        return response.json()

    async def get_diagnostics(self) -> dict[str, Any]:
        """Gets diagnostics from /api/diagnostics."""
        response = await self.client.get("/api/diagnostics")
        response.raise_for_status()
        return response.json()

    async def get_models(self) -> dict[str, Any]:
        """Gets models from /api/models."""
        response = await self.client.get("/api/models")
        response.raise_for_status()
        return response.json()

    async def get_model_groups(self) -> dict[str, Any]:
        """Gets model groups from /api/models/groups."""
        response = await self.client.get("/api/models/groups")
        response.raise_for_status()
        return response.json()

    async def get_agents(self) -> dict[str, Any]:
        """Gets agents from /api/v1/agents."""
        response = await self.client.get("/api/v1/agents")
        response.raise_for_status()
        return response.json()

    async def run_agent(self, name: str, task: str, mode: str | None = None) -> dict[str, Any]:
        """Runs an agent."""
        data = {"task": task}
        if mode: data["mode"] = mode
        response = await self.client.post(f"/api/v1/agents/{name}/run", json=data)
        response.raise_for_status()
        return response.json()

    async def get_memory_stats(self) -> dict[str, Any]:
        """Gets memory stats from /api/memory/stats."""
        try:
            response = await self.client.get("/api/memory/stats")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.warning("get_memory_stats failed: %s", e)
            return {"memories": []}

    async def get_settings(self) -> list[dict]:
        """Gets all settings."""
        response = await self.client.get("/api/settings")
        response.raise_for_status()
        return response.json()

    async def update_setting(self, key: str, value: Any) -> dict[str, Any]:
        """Updates a setting."""
        response = await self.client.put(f"/api/settings/{key}", json={"value": value})
        response.raise_for_status()
        return response.json()

    async def get_activities(self) -> list[dict]:
        """List all active root activities."""
        try:
            response = await self.client.get("/api/activity")
            response.raise_for_status()
            data = response.json()
            return data.get("activities", [])
        except Exception as e:
            logger.warning("get_activities failed: %s", e)
            return []

    async def get_activity_counts(self) -> dict:
        """Get aggregate counts by status."""
        try:
            response = await self.client.get("/api/activity/counts")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.warning("get_activity_counts failed: %s", e)
            return {}

    async def get_activity_tree(self, activity_id: str) -> dict:
        """Get full activity tree (nodes + edges)."""
        response = await self.client.get(f"/api/activity/{activity_id}/tree")
        response.raise_for_status()
        return response.json()

    async def get_activity_detail(self, activity_id: str) -> dict:
        """Get a single activity node by ID."""
        response = await self.client.get(f"/api/activity/{activity_id}")
        response.raise_for_status()
        return response.json()

    async def get_activity_summary(self, activity_id: str) -> dict:
        """Get summary of an activity."""
        response = await self.client.get(f"/api/activity/{activity_id}/summary")
        response.raise_for_status()
        return response.json()

    async def get_activity_timeline(self, activity_id: str) -> list[dict]:
        """Get nodes in chronological order."""
        response = await self.client.get(f"/api/activity/{activity_id}/timeline")
        response.raise_for_status()
        data = response.json()
        return data.get("timeline", [])

    async def get_activity_replay(self, activity_id: str) -> dict:
        """Get the full ReplayDAG for an activity.

        Returns the complete execution DAG with timeline, decision traces,
        provider/tool/workflow metadata, and summary metrics.
        """
        response = await self.client.get(f"/api/activity/{activity_id}/replay")
        response.raise_for_status()
        return response.json()

    async def pause_activity(self, activity_id: str) -> dict:
        """Suspend a running activity."""
        response = await self.client.post(f"/api/activity/{activity_id}/pause")
        response.raise_for_status()
        return response.json()

    async def resume_activity(self, activity_id: str) -> dict:
        """Resume a suspended activity."""
        response = await self.client.post(f"/api/activity/{activity_id}/resume")
        response.raise_for_status()
        return response.json()

    async def cancel_activity(self, activity_id: str) -> dict:
        """Cancel an activity."""
        import json
        response = await self.client.post(
            f"/api/activity/{activity_id}/cancel",
            content=json.dumps({"activity_id": activity_id, "error": "cancelled by user"}),
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        return response.json()

    async def close(self):
        await self.client.aclose()
