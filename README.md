<div align="center">
  <img src="https://capsule-render.vercel.app/api?type=waving&color=0:00c6ff,100:0072ff&height=200&section=header&text=JARVIS&fontSize=80&fontColor=fff&animation=fadeIn" alt="JARVIS">

  <h1>The Privacy-First AI Operating System</h1>

  <p>
    <b>Local-first · Voice-enabled · Self-healing · Tool-extensible</b>
  </p>
  <p>
    Chat, code, research, and automate — all on your hardware, zero data leaks.
  </p>

  <p>
    <a href="LICENSE">
      <img src="https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square" alt="MIT License">
    </a>
    <a href="https://www.python.org/downloads/">
      <img src="https://img.shields.io/badge/python-3.11+-blue.svg?style=flat-square&logo=python" alt="Python 3.11+">
    </a>
    <a href="https://fastapi.tiangolo.com/">
      <img src="https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI">
    </a>
    <a href="https://litellm.ai/">
      <img src="https://img.shields.io/badge/LiteLLM-126%20Providers-8A2BE2?style=flat-square" alt="126+ LLM Providers">
    </a>
    <a href="https://ollama.com/">
      <img src="https://img.shields.io/badge/Ollama-Local%20First-5B5BD6?style=flat-square&logo=ollama" alt="Ollama Local First">
    </a>
    <a href="https://modelcontextprotocol.io/">
      <img src="https://img.shields.io/badge/MCP-Server-7B68EE?style=flat-square" alt="MCP Server">
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
- [Model Coverage](#-model-coverage)
- [Contributing](#-contributing)
- [License](#-license)

---

## 🌟 Why JARVIS?

JARVIS is an all-in-one **AI Operating System** that runs on your machine. Unlike cloud-dependent assistants (Claude Code, ChatGPT, OpenClaw), JARVIS keeps your data **local by default** — no telemetry, no training on your conversations, no forced cloud dependency.

| Capability | JARVIS | Claude Code | OpenClaw | ChatGPT |
|------------|--------|-------------|----------|---------|
| **Local-first** | ✅ Default (Ollama) | ❌ Cloud-only | ❌ Cloud-only | ❌ Cloud-only |
| **Privacy tiers** | ✅ 3-tier (LOCAL/HYBRID/CLOUD) | ❌ None | ❌ None | ❌ None |
| **Persistent shell sessions** | ✅ Stateful, `cd`/`export` recall | ✅ Stateful | ❌ Stateless | ❌ Stateless |
| **Parallel sub-agents** | ✅ Free (unlimited) | ❌ Limited | ❌ Limited | ❌ Limited |
| **LLM providers** | **126** via LiteLLM | ❌ Proprietary | 50 plugins | ❌ Proprietary |
| **Voice pipeline** | ✅ Full local (wake → STT → TTS) | ❌ None | ❌ None | ✅ Cloud-only |
| **Self-healing** | ✅ 3-layer auto-recovery | ❌ None | ❌ Partial | ❌ None |
| **PC control** | ✅ Natural language automation | ❌ None | ❌ None | ❌ None |
| **Docker sandbox** | ✅ One-command, network-isolated | ❌ None | ✅ Partial | ❌ None |
| **Tool extensibility** | ✅ Python, 5 lines per tool | ✅ TypeScript | ✅ TypeScript | ❌ Limited |
| **AST code graph** | ✅ Semantic search + symbol index | ❌ RAG only | ❌ RAG only | ❌ None |
| **Cost** | **Free** | $100/mo | $20/mo + usage | $20/mo + usage |

**JARVIS vs OpenClaw on security:** OpenClaw's plugin ecosystem has reported **512 CVEs** (including CVE-2026-25253, an RCE in the plugin loader). JARVIS addresses this with a hard audit: **8 security-critical fixes** shipped pre-launch (see [Security](#-security)).

---

## 🚀 Quick Start

### Docker (Recommended — 1 Command)

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
# Model Selection (any of 126 LiteLLM providers)
CHAT_MODEL=ollama/llama3.1:8b
CODE_MODEL=openai/gpt-4o
ANALYSIS_MODEL=anthropic/claude-sonnet-4-20250514
REASONING_MODEL=gemini/gemini-2.5-flash

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
        <li><b>Hot</b> — Recent session context (in-memory)</li>
        <li><b>Warm</b> — Semantic vector search</li>
        <li><b>Cold</b> — Durable SQLite storage</li>
      </ul>
    </td>
  </tr>
  <tr>
    <td width="50%">
      <h3>🎙️ Full Voice Pipeline</h3>
      <p>End-to-end local, zero cloud dependency:</p>
      <ul>
        <li><b>Wake word:</b> Porcupine (local)</li>
        <li><b>STT:</b> Faster-Whisper (local)</li>
        <li><b>TTS:</b> Kokoro (local)</li>
      </ul>
    </td>
    <td width="50%">
      <h3>🤖 10 Parallel Sub-Agents</h3>
      <p>Specialized agents for every task — runs in parallel, not serial:</p>
      <ul>
        <li><b>NEXUS</b> — Integration & automation</li>
        <li><b>FORGE</b> — Code generation & review</li>
        <li><b>ORACLE</b> — Chain-of-thought planning</li>
        <li><b>PHANTOM</b> — Analysis & summarization</li>
        <li><b>CIPHER</b> — Security & governance</li>
        <li><b>HERALD</b> — Social & communication</li>
        <li><b>SCRIBE</b> — Quality & grading</li>
        <li><b>ATLAS</b> — Deep research & multi-hop search</li>
        <li><b>SENTINEL</b> — Monitoring & alerting</li>
        <li><b>MAESTRO</b> — Orchestration & planning</li>
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
        <li>Browser automation with Playwright</li>
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
        <li>Prefix any <code>shell</code> command with <code>sandbox:</code></li>
      </ul>
    </td>
    <td width="50%">
      <h3>🧩 Hot-Reloadable Skills</h3>
      <p>Agent-writable, trigger-based skills that load without restart:</p>
      <ul>
        <li><code>create_skill</code> tool generates <code>.md</code> + <code>.py</code> in one call</li>
        <li>Trigger phrases route directly to handler (bypass LLM)</li>
        <li>Cache invalidated automatically on creation</li>
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
        <li>Essential for interactive CLI workflows</li>
      </ul>
    </td>
    <td width="50%">
      <h3>📊 AST Code Graph</h3>
      <p>Semantic code search with hybrid BM25 + vector + symbol regex:</p>
      <ul>
        <li><code>semantic_search</code> tool for natural-language queries</li>
        <li><code>refactor</code> tool for multi-file transformations</li>
        <li>Symbol-level indexing for fast navigation</li>
        <li>Understands Python, JS, TS, Rust, Go, and more</li>
      </ul>
    </td>
  </tr>
  <tr>
    <td width="50%">
      <h3>🔌 MCP Server Support</h3>
      <p>Model Context Protocol — the 2026 standard for AI tool interoperability:</p>
      <ul>
        <li>Built-in MCP server at <code>mcp/server.py</code> with tool/resource registration</li>
        <li>Connect any <code>mcp_server.json</code> from the ecosystem</li>
        <li>Email MCP server for IMAP/SMTP integration</li>
        <li>Bridge to external MCP hosts via <code>manage_mcp</code> tool</li>
        <li>Event bridge channels MCP notifications into agent loop</li>
      </ul>
    </td>
    <td width="50%">
      <h3>📊 AST Code Graph</h3>
      <p>Semantic code search with hybrid BM25 + vector + symbol regex:</p>
      <ul>
        <li><code>semantic_search</code> tool for natural-language queries</li>
        <li><code>refactor</code> tool for multi-file transformations</li>
        <li>Symbol-level indexing for fast navigation</li>
        <li>Understands Python, JS, TS, Rust, Go, and more</li>
      </ul>
    </td>
  </tr>
</table>

---

## 🏗️ Architecture

```
jarvis/
├── core/                   # FastAPI brain, config, auth, diagnostics
│   ├── agent_loop.py       # Main LLM orchestration loop
│   ├── tools/              # All tools (edit, shell, search, skills, etc.)
│   │   ├── execution.py    # Tool dispatcher + MCP bridge
│   │   ├── persistent_shell.py  # Stateful shell sessions
│   │   ├── skill_tools.py  # Skill management + create_skill
│   │   ├── settings_tools.py    # Runtime settings
│   │   ├── admin_tools.py       # Endpoints, MCP, webhooks
│   │   └── cookbook_tools.py    # Model serving, image gen, research
│   ├── config_schema.py    # Pydantic-validated config
│   ├── prompt_security.py  # Content integrity verification
│   ├── api_key_vault.py    # Encrypted key storage
│   ├── ssrf.py             # DNS-based SSRF protection
│   └── diagnostics.py      # Health checks (disk/port/docker/git)
├── brain/                  # Cognitive patterns, reasoning
├── memory/                 # Tiered memory, vector storage
├── ai_os/                  # Docker sandbox, planner stubs
├── channels/               # Discord, Telegram, Slack, Email, IRC
├── assistant/              # Voice pipeline (wake → STT → TTS)
├── pc_agent/               # Computer control & automation
├── governance/             # Security, privacy, validation
├── skills/                 # Hot-reloadable trigger skills (.md + .py)
├── media/                  # Media player with subprocess fallback
├── tests/                  # Unit + integration tests (no external deps)
├── docker-compose.yml      # Docker stack definition
└── Dockerfile              # Production container
```

| Directory | Purpose |
|-----------|---------|
| `core/` | Everything you need to understand JARVIS: agent loop, tools, config, security, diagnostics |
| `core/tools/` | All AI-callable tools: edit files, run shell, search code, manage skills |
| `skills/` | User-created trigger skills — created dynamically via `create_skill` tool |
| `channels/` | Communication channels (Discord, Telegram, Slack, Email, IRC, Matrix) |
| `tests/` | Tests that mock external services — run without network |

---

## 🔒 Security

Pre-launch security audit — **8 critical fixes** shipped before v1.0:

| Issue | Fix | File |
|-------|-----|------|
| Hardcoded API keys in source | Replaced with `YOUR_*` placeholders | `google-services.json` (3 locations) |
| `shell=True` subprocess calls | Converted to `shell=False` with list args | `pc_automation.py`, `computer_agent.py`, `spotify/main.py` |
| `os.system()` command injection | Migrated to `subprocess.run()` | `daemon/jarvis_service.py` |
| 82 silent `except: pass` blocks | Changed to `logger.warning()` with exception context | 30 files across `core/`, `daemon/`, `media/` |
| SSRF via DNS rebinding | `resolve_and_check()` prevents internal network attacks | `core/ssrf.py` |
| Prompt injection detection | `PromptSecurity` classifier identifies 5 attack types | `core/prompt_security.py` |
| API key vault with audit | Key rotation + usage tracking + encrypted storage | `core/api_key_vault.py` |
| Docker sandbox isolation | `network_disabled=True`, `read_only=True`, 256m mem limit | `ai_os/docker_sandbox.py` |

**No hardcoded secrets** in any source file. All API keys come from environment variables or the key vault.

---

## 📊 Model Coverage

JARVIS supports **126+ LLM providers** through LiteLLM — more than double OpenClaw's 50.

| Feature | JARVIS | OpenClaw |
|---------|--------|----------|
| **Provider count** | **126** | 50 |
| **Add a provider** | 1 line in `.env` | TypeScript plugin (200+ LOC) |
| **Use any model ID** | `CHAT_MODEL=claude-4-opus` | Must edit TypeScript |
| **Maintenance** | Zero (LiteLLM handles all) | Must maintain 50 extensions |

Just set a `*_API_KEY` in `.env` and any of 126 providers work:

```env
CHAT_MODEL=openai/gpt-4o
CODE_MODEL=anthropic/claude-sonnet-4-20250514
ANALYSIS_MODEL=gemini/gemini-2.5-flash
REASONING_MODEL=deepseek/deepseek-reasoner
VISION_MODEL=openai/gpt-4o
```

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

[MIT](LICENSE) — free for personal and commercial use.

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
