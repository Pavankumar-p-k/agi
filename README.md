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
- `POST /agi/call/config`
- `POST /agi/call/incoming`
- `POST /agi/style/reply`
- `GET /agi/style/profile`
- `GET /agi/work/summary`

## 5) Device bridge modes

The backend action endpoints now exist:
- `POST /api/messages/send`
- `POST /api/calls/answer_tts`
- `POST /api/tts`
- `GET /api/messages/unread_count`
- `POST /api/messages/incoming`

Configure how actions are executed:

- `JARVIS_BRIDGE_MODE=mock` (default): simulate success for development.
- `JARVIS_BRIDGE_MODE=adb`: run `adb` commands from PC.
- `JARVIS_BRIDGE_MODE=device_api`: forward to phone companion API.

Optional env vars:

- `ANDROID_SERIAL=<adb_serial>`
- `ANDROID_DEVICE_API=http://<phone_ip>:<port>`
- `JARVIS_ADB_AUTO_TAP_SEND=1` (attempt auto key tap to send SMS)
- `JARVIS_BRIDGE_TOKEN=<shared_secret>`

## 6) Phone companion API (for `device_api` mode)

Run this on the phone (Termux/Pydroid):

```bash
export COMPANION_MODE=termux
export JARVIS_BRIDGE_TOKEN=change_this_token
uvicorn device_companion:app --host 0.0.0.0 --port 8090
```

Then on Windows backend:

```powershell
$env:JARVIS_BRIDGE_MODE="device_api"
$env:ANDROID_DEVICE_API="http://<PHONE_IP>:8090"
$env:JARVIS_BRIDGE_TOKEN="change_this_token"
uvicorn main:app --host 0.0.0.0 --port 8000
```

Companion endpoints:
- `POST /bridge/messages/send`
- `POST /bridge/calls/answer_tts`
- `POST /bridge/tts`
- `GET /bridge/messages/unread_count`

## Notes

- AGI loop interval: 30 seconds.
- Some actions call external JARVIS endpoints (`/api/reminders`, `/api/tts`, etc). If those endpoints are unavailable, fallback behavior is used.
- Local Ollama endpoints are used by solver/reflector when reachable (`http://localhost:11434`).
- Android call answering behavior depends on device permissions and OS restrictions; set `COMPANION_CALL_ANSWER_COMMAND` for device-specific handling.

## 7) Android native receiver contract

Added receiver/service spec files in:
- `android_receiver/README.md`
- `android_receiver/JarvisBridgeReceiver.kt`
- `android_receiver/JarvisActionService.kt`
- `android_receiver/AndroidManifest.snippet.xml`

These match bridge broadcast actions used by `adb` mode.
