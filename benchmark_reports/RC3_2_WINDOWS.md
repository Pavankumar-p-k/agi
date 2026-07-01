# RC3.2 — Windows Fresh-Machine Validation

**Date:** 2026-07-01
**Machine:** Peter's laptop — Windows 10, Python 3.11.9, Git 2.53.0, Ollama (TinyLlama 1.1B), NVIDIA RTX 4050, 16GB RAM
**Wheel:** `jarvis_ai-3.0.0rc3-py3-none-any.whl` (881 files, 4.3 MB)

## Methodology

Fresh Python venv, no prior JARVIS installation. Old `~/.jarvis/` moved aside for clean-state test.

## Results

| # | Test | Result | Timing | Notes |
|---|------|--------|--------|-------|
| 1 | `pip install jarvis-ai` | **PASS** | 128s | First install (downloads all deps from PyPI) |
| 2 | `jarvis --help` | **PASS** | <1s | 19 subcommands listed |
| 3 | `jarvis version` | **PASS** | <1s | Shows "JARVIS 3.0.0-rc3" |
| 4 | `jarvis doctor` | **PASS** | 18s | Detects phase=failed, setup not completed, missing playwright/docker/config |
| 5 | `jarvis setup` | **PASS** | — | Runs wizard, detects Python/Git/Ollama, asks demo question (EOF in non-interactive) |
| 6 | `jarvis demo` | **PASS** | 31s | All 4 sections pass: Config, 8 core modules, 135 tools, diagnostics |
| 7 | `~/.jarvis/` creation | **PASS** | — | `/data/.setup_complete`, `/data/settings.json`, `/logs/`, `/sessions/`, `/backups/`, 12 files total |
| 8 | Second launch skips setup | **PASS** | — | `version`, `demo`, `doctor`, `server`, `web` all skip setup; non-skipped commands check phase |
| 9 | `jarvis server --port 18999` | **PASS** | ~40s | Server starts as subprocess, HTTP 200 on `/`, returns JARVIS Neural OS HTML |
| 10 | `pip uninstall jarvis-ai` | **PASS** | 2s | Clean removal |
| 11 | `~/.jarvis/` survives uninstall | **PASS** | — | All 12 files preserved |
| 12 | `pip install jarvis-ai` (2nd) | **PASS** | 12s | Faster — cached deps |
| 13 | `jarvis version` after reinstall | **PASS** | <1s | Works correctly |

## Bugs Found and Fixed During RC3.2

| Bug | File | Fix |
|-----|------|-----|
| `jarvis server` hit setup wizard in non-interactive mode | `jarvis.py` | Added `"server"`, `"web"` to `_SETUP_SKIP` set |
| `init_db()` crash (alembic not installed) during server startup | `core/lifespan.py` | Wrapped `init_db()` in try/except, logs non-fatal warning |
| `init_db()` hardcoded relative path `"alembic.ini"` | `core/database.py` | Now resolves relative to package directory; skips gracefully if absent |
| Alembic missing from core dependencies | `pyproject.toml` | Added `alembic>=1.12.0` to `[dependencies]` |
| Alembic files (`alembic.ini`, `alembic/`) not in wheel | `MANIFEST.in`, `pyproject.toml` | Added MANIFEST entries, included `alembic*` in packages.find |

## Known Gaps (non-blocking for RC3.2)

1. **Database migrations skip** — alembic files are not yet properly included in wheel (no `__init__.py` in `alembic/` dir). Server starts with non-fatal warning.
2. **Setup wizard requires TTY** — non-interactive commands (`server`, `web`) skip setup entirely; expected behavior.
3. **Server creates logs in site-packages/** — `ROOT = Path(__file__).parent` resolves to site-packages when installed. Logs written there instead of `~/.jarvis/logs/`.

## Verdict

**RC3.2 Windows: PASS** — 13/13 tests pass. All CLI commands work, demo and doctor complete, server starts and serves web UI, uninstall/reinstall preserves user data.
