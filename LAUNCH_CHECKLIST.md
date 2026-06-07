# JARVIS Pre-Launch Checklist

> Final verification steps before releasing to open source. Run each check and mark ✓ when passing.

## 1. Environment & Build

- [ ] **`jarvis doctor` passes all 6 checks** — deps, disk, ports, Docker, git, config
- [ ] **`pip install -e .` succeeds** in a clean venv
- [ ] **`docker compose up --build -d` builds** without errors
- [ ] **No hardcoded secrets** — API keys come from `.env` or env vars only
- [ ] **`grep -r "Bearer dev" --include="*.py" --include="*.html"` returns empty** (was in `static/index.html`, now fixed)

## 2. Core Functionality

- [ ] **`jarvis cli` starts** — prompt_toolkit REPL appears
- [ ] **Chat works** — type a message, get a response (local or cloud LLM)
- [ ] **Streaming works** — WebSocket `/ws/chat_stream` streams tokens
- [ ] **Slash commands work** — `/help`, `/model`, `/clear`, `/session-new`
- [ ] **Web UI serves** — `GET /` returns `static/index.html`
- [ ] **Web UI chat works** — type + submit, get response
- [ ] **Web UI markdown renders** — code blocks, bold, lists display correctly

## 3. Tools & Actions

- [ ] **`edit_file` works** — FIND/REPLACE with backup created
- [ ] **`undo_edit_file` works** — restores from backup
- [ ] **`shell` works** — `pwd` returns correct directory
- [ ] **`semantic_search` works** — queries codebase_indexer
- [ ] **Skills load** — `create_skill` creates hot-reloadable skill
- [ ] **Sub-agents respond** — FORGE, ORACLE, SCRIBE are reachable

## 4. Voice & Channels

- [ ] **Wake word detection** — "hey jarvis" triggers recording
- [ ] **STT → TTS pipeline** — voice input, speech response
- [ ] **Discord channel** — bot responds in server
- [ ] **Telegram channel** — bot responds to messages
- [ ] **WhatsApp sender** — `WhatsAppSender.send()` works

## 5. Diagnostics

- [ ] **3-layer self-healing** — process crash → auto-restart
- [ ] **No silent `except` blocks** — every `except` logs via `logger.warning()`
- [ ] **No `shell=True`** in any `subprocess` call
- [ ] **All tests pass** — `pytest tests/unit/ && pytest tests/integration/`

## 6. Documentation

- [ ] **`README.md`** has quickstart, feature list, architecture diagram links
- [ ] **`JARVIS_USECASES.md`** exists with every working capability
- [ ] **`AGENTS.md`** describes code conventions for AI assistants
- [ ] **`pyproject.toml`** has correct version, dependencies, entry point

## What Was Fixed Before Launch

| Issue | Fix |
|-------|-----|
| `static/index.html` hardcoded `http://localhost:8000` | Changed to `window.location.origin` for auto-detection |
| `static/index.html` hardcoded `Authorization: Bearer dev` | Removed — server accepts requests without auth now |
| `static/index.html` no markdown rendering | Added `renderMarkdown()` function + CSS for code/blocks/lists/links |
| Chat messages displayed raw text | Jarvis messages now pass through markdown renderer |
| No centralized capability catalog | Created `JARVIS_USECASES.md` with every working feature |

## How to Break It (and What We're Doing About It)

| Threat | Mitigation |
|--------|------------|
| User pastes malicious code in chat | Input sanitized by highlightKeywordsChat, agent prompt security filters |
| API keys leaked in `.env` | `.env` in `.gitignore`, vault encrypts at rest |
| Docker sandbox escape | Sandbox has no network, 256m RAM, no volume mounts to host |
| SSRF via web fetch | `core/ssrf.py` blocks private IP ranges, internal hostnames |
| Prompt injection | `core/prompt_security.py` filters system prompt override attempts |
| Model returns harmful content | Cipher agent reviews output; user configures safety level |
| File edit corrupts code | Every edit backed up; `undo_edit_file` recovers by file hash |
| Unlimited agent loops | Max turns enforced; long-running tasks timeout after 120s |
| Channel spam | Rate limiting built into each channel adapter |
| Dependency supply chain | `pip install` from PyPI only; no `--extra-index-url` in defaults |
