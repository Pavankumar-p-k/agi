<div align="center">
  <img src="https://capsule-render.vercel.app/api?type=waving&color=0:00c6ff,100:0072ff&height=200&section=header&text=JARVIS&fontSize=80&fontColor=fff&animation=fadeIn" alt="JARVIS">

  <h1>The Privacy-First AI Assistant</h1>

  <p>
    <b>Local-first · Voice-enabled · Self-healing · Tool-extensible</b>
  </p>
  <p>
    Chat, code, research, and automate — all on your hardware, zero data leaks.
  </p>

  <p>
    <a href="LICENSE">
      <img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg?style=flat-square" alt="Apache 2.0 License">
    </a>
    <a href="https://www.python.org/downloads/">
      <img src="https://img.shields.io/badge/python-3.11+-blue.svg?style=flat-square&logo=python" alt="Python 3.11+">
    </a>
    <a href="https://fastapi.tiangolo.com/">
      <img src="https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI">
    </a>
    <a href="https://ollama.com/">
      <img src="https://img.shields.io/badge/Ollama-Local%20First-5B5BD6?style=flat-square&logo=ollama" alt="Ollama Local First">
    </a>
    <a href="https://www.docker.com/">
      <img src="https://img.shields.io/badge/Docker-Ready-2496ED?style=flat-square&logo=docker" alt="Docker Ready">
    </a>
    <br>
    <a href="#-quick-start">
      <img src="https://img.shields.io/badge/Quick_Start-2_Commands-00C853?style=flat-square" alt="Quick Start">
    </a>
    <a href="#-features">
      <img src="https://img.shields.io/badge/Features-Overview-FF6F00?style=flat-square" alt="Features">
    </a>
    <a href="#-architecture">
      <img src="https://img.shields.io/badge/Architecture-Modular-1A237E?style=flat-square" alt="Architecture">
    </a>
  </p>
</div>

---

## Table of Contents

- [Why JARVIS?](#-why-jarvis)
- [Quick Start](#-quick-start)
- [Features](#-features)
- [Architecture](#-architecture)
- [Security](#-security)
- [Contributing](#-contributing)
- [License](#-license)

---

## 🌟 Why JARVIS?

JARVIS is an all-in-one **AI assistant** that runs on your machine. Unlike cloud-dependent assistants, JARVIS keeps your data **local by default** — no telemetry, no training on your conversations, no forced cloud dependency.

| Capability | JARVIS | Claude Code | ChatGPT |
|------------|--------|-------------|---------|
| **Local-first** | ✅ Default (Ollama) | ❌ Cloud-only | ❌ Cloud-only |
| **Privacy tiers** | ✅ 3-tier (LOCAL/HYBRID/CLOUD) | ❌ None | ❌ None |
| **Persistent shell sessions** | ✅ Stateful, `cd`/`export` recall | ✅ Stateful | ❌ Stateless |
| **Agent chaining** | ✅ Sequential agent execution | ✅ | ❌ |
| **Voice pipeline** | ✅ Full local (wake → STT → TTS) | ❌ None | ✅ Cloud-only |
| **Self-healing** | ✅ 3-layer auto-recovery | ❌ None | ❌ None |
| **PC control** | ✅ Natural language automation | ❌ None | ❌ None |
| **Docker sandbox** | ✅ One-command, network-isolated | ❌ None | ❌ None |
| **Tool extensibility** | ✅ Python, 5 lines per tool | ✅ TypeScript | ❌ Limited |
| **Cost** | **Free** | $100/mo | $20/mo + usage |

---

## 🚀 Quick Start

### Docker (Recommended)

```bash
git clone https://github.com/Pavankumar-p-k/agi.git
cd agi
cp .env.example .env
docker compose up --build -d
```

Open [http://localhost:8000](http://localhost:8000) and start talking to JARVIS.

### Native Install

```bash
# Prerequisites: Python 3.11+, Ollama running locally
git clone https://github.com/Pavankumar-p-k/agi.git
cd agi
pip install -e .
python jarvis.py setup   # Run the setup wizard
python jarvis.py         # Launch the interactive CLI
```

### Configuration

```env
# Model Selection
CHAT_MODEL=ollama/llama3.1:8b
CODE_MODEL=ollama/qwen2.5-coder:3b
REASONING_MODEL=ollama/deepseek-r1:1.5b

# API Keys (only if using cloud models)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-...
```

---

## 🧠 Features

<table>
  <tr>
    <td width="50%">
      <h3>🔒 Privacy-First Architecture</h3>
      <p>3-tier routing engine classifies every query:</p>
      <ul>
        <li><b>LOCAL</b> — Sensitive data stays on-device via Ollama</li>
        <li><b>HYBRID</b> — PII stripped before reaching cloud models</li>
        <li><b>CLOUD</b> — Generic queries use high-performance APIs</li>
      </ul>
    </td>
    <td width="50%">
      <h3>🧠 Persistent Tiered Memory</h3>
      <p>Multi-tier recall with vector embeddings:</p>
      <ul>
        <li><b>Vector</b> — Semantic search (ChromaDB)</li>
        <li><b>Graph</b> — Knowledge graph relationships</li>
        <li><b>Conversation</b> — Recent session context</li>
        <li><b>mem0</b> — Long-term memory integration</li>
      </ul>
    </td>
  </tr>
  <tr>
    <td width="50%">
      <h3>🎙️ Full Voice Pipeline</h3>
      <p>End-to-end local, zero cloud dependency:</p>
      <ul>
        <li><b>Wake word:</b> Porcupine + Silero VAD (local)</li>
        <li><b>STT:</b> Faster-Whisper (local)</li>
        <li><b>TTS:</b> Edge TTS + pyttsx3 (local)</li>
      </ul>
    </td>
    <td width="50%">
      <h3>🤖 Specialized Agents</h3>
      <p>18 registered agents for different tasks:</p>
      <ul>
        <li>Manager, Code, Research, Memory</li>
        <li>Planner, Reasoning, Voice, Skill</li>
        <li>Tool, Chat, Assistant, Writer</li>
        <li>Editor, Translator, Analyst, Critic</li>
        <li>Teacher, Voice</li>
      </ul>
    </td>
  </tr>
  <tr>
    <td width="50%">
      <h3>🖥️ PC Control</h3>
      <p>Natural language computer automation:</p>
      <ul>
        <li>Open/manage applications</li>
        <li>File system operations</li>
        <li>Keyboard & mouse control</li>
      </ul>
    </td>
    <td width="50%">
      <h3>🔄 Self-Healing</h3>
      <p>3-layer autonomous recovery:</p>
      <ul>
        <li><b>Detection</b> — Health monitoring & diagnostics</li>
        <li><b>Diagnosis</b> — Root cause analysis</li>
        <li><b>Recovery</b> — Automatic service restart</li>
      </ul>
    </td>
  </tr>
  <tr>
    <td width="50%">
      <h3>🐳 Docker Sandbox</h3>
      <p>Isolated code execution with network-disabled containers:</p>
      <ul>
        <li>Run any command in sandboxed environment</li>
        <li>Memory-limited, read-only by default</li>
        <li>Automatic container cleanup</li>
      </ul>
    </td>
    <td width="50%">
      <h3>🧩 Hot-Reloadable Skills</h3>
      <p>Agent-writable, trigger-based skills that load without restart:</p>
      <ul>
        <li><code>create_skill</code> tool generates <code>.md</code> + <code>.py</code> in one call</li>
        <li>Trigger phrases route directly to handler (bypass LLM)</li>
        <li>No server restart required</li>
      </ul>
    </td>
  </tr>
  <tr>
    <td width="50%">
      <h3>🔧 Persistent Shell Tool</h3>
      <p>Stateful shell sessions that preserve <code>cd</code>, <code>export</code>, and virtualenvs:</p>
      <ul>
        <li>Per-conversation shell with 5-min idle GC</li>
        <li>Works on Windows (cmd.exe) and Unix (/bin/sh)</li>
        <li>Docker sandbox escape hatch for unsafe commands</li>
      </ul>
    </td>
    <td width="50%">
      <h3>🔌 MCP Server Support</h3>
      <p>Model Context Protocol for AI tool interoperability:</p>
      <ul>
        <li>Built-in MCP server at <code>mcp/server.py</code></li>
        <li>Connect external MCP servers</li>
        <li>Bridge external tools into the agent loop</li>
      </ul>
    </td>
  </tr>
  <tr>
    <td width="50%">
      <h3>📱 Multi-Channel</h3>
      <p>Connect JARVIS to your communication platforms:</p>
      <ul>
        <li>Discord, Telegram, Slack</li>
        <li>Email (IMAP/SMTP), IRC, Matrix</li>
      </ul>
    </td>
    <td width="50%">
      <h3>⚙️ Configurable Settings</h3>
      <p>Live-editable configuration from Web UI:</p>
      <ul>
        <li>62 settings across all subsystems</li>
        <li>Model selection and groups</li>
        <li>Voice, memory, tool configuration</li>
        <li>Persisted to <code>data/settings.json</code></li>
      </ul>
    </td>
  </tr>
</table>

---

## 🏗️ Architecture

```
jarvis/
├── core/                   # FastAPI app, agent loop, tools, config, security
│   ├── agent_loop.py       # Main LLM orchestration loop
│   ├── tools/              # All tools (shell, skills, settings, etc.)
│   │   ├── execution.py    # Tool dispatcher
│   │   ├── persistent_shell.py  # Stateful shell sessions
│   │   ├── skill_tools.py  # Skill management
│   │   ├── settings_tools.py    # Runtime settings
│   │   └── admin_tools.py       # Endpoints, MCP, webhooks
│   ├── config_registry.py  # 62-entry config system with live editing
│   ├── routes/             # API routes (chat, voice, settings, agents, etc.)
│   ├── prompt_security.py  # Content integrity verification
│   ├── api_key_vault.py    # Encrypted key storage
│   ├── ssrf.py             # DNS-based SSRF protection
│   ├── self_healing.py     # Auto-recovery monitors
│   └── diagnostics.py      # Health checks (disk/port/docker/git)
├── brain/                  # Reasoning engine, planning, execution context
├── memory/                 # Vector memory, graph memory, mem0 adapter
├── assistant/              # Voice pipeline (wake → STT → TTS)
│   └── providers/          # STT/TTS provider implementations
├── ai_os/                  # Docker sandbox, file operations, process management
├── api/                    # Additional API routes (OS, memory, settings, etc.)
├── channels/               # Multi-channel (Discord, Telegram, Slack, Email, IRC, Matrix)
├── pc_agent/               # Computer control & automation
├── governance/             # Security validation, runtime governance
├── mcp/                    # MCP server implementation
├── skills/                 # Hot-reloadable trigger skills (.md + .py)
├── static/                 # Web UI (chat, settings)
├── tests/                  # Unit + integration tests
├── data/                   # Runtime data (settings.json, etc.)
├── media/                  # Media player
├── docker-compose.yml      # Docker stack definition
└── Dockerfile              # Production container
```

| Directory | Purpose |
|-----------|---------|
| `core/` | Everything you need to understand JARVIS: agent loop, tools, config, security, diagnostics |
| `core/tools/` | All AI-callable tools: edit files, run shell, manage skills |
| `core/routes/` | API route handlers (chat, voice, settings, agents, WebSocket) |
| `skills/` | User-created trigger skills — created dynamically via `create_skill` tool |
| `channels/` | Communication channels (Discord, Telegram, Slack, Email, IRC, Matrix) |
| `ai_os/` | Docker sandbox, file ops, process management |
| `tests/` | Tests that mock external services — run without network |

---

## 🔒 Security

Pre-launch security audit — **critical fixes shipped before v1.0**:

| Issue | Fix | File |
|-------|-----|------|
| `shell=True` subprocess calls | Converted to `shell=False` with list args | Multiple files |
| `os.system()` command injection | Migrated to `subprocess.run()` | Multiple files |
| Silent `except: pass` blocks | Changed to `logger.warning()` with exception context | 30+ files |
| SSRF via DNS rebinding | `resolve_and_check()` prevents internal network attacks | `core/ssrf.py` |
| Prompt injection detection | Classifier identifies 5 attack types | `core/prompt_security.py` |
| API key vault with audit | Key rotation + usage tracking + encrypted storage | `core/api_key_vault.py` |
| Docker sandbox isolation | `network_disabled=True`, `read_only=True`, mem limit | `ai_os/docker_sandbox.py` |

**No hardcoded secrets** in any source file. All API keys come from environment variables or the key vault.

---

## 🤝 Contributing

We welcome contributions! The project is in active development.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing`)
5. Open a Pull Request

See our [issues page](https://github.com/Pavankumar-p-k/agi/issues) for good first issues.

---

## 📄 License

[Apache 2.0](LICENSE) — free for personal and commercial use.

---

<div align="center">
  <p>Built for a private AI future</p>
  <p>
    <a href="https://github.com/Pavankumar-p-k/agi/issues">Report Bug</a>
    ·
    <a href="https://github.com/Pavankumar-p-k/agi/issues">Request Feature</a>
    ·
    <a href="https://github.com/Pavankumar-p-k/agi">GitHub</a>
  </p>
</div>
