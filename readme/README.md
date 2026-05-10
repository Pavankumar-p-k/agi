# JARVIS Monorepo

This repository is organized as a single, professional monorepo for the JARVIS assistant across desktop and Android.

## Structure

- `apps/jarvis_app/` – Flutter app (Android / Windows)
- `backend/` – Python FastAPI backend + AI/automation services
- `services/jarvis_social/` – Social AI engine (optional)
- `docs/` – Guides and architecture docs
- `archive/` – Legacy/duplicate files kept for reference

## Quick Start (Backend)

```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# optional: create backend/.env (see docs/SETUP_GUIDE.md)
python -m core.main
```

## Unified Launcher

From the repo root on Windows you can use:

```powershell
jarvis cli
jarvis server
jarvis server /m
jarvis gui
jarvis up /m --background
jarvis extension list
```

Detailed command reference: `docs/COMMANDS.md`

## JARVIS OS Phase 1

The new modular AI OS runtime now lives in `jarvis_os/` and can be launched without the legacy backend stack:

```powershell
jarvis os list directory .
python -m jarvis_os.interface.cli "search latest web3 news"
python -m jarvis_os.interface.api_server
```

Highlights:

- clean intent -> planning -> execution -> reflection loop
- tool registry with 134 tool entrypoints
- local memory, Ollama routing, agent selection, CLI, and HTTP API
- phase-2 control plane: `--preview`, `--submit`, `--status`, `--jobs`
- phase-3 adaptive layer: learned skills via `--skills`, `--show-skill`, and `--run-skill`
- phase-4 operations layer: policy, telemetry, and schedules via `--schedules`, `--run-due`, and `--telemetry`
- phase-5 autonomy daemon: background polling and heartbeat controls via `--daemon-status`, `--daemon-start`, `--daemon-stop`, and `--daemon-tick`

## Cognitive Agent

The extracted `cognitive_agent/` package now lives under `backend/` and can be launched through the existing root launcher:

```powershell
jarvis cognitive "Research the latest advances in quantum computing"
jarvis cognitive --list-skills
jarvis cognitive --stats
```

Direct backend usage also works from `backend/`:

```powershell
python -m cognitive_agent.main "Write a Python web scraper and test it"
```

### Launcher notes on Windows

- `jarvis gui` and `jarvis up` expect Flutter to be installed and available on `PATH`.
- On Windows, Flutter is commonly installed as `flutter.bat`; the launcher resolves batch-based tools before starting the GUI.
- If GUI startup still fails, verify Flutter itself first with `flutter doctor` and `flutter run -d windows` from `apps/jarvis_app`.

Global install:

```powershell
.\scripts\install_jarvis_global.ps1
```

## Multi-Model Ollama (Option 2)

If you want one Ollama server per model with automatic routing, use:

```bash
start_jarvis_multi.bat
```

## Quick Start (Flutter)

```bash
cd apps/jarvis_app
flutter pub get
flutter run
```

## Notes

- Firebase is required for auth. Replace `apps/jarvis_app/lib/firebase_options.dart` by running:
  `flutterfire configure`
- Update API base URL via Dart define:
  `flutter run --dart-define=API_BASE_URL=http://YOUR_PC_IP:8000`
- Optional components (AGI, Vision, Automation) are loaded if dependencies are available.

## Legacy

All prior duplicate files were moved into `archive/` so nothing is lost.
