# JARVIS Workflow Automation

This backend now supports persistent, multi-step automation workflows with:

- Manual triggers
- Interval triggers (every N seconds)
- Daily schedule triggers (`HH:MM` UTC + weekdays)
- One-time triggers (`once_at` ISO datetime)
- Webhook triggers (token-based)
- Step-by-step execution logs
- Run history
- Run cancellation and run-history cleanup
- Retry + timeout controls per step
- Runtime variables + template substitution with `{{vars.name}}`, `{{last.success}}`, etc.

## API Endpoints

- `GET /api/automation/workflows/step-types`
- `GET /api/automation/workflows/trigger-types`
- `GET /api/automation/status`
- `GET /api/automation/workflows`
- `GET /api/automation/workflows/{workflow_id}`
- `POST /api/automation/workflows`
- `PUT /api/automation/workflows/{workflow_id}`
- `DELETE /api/automation/workflows/{workflow_id}`
- `POST /api/automation/workflows/{workflow_id}/clone`
- `POST /api/automation/workflows/{workflow_id}/run`
- `GET /api/automation/workflows/{workflow_id}/runs?limit=20`
- `GET /api/automation/workflow-runs?limit=20`
- `GET /api/automation/workflow-runs/{run_id}`
- `POST /api/automation/workflow-runs/{run_id}/cancel`
- `DELETE /api/automation/workflow-runs?workflow_id={id}`
- `POST /api/automation/workflows/webhook/{token}`
- `POST /api/automation/mobile-data/sync`
- `GET /api/automation/mobile-data/stats`

## Trigger Types

- `manual`: run only when requested by API.
- `interval`: run automatically every `interval_seconds`.
- `daily`: run at `daily_time` (`HH:MM` UTC), optional `weekdays`.
- `once`: run once at `once_at`.
- `webhook`: run when calling `/api/automation/workflows/webhook/{token}`.

## Workflow Payload

```json
{
  "name": "Morning Routine",
  "description": "Open work tools and notify team",
  "enabled": true,
  "trigger": { "type": "interval", "interval_seconds": 1800 },
  "variables": { "target_name": "Rahul" },
  "steps": [
    {
      "name": "Open Chrome",
      "type": "launch_app",
      "params": { "app": "chrome" },
      "retry_count": 1,
      "timeout_seconds": 15
    },
    {
      "name": "Open Calendar",
      "type": "open_url",
      "params": { "url": "https://calendar.google.com" },
      "delay_seconds": 2
    },
    {
      "name": "Notify WhatsApp",
      "type": "whatsapp_send",
      "params": {
        "recipient": "{{vars.target_name}}",
        "message": "Started my morning routine."
      }
    }
  ]
}
```

## Important Notes

- Workflow state is persisted in `backend/data/automation_workflows.json`.
- Runs are stored with per-step outputs and success/failure counters.
- On backend startup, scheduler resumes automatically.
- If a workflow is already running, another run request is rejected.
- Available advanced step types include `shell`, `http_request`, `file_write`, `file_read`, and `set_var`.
- `input_payload` keys are available as both `{{vars.key}}` and `{{vars.payload_key}}` during a run.
- For webhook runs, you can send either:
  - `{"variables": {...}}` (explicit variable injection), or
  - top-level keys like `{"platform":"whatsapp","recipient":"Rahul","incoming_message":"Hi"}`.
- Mobile sync endpoint accepts `contacts`, `call_logs`, `calendar_events`, and `sms_messages` arrays (plus `device_id`) for app-side permission-based data ingestion.

## Windows Voice Assistant (Always Listening)

This project includes a local Windows assistant daemon that listens for a wake phrase and forwards commands to:

- `POST /api/automation/command`

Files:

- `backend/windows_assistant_daemon.ps1`
- `backend/start_windows_assistant.bat`
- `backend/install_windows_assistant_startup.ps1`
- `backend/remove_windows_assistant_startup.ps1`

Run manually:

```powershell
cd backend
.\start_windows_assistant.bat jarvis 127.0.0.1 8000
```

Install auto-start at login:

```powershell
cd backend
powershell -ExecutionPolicy Bypass -File .\install_windows_assistant_startup.ps1 -WakePhrase "jarvis" -ServerHost "127.0.0.1" -ServerPort 8000
```

Remove auto-start task:

```powershell
cd backend
powershell -ExecutionPolicy Bypass -File .\remove_windows_assistant_startup.ps1
```

Notes:

- Requires microphone access and Windows Speech Recognition APIs (`System.Speech`).
- Keep the backend server running on the host/port configured in the script.
- Stop by voice: `jarvis stop listening`.
