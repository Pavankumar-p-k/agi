# Deployment Guide — JARVIS

## Prerequisites

- Python 3.11+
- Ollama (for local models)
- Docker (optional, for sandboxed execution)
- Android SDK + Gradle (optional, for Android builder)

## Installation

```bash
# Clone and install
git clone https://github.com/jarvis/jarvis.git
cd jarvis
pip install -r requirements.txt

# Setup wizard
python jarvis.py setup
```

## Quick Start

```bash
# Start the interactive CLI
python jarvis.py cli

# Start the server
python jarvis.py server

# Launch the TUI
python jarvis.py tui

# Run diagnostics
python jarvis.py doctor

# Check status
python jarvis.py status
```

## Configuration

Configuration is loaded from (in priority order):
1. In-memory overrides
2. Environment variables
3. `data/settings.json`
4. `config.yaml`
5. Code defaults

### Key Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `OLLAMA_URL` | Ollama base URL | `http://localhost:11434` |
| `OPENAI_API_KEY` | OpenAI API key | — |
| `ANTHROPIC_API_KEY` | Anthropic API key | — |
| `GEMINI_API_KEY` | Google Gemini API key | — |
| `GROQ_API_KEY` | Groq API key | — |
| `OPENROUTER_API_KEY` | OpenRouter API key | — |
| `CHAT_MODEL` | Default chat model | `ollama/qwen2.5-coder:3b` |
| `VOICE_TTS_PROVIDER` | TTS provider | `edge-tts` |
| `VOICE_STT_PROVIDER` | STT provider | `faster-whisper` |

### config.yaml

```yaml
plugins:
  hot_reload:
    enabled: true
    poll_interval: 2.0
  directories:
    - plugins/
    - core/plugins/
  config_dir: data/plugin_configs
```

## Model Configuration

Default task profiles can be overridden in config or at runtime:

```bash
# Via CLI
jarvis settings set task_profile.coding primary=openai
jarvis settings set task_profile.coding fallback=anthropic

# Via slash command (in CLI chat)
/models switch coding openai
```

## Running Background Services

```bash
# Full stack (server + GUI)
python jarvis.py up

# Server only
python jarvis.py server --host 0.0.0.0 --port 8000

# GUI only
python jarvis.py gui

# Web UI
python jarvis.py web
```

## Android Builder

```bash
# Build an Android app
python jarvis.py build "Create a calculator app"
```

The Android builder uses deterministic repair modules in `brain/repair_modules/`:
- `fix_imports` — Missing imports
- `fix_manifest` — AndroidManifest.xml
- `fix_layouts` — XML layouts
- `fix_resources` — Drawables, colors, strings
- `fix_gradle` — Build files
- `fix_dependencies` — Gradle dependencies
- `fix_class_names` — Class/file name mismatches
- `fix_package_names` — Package declarations

## Docker

```bash
docker-compose up -d
```

## Health Checks

```bash
# Comprehensive diagnostics
python jarvis.py doctor

# Feature audit
python jarvis.py doctor --json

# Environment status
python jarvis.py status
```

## Production Checklist

- [ ] Ollama running with desired models
- [ ] API keys configured (as needed)
- [ ] `python jarvis.py doctor` passes
- [ ] Model routing works (`jarvis models list`)
- [ ] Cloud/local switching works
- [ ] Plugin creation works
- [ ] Voice stack tested
- [ ] All tests pass: `pytest tests/unit/`
- [ ] Feature audit: `python jarvis.py doctor --json`
