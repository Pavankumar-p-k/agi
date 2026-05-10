# JARVIS Monorepo Review

## 1. Overview

This repository implements a **personal AI assistant platform** (JARVIS) with a **Python FastAPI backend**, an optional **Flutter frontend**, and numerous modular subsystems (autonomy layers, automation, vision, student AGI, etc.). The goal is to be a **self-hosted personal assistant** that can:

- Chat conversationally via an LLM-driven assistant
- Run autonomous decision-making workflows (4-layer autonomy stack)
- Control local hardware and software (automation, adb, PC macros)
- Process and analyze vision / camera input
- Manage notes, reminders, and personal data via a backend database
- Expose extensible API routes for 3rd-party clients (mobile, web, CLI)
- Optionally embed a standalone “Student AGI” service for more advanced learning/agent behavior

This document is intended as a full project review: structure, key modules, flows, and how components connect.

---

## 2. Repository Structure (Top-Level)

The repo is organized as a **monorepo** with multiple workstreams under a single root:

- `backend/` — Python FastAPI backend + AI/automation services
- `apps/jarvis_app/` — Flutter mobile/desktop front-end (Android/Windows/iOS/Mac/Linux/web)
- `services/jarvis_social/` — Optional social AI service
- `docs/` — Guides, setup documentation, architecture diagrams
- `archive/` — Legacy/duplicate code kept for reference
- `scripts/` — Utilities and tooling scripts (e.g., project analysis)
- `jarvis_main.py` — Legacy/entry script that can launch the backend
- `start_jarvis.bat` / `start_jarvis_multi.bat` — Windows startup batching for multiple services

---

## 3. Backend (Python FastAPI)

### 3.1. Backend footprint

- **Total Python files (backend): ~17,946** (across all submodules)
- **Top-level backend packages:**
  - `core`, `assistant`, `autonomy`, `automation`, `vision`, `learning`, `orchestrator`, `memory`, `reminders`, `tools`, etc.

### 3.2. Entrypoint

- `backend/core/main.py` is the canonical FastAPI application entrypoint.
- It initializes dependencies (database, Firebase auth, reminder scheduler, assistant engine) and mounts routers for:
  - Core assistant endpoints (`/api/*`)
  - Vision endpoints (`/vision/*`)
  - Automation endpoints (`/automation/*`)
  - Autonomous stack endpoints (`/autonomy/*` and root `/think` for legacy support)
  - Student AGI proxy endpoints (`/student-agi/*`)

### 3.3. Startup lifecycle

- Uses `@asynccontextmanager` to run startup logic (DB init, Firebase, reminders, autonomous stack) and graceful shutdown logic.
- The autonomous stack initialization is handled by `autonomy.initialize_autonomous_stack()` and runs during startup.

### 3.4. Core modules

#### 3.4.1. `core/`
- `core/config.py` — configuration values (HOST, PORT, etc.)
- `core/database.py` — SQLAlchemy async database, user model, schema migration helpers
- `core/auth.py` — authentication (Firebase token verification etc.)

#### 3.4.2. `assistant/`
- `assistant/engine.py` — primary assistant engine (Jarvis) that routes requests into LLMs and handles text/voice generation.
- `assistant/voice/` (if present) — TTS/voice pipeline integration.

#### 3.4.3. `reminders/`, `notes/`, `automation/`, `vision/` and others
- `reminders/` — scheduling, persistence, runtime dispatch
- `notes/` — note CRUD + activity tracking
- `automation/` — automation workflows, PC automation, ADB, etc.
- `vision/` — OpenCV-based vision endpoints (face recognition, camera capture, etc.)

---

## 4. Autonomous Stack (L1–L4)

This is a core differentiator: a **4-layer autonomous intelligence system** designed to run in a single process and provide both **reactive** and **proactive** capabilities.

### 4.1. Overview

- **L1 (Brain Layer)** — The central decision-making brain. Routes queries to LLMs, handles prompt engineering, and maintains high-level context.
- **L2 (Assistant Layer)** — Project-aware assistant that scans the codebase and provides developer-oriented intelligence (code search, task extraction, etc.).
- **L3 (Executor Layer)** — Executes actions, runs tools, evaluates code, and simulates workflows.
- **L4 (Controller Layer)** — Interfaces with system-level controllers (ADB, OS automation, hardware interfacing, etc.).

### 4.2. Key packages

- `backend/autonomy/__init__.py` — Initialization bridge that launches all layers; exposes `get_router()` for mounting the API
- `backend/autonomy/core/autonomous_orchestrator.py` — Wires the layers together and provides the `think()`/`plan()` interface used by API and CLI
- `backend/autonomy/api/autonomous_routes.py` — FastAPI router that exposes `/think`, `/plan`, `/execute`, etc.
- `backend/autonomy/cli/jarvis_cli.py` — Command-line harness for interacting with `/think` (used by scripts and users)
- `backend/autonomy/l1_brain/`, `l2_assistant/`, `l3_executor/`, `l4_controller/` — layer implementations
- `backend/autonomy/core/proactive_worker.py` — Runs in background to trigger autonomous checks (e.g., every 30s)

### 4.3. Initialization

`autonomy.initialize_autonomous_stack()` (called from `core/main.py`) performs:
1. Loading of optional shared core modules (fusion engine, world state, semantic store, etc.)
2. Layer instantiation (L1–L4) with safe fallbacks on missing dependencies
3. Orchestrator wiring if all layers are available
4. Background worker startup for proactive decision cycles
5. Injection of runtime layer handles into API route handlers

This means that **API endpoints exist regardless of initialization state**, but will return `503` if the stack is not yet ready.

---

## 5. API Surface (FastAPI Routes)

### 5.1. Core routes (FastAPI `core/main.py`)
- `/` — health/root check
- `/health` — returns API status + LLM availability
- `/api/chat` — chat endpoint (LLM conversation)
- `/api/reminders` — list/create/delete reminders
- `/api/chat/history` — user chat history
- (others in core routers)

### 5.2. Autonomy routes (`/think` etc.)
- `/think` — primary autonomous query interface
- `/plan` — planning/action generation
- `/execute` — execute generated plans via executor layer

**Mount points:**
- Routed under `/autonomy/*` for namespaced access
- Also mounted at root for backwards compatibility (legacy CLI and scripts)

### 5.3. Student AGI routes (`/student-agi/*`)
- Proxy to a separate `student_agi` service that can be launched independently.
- Routes are only mounted if the service is available

### 5.4. Vision routes (`/vision/*`)
- Camera capture
- Face recognition and registration
- Image analysis

### 5.5. Automation routes (`/automation/*`)
- Trigger PC automation tasks
- Dispatch commands to ADB controllers

---

## 6. CLI and Scripts

### 6.1. CLI
- `backend/autonomy/cli/jarvis_cli.py` — primary CLI interface for autonomous queries.
  - Example: `python backend/autonomy/cli/jarvis_cli.py think "what should I focus on today?"`
  - Uses configurable base URL via `AUTONOMY_PREFIX` env var to route to server.

### 6.2. Startup scripts
- `start_jarvis.bat` — starts the backend and supporting services
- `start_jarvis_multi.bat` — starts multiple model servers (Ollama) for multi-model routing
- `jarvis_main.py` — legacy entrypoint for launching the backend as a script

### 6.3. Analysis scripts
- `scripts/` contains helper scripts (such as project metadata generators)

---

## 7. Frontend (Flutter)

### 7.1. Location
- `apps/jarvis_app/` contains the Flutter application.

### 7.2. Features
- Chat UI over `/api/chat`
- Voice input / TTS (if configured)
- Reminders and notes management
- Firebase auth integration (requires `firebase_options.dart` via `flutterfire configure`)

---

## 8. Optional/Plug-in Systems

### 8.1. Vision
- Uses OpenCV (`cv2`) for camera feed processing
- Supports face registration / recognition
- Exposed via `backend/api/vision_routes.py`

### 8.2. Automation
- PC automation integration via `automation/pc_automation.py`
- Android ADB integration via `automation/adb_controller.py`

### 8.3. Student AGI
- A separate microservice located in `backend/learning/student_agi/`
- Launch with: `python backend/learning/student_agi/student_agi_main.py`
- Exposed via `/student-agi/*` endpoints when running

---

## 9. Dependency & Environment Notes

- Backend recommended setup (from `README.md`):
  - `python -m venv backend/venv`
  - `backend\venv\Scripts\activate`
  - `pip install -r backend/requirements.txt`
  - `python -m core.main`

- Many components are optional and will gracefully degrade if dependencies are missing (e.g., vision, TTS, ADB).

---

## 10. How the Pieces Connect (Data/Control Flow)

1. **Client** (Flutter app / CLI / Web) → **FastAPI**
2. FastAPI route verifies auth (Firebase token) and dispatches to the correct subsystem:
   - Chat request → `assistant/engine.py` (LLM + prompt architecture)
   - `/think` request → `autonomy/api/autonomous_routes.py` → orchestrator → L1/L2/L3/L4
   - Automation request → `automation/routes.py`
   - Vision request → `vision/routes.py`
3. **Autonomy orchestrator** (if initialized) can:
   - Use LLM to interpret requests
   - Plan multi-step actions via L2/L3
   - Execute actions via Local Executor (L3) and Controller (L4)
   - Trigger proactive checks via the Proactive Worker
4. Results flow back through FastAPI to the client.

---

## 11. Key Files / Modules (Quick Reference)

### Core
- `backend/core/main.py` — server startup, routers, lifespan
- `backend/core/database.py` — DB/ORM models
- `backend/core/auth.py` — token validation (Firebase)

### Assistant
- `backend/assistant/engine.py` — main LLM assistant logic

### Autonomy
- `backend/autonomy/__init__.py` — init bridge + router
- `backend/autonomy/core/autonomous_orchestrator.py` — orchestrator logic
- `backend/autonomy/api/autonomous_routes.py` — API endpoints
- `backend/autonomy/cli/jarvis_cli.py` — CLI integration

### Automation
- `backend/automation/routes.py` — API endpoints
- `backend/automation/pc_automation.py` — PC automation driver
- `backend/automation/adb_controller.py` — Android ADB driver

### Vision
- `backend/api/vision_routes.py` — vision endpoints

### Learning / Student AGI
- `backend/learning/student_agi/*` — independent agent service

---

## 12. How To Use (Sample Workflows)

### 12.1. Run backend + use CLI

```powershell
cd c:\Users\peter\Desktop\jarvis\backend
.\venv\Scripts\activate
pip install -r requirements.txt
python -m core.main
```

In another terminal:

```powershell
& .\backend\.venv\Scripts\python.exe backend\autonomy\cli\jarvis_cli.py think "what should I focus on today?"
```

### 12.2. Run Flutter app

```bash
cd apps/jarvis_app
flutter pub get
flutter run --dart-define=API_BASE_URL=http://YOUR_PC_IP:8000
```

### 12.3. Run Student AGI service (optional)

```powershell
python backend/learning/student_agi/student_agi_main.py
```

---

## 13. Notes / Recommendations (Industry Level)

- The project is intentionally modular: missing dependencies do not crash startup, but functionality is gated.
- For production readiness, ensure the backend runs in a controlled environment with correct secrets (Firebase credentials, API keys).
- Consider containerization (Docker) for reproducible deployments.
- The autonomy stack is powerful but can be resource-intensive (LLM usage); tune the LLM backend and caching.
- Security: validate authentication tokens and enforce authorization for critical actions (automation, personal data access).

---

## 14. Appendix: Helpful References

- `docs/SETUP_GUIDE.md` — setup instructions
- `docs/FLUTTER_GUIDE.md` — details for Flutter integration
- `docs/CALL_ASSISTANT_GUIDE.md` — usage examples
- `README.md` — high-level overview
