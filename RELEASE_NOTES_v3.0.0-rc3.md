# JARVIS v3.0.0-rc3 — Release Candidate 3.1 (Packaging)

## What's New

This is a pure release-engineering milestone. Zero new features.

### `pip install jarvis-ai`

The entire application now installs with a single command:

```
pip install jarvis-ai
jarvis
```

### CLI Entry Points

| Command | Description |
|---------|-------------|
| `jarvis --help` | Full help with all commands |
| `jarvis version` | Version info |
| `jarvis setup` | Interactive setup wizard |
| `jarvis demo` | System smoke test |
| `jarvis doctor` | Full diagnostics |
| `jarvis chat` | Interactive terminal |
| `jarvis web` | Launch web UI |
| `jarvis server` | FastAPI backend |
| `jarvis tui` | Textual TUI frontend |
| `jarvis code` | Autonomous coding |
| `jarvis build` | Build with auto-repair |
| `jarvis run` | Run project |

### First-Run Flow

1. `jarvis` (or any command) detects first run
2. Welcome Wizard walks through: Python ✓ → Ollama → Model download → Playwright → API keys → Demo
3. Done. Home page shows.

### Configuration

Auto-created at `~/.jarvis/`:

```
~/.jarvis/
  config.json       CLI configuration
  settings.json     Application settings
  data/             Runtime data
    .setup_complete Setup state
  logs/             Application logs
  workspace/        Workspace data
  memory/           Knowledge store
  artifacts/        Workflow artifacts
```

### Dependencies

**Required** (installed automatically):
`fastapi`, `uvicorn`, `sqlalchemy`, `pydantic`, `httpx`, `prompt_toolkit`, `textual`, `rich`, `pillow`, `psutil`, `websockets`, `aiohttp`, `anthropic`, `numpy`, `opencv-python-headless`, and others.

**Optional** (install on demand):
- `pip install jarvis-ai[browser]` — Playwright for browser automation
- `pip install jarvis-ai[voice]` — Voice input support
- `pip install jarvis-ai[vision]` — Face recognition
- `pip install jarvis-ai[firebase]` — Firebase auth

## Upgrade Notes

- `pip install --upgrade jarvis-ai` updates binaries only
- `~/.jarvis/` (config, memory, workspace) is never touched
- All user data survives upgrades

## Known Limitations

- The full Next.js web UI (`jarvis web`) requires a separate build from source for now
- The basic static web UI (`static/index.html`) ships with the package
- Skills library is not included in the wheel (available at source repo)
- Flutter GUI (`jarvis gui`) requires the source repository

## Release Checklist

| Check | Status |
|-------|--------|
| Clean install succeeds | ✅ |
| `jarvis` launches | ✅ |
| Setup Wizard starts automatically | ✅ |
| Demo runs | ✅ |
| `jarvis version` displays version | ✅ |
| `jarvis doctor` runs diagnostics | ✅ |
| CLI commands have proper help | ✅ |
| Optional dependency groups defined | ✅ |
| Package metadata correct | ✅ |
| Wheel includes static assets | ✅ |
| ~/.jarvis/ created on first run | ✅ |
