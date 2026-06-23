# JARVIS UI Wiring Map

| UI Interface | Frontend Logic | API Endpoint | Backend Path | Status |
| :--- | :--- | :--- | :--- | :--- |
| **WebUI** | `api.ts`, `ws.ts` | `/api/chat`, `/ws/chat_stream` | `core/routes/chat.py`, `core/routes/websocket.py` | **WORKING** |
| **CLI** | `cli_requests.py` | `/ws/chat_stream` | `core/routes/websocket.py` | **PARTIAL** (Hangs on completion) |
| **TUI** | `jarvis_client.py` | `/ai_os/execute` | `api/ai_os_routes.py` | **BROKEN** (Missing `jarvis_os`) |
| **Flutter** | `api_config.dart` | `/api/chat` | `core/routes/chat.py` | **WORKING** |
| **Electron** | `main.js` | `/api/screen/understand` | `routers/screen.py` | **WORKING** |

---

## Connectivity Gaps
1.  **TUI Isolation:** The TUI is the only interface hitting the broken `ai_os` path.
2.  **CLI Hang:** The CLI uses the WebSocket path but fails to handle the termination sequence properly.
3.  **Redundancy:** The WebUI and CLI use different endpoints (`/api/chat` vs `/ws/chat_stream`) for the same intent.
