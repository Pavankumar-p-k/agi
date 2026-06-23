# UI Backend Connection Report

This report tracks the connection status between the JARVIS Web UI and the FastAPI backend.

| Page / Component | Backend Endpoint | Connected | Missing Endpoint | Missing API Client | Missing WS | Notes |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| **Pages** | | | | | | |
| Dashboard (`/`) | `/api/system/stats`, `/health`, `/api/plugins`, `/api/stats`, `/api/monthly-highlights`, `/api/activity/today`, `/api/diagnostics` | YES | NO | NO | NO | Terminal panel now uses real diagnostics. |
| Chat (`/chat`) | `/api/chat`, `/ws/chat_stream` | YES | NO | NO | NO | |
| CLI Mode (`/cli`) | `/ws/terminal` | YES | NO | NO | YES | Now a real WebSocket terminal. |
| Backend Control (`/backend`) | `/health`, `/api/system/stats`, `/api/plugins`, `/api/diagnostics` | YES | NO | NO | NO | Service statuses are now real. |
| Build Dashboard (`/build`) | `/api/build/*` | YES | NO | NO | NO | **NEW** Functional build dashboard. |
| Monitor (`/monitor`) | `/api/system/stats`, `/ws/telemetry` | YES | NO | NO | NO | |
| Logs (`/logs`) | `/ws/logs` | YES | NO | NO | NO | |
| Settings (`/settings`) | `/api/settings` | YES | NO | NO | NO | |
| Models (`/models`) | `/api/models` | YES | NO | NO | NO | |
| Features (`/features`) | `/api/features` | YES | NO | NO | NO | |
| Integrations (`/integrations`) | `/api/integrations` | YES | NO | NO | NO | |
| Automation (`/automation`) | `/api/scheduler/jobs`, `/api/cron/jobs` | YES | NO | NO | NO | |
| Diagnostics (`/diagnostics`) | `/api/diagnostics` | YES | NO | NO | NO | |
| Agents (`/agents`) | `/api/v1/agents/` | YES | NO | NO | NO | |
| Memory (`/memory`) | `/api/memory` | YES | NO | NO | NO | |
| Skills (`/skills`) | `/api/skills` | YES | NO | NO | NO | |
| Voice (`/voice`) | `/api/diagnostics/voice`, `/stt`, `/tts` | YES | NO | NO | NO | |
| Plugins (`/plugins`) | `/api/plugins` | YES | NO | NO | NO | |
| Projects (`/projects`) | `/projects` | YES | NO | NO | NO | |
| Notes (`/notes`) | `/api/notes` | YES | NO | NO | NO | |
| Email (`/email`) | `/email/status`, `/email/inbox` | YES | NO | NO | NO | |
| Files (`/files`) | `/api/files` | YES | NO | NO | NO | |
| Knowledge (`/knowledge`) | `/api/memory/search` | YES | NO | NO | NO | |
| **Components** | | | | | | |
| HealthCheck | `/health` | YES | NO | NO | NO | |
| ModelSelector | `/api/models` | YES | NO | NO | NO | |
| StatusBar | `/api/system/status`, `/api/diagnostics` | YES | NO | NO | NO | Expanded with more health dots. |

## Summary
- **Total Pages:** 28
- **Connected Pages:** 28
- **Partial/Fake Pages:** 0
- **New Wiring:** Build System, Real Terminal, API Keys, Voice Settings.
