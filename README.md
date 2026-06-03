<div align="center">
  <img src="https://capsule-render.vercel.app/api?type=waving&color=0:00c6ff,100:0072ff&height=200&section=header&text=JARVIS&fontSize=80&fontColor=fff&animation=fadeIn" alt="JARVIS">

  <h1>The Privacy-First AI Operating System</h1>

  <p>
    <b>Local-first · Voice-enabled · Self-healing · Plugin extensible</b>
  </p>

  <p>
    <a href="https://github.com/Pavankumar-p-k/agi/blob/main/LICENSE">
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
    <a href="#-plugin-sdk">
      <img src="https://img.shields.io/badge/Plugin_SDK-Python-3776AB?style=flat-square&logo=python" alt="Plugin SDK">
    </a>
  </p>

  <br>

  <table>
    <tr>
      <td align="center">
        <img src="https://raw.githubusercontent.com/Pavankumar-p-k/agi/main/docs/demo.gif" alt="Demo" width="600">
        <br>
        <i>JARVIS in action — voice, code, research, and PC control</i>
      </td>
    </tr>
  </table>
</div>

---

## Table of Contents

- [Why JARVIS?](#-why-jarvis)
- [Quick Start](#-quick-start)
- [Features](#-features)
- [Architecture](#-architecture)
- [Model Coverage](#-model-coverage)
- [Plugin SDK](#-plugin-sdk)
- [Contributing](#-contributing)
- [License](#-license)

---

## 🌟 Why JARVIS?

JARVIS is an all-in-one **AI Operating System** for your personal machine. Unlike cloud-dependent AI assistants, JARVIS is built **local-first** — your data stays on your hardware unless you explicitly choose otherwise.

| Capability | JARVIS | ChatGPT | OpenClaw |
|------------|--------|---------|----------|
| **Local-first** | ✅ Default (Ollama) | ❌ Cloud-only | ❌ Cloud-only |
| **Privacy tiers** | ✅ 3-tier routing + PII stripping | ❌ None | ❌ None |
| **Persistent memory** | ✅ Vector + semantic recall | ❌ Session-only | ❌ Session-only |
| **Voice pipeline** | ✅ Full local (wake → STT → TTS) | ✅ Cloud-only | ❌ None |
| **LLM providers** | ✅ **126** via LiteLLM | ❌ Proprietary | ✅ 50 plugins |
| **Plugin SDK** | ✅ Python, 5 lines with `@hook` | ❌ Limited | ✅ TypeScript |
| **Self-healing** | ✅ 3-layer auto-recovery | ❌ None | ❌ None |
| **PC control** | ✅ Natural language automation | ❌ None | ❌ None |
| **Docker-ready** | ✅ One-command deploy | ❌ Not applicable | ❌ Complex |

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
python jarvis.py
```

### Configuration

All configuration is done through `.env`. Copy the template and customize:

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
      <p>3-tier recall with vector embeddings:</p>
      <ul>
        <li><b>Hot</b> — Recent session context (in-memory)</li>
        <li><b>Warm</b> — Mem0 + Qdrant semantic search</li>
        <li><b>Cold</b> — SQLite with nomic-embed-text vectors</li>
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
      <h3>🤖 10 Sub-Agents</h3>
      <p>Specialized agents for every task:</p>
      <ul>
        <li><b>FORGE</b> — Code generation & review</li>
        <li><b>ATLAS</b> — Deep research & multi-hop search</li>
        <li><b>ORACLE</b> — Chain-of-thought planning</li>
        <li><b>NEXUS</b> — Integration & automation</li>
        <li><b>CIPHER</b> — Analysis & summarization</li>
        <li><b>ECHO</b> — Social & communication</li>
        <li><b>CRUX</b> — Quality & grading</li>
        <li><b>LENS</b> — Vision & image understanding</li>
        <li><b>AEGIS</b> — Security & governance</li>
        <li><b>NOVA</b> — Creative generation</li>
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
      <h3>🌐 6 Communication Channels</h3>
      <ul>
        <li>Discord, Telegram, Slack</li>
        <li>Email (IMAP), IRC, Matrix</li>
        <li>MCP Server (Model Context Protocol)</li>
      </ul>
    </td>
    <td width="50%">
      <h3>📦 Plugin SDK</h3>
      <p>Python-native plugin system:</p>
      <ul>
        <li><code>@hook(name)</code> decorator — 5 lines to extend</li>
        <li>7 lifecycle hooks (voice, memory, channels, etc.)</li>
        <li>PyPI distribution via <code>entry_points</code></li>
        <li>Dashboard plugin manager</li>
      </ul>
    </td>
  </tr>
</table>

---

## 🏗️ Architecture

```
jarvis/
├── core/           # FastAPI brain, LLM router, config, auth
│   ├── llm_router.py     # LiteLLM Router — 126+ providers
│   ├── model_router.py   # Role-to-model mapping
│   ├── main.py           # FastAPI application
│   ├── plugins/          # Plugin registry & loader
│   └── sub_agents/       # 10 specialized agents
├── brain/          # Cognitive patterns, reasoning, epistemic tagging
├── memory/         # Tiered memory, embeddings, vector search
├── api/            # REST endpoints
├── channels/       # 6 communication channels
├── assistant/      # Voice pipeline (wake → STT → TTS)
├── pc_agent/       # Computer control & automation
├── governance/     # Security, privacy classification, validation
├── tools/          # Search, browser, research, image generation
├── jarvis_plugin_sdk/  # Python plugin SDK
├── docker-compose.yml   # Ollama + JARVIS stack
└── Dockerfile           # Container image
```

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

## 🔌 Plugin SDK

JARVIS has a Python-native plugin SDK — no TypeScript required.

```python
from jarvis_plugin_sdk import Plugin, hook

class MyPlugin(Plugin):
    @hook("on_agent_reply")
    def add_signature(self, reply: str) -> str:
        return reply + "\n\n— Sent via MyPlugin"

    @hook("on_voice_command")
    def log_commands(self, text: str) -> str:
        print(f"Voice: {text}")
        return text
```

**7 hook points** across the entire system:
- `on_agent_reply` — Modify agent responses
- `on_channel_message` — Intercept channel messages
- `on_voice_command` — Process voice input
- `on_website_generate` — Customize generated websites
- `on_dreaming_cycle` — Extend dreaming/reflection
- `on_file_saved` — React to file changes
- `on_memory_recall` — Augment memory search

Install plugins via pip or the dashboard:
```bash
jarvis plugin search  # Browse marketplace
jarvis plugin install my-plugin  # pip install
jarvis plugin list    # See active plugins
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
  <p>Built with ❤️ for a private AI future</p>
  <p>
    <a href="https://github.com/Pavankumar-p-k/agi/issues">Report Bug</a>
    ·
    <a href="https://github.com/Pavankumar-p-k/agi/issues">Request Feature</a>
    ·
    <a href="https://github.com/Pavankumar-p-k/agi">GitHub</a>
  </p>
</div>
