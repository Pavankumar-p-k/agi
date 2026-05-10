# JARVIS Local-First Stack

This layer adds local-only infrastructure so JARVIS can move closer to Codex/OpenClaw-style operation without requiring cloud model providers.

## Added Components

- `backend/jarvis_os/model_gateway.py`
  - Local Ollama gateway
  - Task-to-model routing for chat, planning, coding, reasoning, and vision
- `backend/jarvis_os/browser/controller.py`
  - Local browser controller
  - Playwright-aware with safe `webbrowser` fallback
- `backend/jarvis_os/skills/registry.py`
  - Local skill discovery from repo `skills/` and user `~/.codex/skills`
- `backend/jarvis_os/daemon/supervisor.py`
  - Background queue/supervisor loop for always-on work
- `backend/jarvis_os/tool_router/router.py`
  - New tools: `browser`, `shell`, `skills`, `models`

## Local-Only Defaults

- `JARVIS_LOCAL_ONLY=1` is treated as the default local-first mode.
- `OLLAMA_URL` points the runtime at the local Ollama server.
- The assistant tool now prefers the local Ollama gateway when local-only mode is enabled.

## CLI Behavior

- `jarvis cli` now supports:
  - `/plan <goal>`
  - `/goal <goal>`
  - `/develop <goal>`
  - `/tools`
  - `/mode chat`
  - `/mode agent`
  - `/vision <prompt>`
- Agent mode automatically previews plans for task-like prompts.

## Current Boundaries

- Browser sign-in and rich DOM workflows still need a dedicated browser executor.
- Messaging app actions beyond opening/search bootstrap still need stronger app-specific controllers.
- The supervisor is a queue/loop foundation, not a full 24/7 task orchestration UI.
- The shell tool is local and workspace-scoped, but it remains safety-gated.
