# JARVIS Ghost Dependency Audit

| Dependency | Severity | Source of Reference | Problem |
| :--- | :--- | :--- | :--- |
| `jarvis_os` | **CRITICAL** | `api/os_routes.py`, `ai_os/orchestrator.py`, `cli_requests.py` | Module is referenced everywhere but doesn't exist. Causes 503 errors and TUI failure. |
| `api/routes/` | **MEDIUM** | `core/main.py`, `THE_TRUTH_ABOUT_JARVIS.md` | Some files might still attempt to import from this deleted directory. |
| `instructor` | **LOW** | `core/intent_router.py` | Optional but heavily used; if missing, intent routing falls back to regex. |
| `composio` | **LOW** | `core/main.py` | Referenced but usage is guarded by `try/except`. |

## Root Cause
The "Release Cleanup" attempt partially deleted modules like `jarvis_os` but failed to update the orchestrators and API routes that depended on them.
