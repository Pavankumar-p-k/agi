# JARVIS Headless Realtime Automation Roadmap

Generated from the local runtime audit on 2026-08-05.

## Goal

Make JARVIS usable as a realtime automation runtime without depending on the CLI, TUI, GUI, or web UI. The durable product surface should be a background service with stable APIs, WebSockets, direct Python imports, tool contracts, permissions, health checks, and event streams.

## Target Architecture

```text
External caller
  |
  | REST / WebSocket / MCP / direct Python
  v
Jarvis runtime daemon
  |
  v
Canonical pipeline
  |
  +--> Identity / tenant / auth / permissions
  +--> Memory / context / knowledge
  +--> Reasoning / planner / model router
  +--> Tool executor
          |
          +--> Native tools
          +--> Plugin tools
          +--> MCP tools
          +--> Provider adapters
          +--> Browser worker
          +--> Desktop worker
          +--> External APIs
  |
  v
Job store + event stream + audit log
```

## Developer Priorities

1. Fix broken runtime imports and startup warnings.
2. Expose stable headless tool contracts:
   - `GET /api/tools`
   - `GET /api/tools/{name}/schema`
   - `POST /api/tools/execute`
3. Add a durable job API:
   - `POST /api/jobs`
   - `GET /api/jobs/{id}`
   - `POST /api/jobs/{id}/cancel`
   - `POST /api/jobs/{id}/approve`
4. Add a realtime event stream:
   - `WS /events`
   - job-level event filtering
   - tool started/progress/completed/failed events
5. Make all transports call the same internal path:
   - `core.pipeline.process_message`
   - `core.tools.executor.tool_executor.execute`
6. Split local desktop control into a worker process with explicit permissions.
7. Add a truthful full health API for providers, integrations, secrets, browser automation, Docker sandbox, plugins, routes, and tools.
8. Convert every feature into a tested tool contract with deterministic input/output shapes.
9. Add replayable audit logs for every automation action.
10. Package JARVIS as a background daemon, with UI surfaces optional.

## Current Implementation Status

| Item | Status | Notes |
| --- | --- | --- |
| Runtime architecture audit | Done | See `docs/architecture/jarvis_real_runtime_architecture.html`. |
| Broken WhatsApp route package import | Done | `core.routes.chat` imports the real WhatsApp router module. |
| Missing automation route module | Done | Added lightweight `automation.routes` with status and explicit send endpoints. |
| Headless tool list API | Done | Backed by `core.tools.execution.handlers.get_registered_tools`. |
| Headless tool execution API | Done | Backed by `core.tools.executor.tool_executor`. |
| Docker sandbox availability | Verified | Docker Desktop 4.72.0 / Engine 29.4.2 responds, and `core.sandbox.docker_sandbox.docker_sandbox.available` is `True`. |
| Realtime event stream | Not started | Should use the existing event bus/execution manager events where possible. |
| Durable jobs API | Not started | Should wrap long-running tool/pipeline calls rather than block HTTP requests. |
| Full health truth API | Not started | Existing diagnostics exist, but do not yet expose route/tool/dependency truth in one place. |
| Desktop worker split | Not started | Current desktop/browser control is mixed into tools/providers. |

## Direct Non-UI Usage

Pipeline request:

```python
import asyncio
from core.pipeline import process_message
from core.pipeline.messages import Request

async def main():
    response = await process_message(Request(
        text="Research this repo and propose the next task",
        transport="python",
        user_id="local-user",
        session_id="headless-1",
    ))
    print(response.text)

asyncio.run(main())
```

Tool execution:

```python
import asyncio
from core.tools._constants import ToolBlock
from core.tools.executor import tool_executor

async def main():
    desc, result = await tool_executor.execute(
        ToolBlock("list_models", "{}"),
        session_id="headless-1",
        owner="local-user",
    )
    print(desc, result)

asyncio.run(main())
```

## Change Log

- 2026-08-05: Roadmap created and first implementation slice started.
- 2026-08-05: Fixed chat package WhatsApp router import, added `automation.routes`, and added first headless tool API routes.
- 2026-08-05: Rechecked Docker after user correction. Docker is available in the current environment; the earlier unavailable warning was stale or process-context-specific.
