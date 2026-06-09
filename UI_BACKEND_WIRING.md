# JARVIS UI Backend Wiring Audit

## UI Connectivity Map

| UI Interface | Backend Endpoint | Protocol | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **CLI** | `/api/chat` / `/ws/chat_stream` | REST/WS | **BROKEN** | WebSocket streaming hangs due to missing `stream_end` event. |
| **TUI** | `/ai_os/execute` | REST | **BROKEN** | Fails due to missing `jarvis_os` dependency. |
| **WebUI** | `/api/chat` / `/ws/chat_stream` | REST/WS | **CONNECTED** | Most stable path; handles `complete` flag correctly. |
| **Electron** | `/api/screen/understand` | REST | **PARTIAL** | Vision features work; Chat opens in external browser (WebUI). |

---

## Detailed Wiring Analysis

### CLI (Command Line Interface)
- **Can user send message?** YES.
- **Can model receive message?** YES.
- **Can model reply?** YES.
- **Can UI display reply?** **NO** (Hangs).
- **Verdict**: **BROKEN**. Default streaming mode causes permanent hang waiting for termination signal.

### TUI (Terminal User Interface)
- **Can user send message?** YES.
- **Can model receive message?** NO.
- **Can model reply?** NO.
- **Can UI display reply?** **NO** (Shows error).
- **Verdict**: **BROKEN**. Missing critical dependency `jarvis_os` makes the orchestrator non-functional.

### WebUI (Next.js App)
- **Can user send message?** YES.
- **Can model receive message?** YES.
- **Can model reply?** YES.
- **Can UI display reply?** YES.
- **Verdict**: **CONNECTED**. This is the primary functional interface.

### Electron (System Dot)
- **Can user send message?** YES (Win+J).
- **Can model receive message?** YES.
- **Can model reply?** YES.
- **Can UI display reply?** YES.
- **Verdict**: **CONNECTED**. Vision-specific route `/api/screen/understand` is functional.

---

## Conclusion
JARVIS suffers from **Backend Fragmentation**. The CLI and TUI use different backend routes than the WebUI, and those routes are either buggy (CLI WS) or broken by missing code (TUI AI OS). Only the WebUI and the specialized Vision route in Electron are currently reliable for end-to-end communication.
