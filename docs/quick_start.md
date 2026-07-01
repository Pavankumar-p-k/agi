# 5-Minute Quick Start

> Get JARVIS running on your machine and send your first message.

---

## Prerequisites

| Requirement | Version | Check |
|-------------|---------|-------|
| Python | >= 3.11 | `python --version` |
| Ollama | latest | `ollama --version` |
| Git | any | `git --version` |

## 1. Install

```bash
# Clone
git clone https://github.com/Pavankumar-p-k/agi.git
cd agi

# Install JARVIS
pip install -e .

# Run setup wizard (one-time)
python jarvis.py doctor
```

The `doctor` command checks your system, downloads a default model
(qwen2.5:7b via Ollama), and creates the config file.

## 2. Start Chatting

```bash
python jarvis.py chat
```

Type your first message. JARVIS can:

- Answer questions using local or cloud models
- Write and edit files
- Run shell commands
- Browse the web
- Manage projects

Press `Ctrl+C` or type `/exit` to leave.

## 3. CLI Commands

| Command | What It Does |
|---------|-------------|
| `jarvis chat` | Interactive terminal session |
| `jarvis code "task"` | Autonomous coding (plan → build → test → repair) |
| `jarvis build [path]` | Build project with auto-repair on failure |
| `jarvis run [path]` | Run the project |
| `jarvis understand [path]` | Analyze repository structure |
| `jarvis workspace [path]` | Show workspace status |
| `jarvis doctor` | System diagnostics |
| `jarvis models [action]` | List, test, benchmark, switch models |
| `jarvis settings [action]` | Get/set/reset/export/import configuration |
| `jarvis activity [action]` | View the activity graph (tree, list, watch) |
| `jarvis provider [action]` | List, enable, disable, install providers |
| `jarvis orchestrate "goal"` | Multi-provider orchestration |
| `jarvis advanced` | Server, agents, voice, and other commands |

## 4. Common Tasks

### Use a different model

```bash
jarvis models list          # See available models
jarvis models switch llama3.1:8b
```

### Analyze a project

```bash
jarvis understand /path/to/project --aspect imports
jarvis understand /path/to/project --aspect api
```

### View running activities

```bash
jarvis activity watch    # Live activity feed
jarvis activity tree     # Activity dependency tree
```

### Run the web UI

```bash
jarvis advanced server --port 8000
# Open http://localhost:8000
```

## 5. Next Steps

| To Do | Read |
|-------|------|
| Understand the architecture | [ARCHITECTURE.md](../ARCHITECTURE.md) |
| Add a new provider | [Provider SDK](providers/create_a_provider.md) |
| Configure models and API keys | `jarvis settings` |
| Run benchmarks | `python -m pytest tests/unit/ -q` |
| Contribute | [CONTRIBUTING.md](../CONTRIBUTING.md) |

## 6. Troubleshooting

| Symptom | Fix |
|---------|-----|
| `jarvis: command not found` | Use `python jarvis.py` instead, or ensure `pip install -e .` completed |
| `No module named core.*` | Run `pip install -e .` from the project root |
| Ollama connection refused | Start Ollama: `ollama serve` |
| Model not found | Run `ollama pull qwen2.5:7b` |
| `doctor` shows warnings | Most warnings are informational — look for `ERROR` level messages |
