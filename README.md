# JARVIS AGI Service (Reduced Tree)

This folder is a standalone AGI service:
- FastAPI backend with autonomous AGI loop
- SQLite AGI memory (`data/jarvis_agi.db`)
- AGI REST routes under `/agi/*`
- Chat hook endpoint at `/api/chat`

## 1) Setup

```powershell
cd C:\Users\Pavan\desktop\apk\agi
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 2) Run on Windows

```powershell
uvicorn main:app --host 0.0.0.0 --port 8000
```

Check:
- `GET http://localhost:8000/health`
- `GET http://localhost:8000/agi/status`

## 3) Android / Flutter connection

`agi_service.dart` now supports base URL override via `AGI_BASE_URL`.

- Android emulator default works with: `http://10.0.2.2:8000`
- Physical device needs your PC LAN IP, for example: `http://192.168.1.100:8000`

Run Flutter with explicit URL:

```powershell
flutter run --dart-define=AGI_BASE_URL=http://192.168.1.100:8000
```

## 4) AGI endpoints

- `GET /agi/status`
- `GET /agi/goals`
- `POST /agi/goal`
- `POST /agi/solve`
- `GET /agi/patterns`
- `GET /agi/predictions`
- `POST /agi/habit`
- `GET /agi/decisions`
- `GET /agi/reflections`
- `POST /agi/config`
- `POST /agi/trigger`

## Notes

- AGI loop interval: 30 seconds.
- Some actions call external JARVIS endpoints (`/api/reminders`, `/api/tts`, etc). If those endpoints are unavailable, fallback behavior is used.
- Local Ollama endpoints are used by solver/reflector when reachable (`http://localhost:11434`).
