# JARVIS Local Autonomy Control Plane

This upgrade adds an OpenClaw-style local-first control plane on top of the existing JARVIS repository without removing or moving legacy modules.

## What Was Added

- `backend/jarvis_os/control_plane/access_manager.py`
  - Scoped host access profiles
  - Approval tickets
  - Local audit trail
- `backend/jarvis_os/control_plane/mobile_sync.py`
  - Android device discovery via `adb`
  - Local sync queue metadata
- `backend/jarvis_os/control_plane/scheduler.py`
  - Heartbeat scheduler for recurring autonomous tasks
- `backend/jarvis_os/control_plane/gateway.py`
  - Local channel gateway for CLI, desktop, and messaging connectors
- `backend/jarvis_os/browser/controller.py`
  - Persistent browser session
  - Playwright-backed DOM automation when installed
  - Truthful fallback mode when not installed

## Runtime Integration

These services are now initialized by the AI OS runtime and included in:

- `/os/status`
- `/os/control/status`
- `/os/control/access`
- `/os/control/mobile`
- `/os/control/scheduler`
- `/os/control/channels`

They are also available through new tools:

- `access`
- `mobile`
- `scheduler`
- `gateway`

## Security Model

The agent is not given silent unrestricted host access.

Instead it now uses explicit profiles:

- `workspace`
- `desktop`
- `mobile_sync`
- `personal_assistant`

Higher-risk actions can create approval tickets, which can then be approved or rejected through the control API.

## What This Enables

- Local-first autonomous scheduling
- Mobile pairing and sync metadata
- Multi-channel control surface scaffolding
- Human-in-the-loop approvals
- Better separation between reasoning, permissions, and execution
- Background heartbeat jobs that actually execute through the supervisor
- Messaging send planning through the gateway
- Browser flows that can progress from open/search into DOM actions when Playwright is available

## Current Boundaries

- Messaging bots like Telegram/Discord/Slack are scaffolded at the gateway layer, not fully implemented connectors yet
- Mobile sync currently manages discovery and queue state; full file/message sync needs app-specific executors
- Heartbeat jobs enqueue autonomous work; they do not yet provide a full cron expression engine
- Full “whole laptop” control is intentionally not granted by default

## Browser Upgrade Path

- If `playwright` is installed, JARVIS can keep a persistent Chromium session and attempt DOM actions like:
  - login
  - click text
  - add to cart
- Without Playwright, JARVIS stays in truthful fallback mode:
  - open site
  - navigate
  - search directly on supported sites
  - stop at DOM-only actions with an explicit limitation

## Approval Model

- Safe actions like opening a site or running a read-only workspace query can proceed.
- Sensitive actions such as:
  - shell execution
  - device control
  - browser login
  - add-to-cart / checkout
  - destructive automation
  create approval tickets before execution.

## Recommended Commands

```powershell
jarvis restart --with-models
jarvis status
jarvis cli
```

Then inspect:

```powershell
curl http://127.0.0.1:8000/os/control/status
curl http://127.0.0.1:8000/os/control/mobile
curl http://127.0.0.1:8000/os/control/scheduler
```
