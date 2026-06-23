# HN Launch Post — Draft

## Title: JARVIS — The Privacy-First AI OS (Local LLMs, 10 Sub-Agents, 126 Providers)

## Body (first comment)

JARVIS is an open-source AI operating system that runs entirely on your machine. No data leaves your hardware unless you explicitly allow it.

**Why another AI assistant?** Every other tool (Claude Code at $100/mo, ChatGPT at $20/mo, OpenClaw at $20/mo) sends your code, conversations, and data to their cloud. JARVIS runs local by default — Ollama on your GPU, voice pipeline on your CPU, all private.

**What makes JARVIS different:**

• 126+ LLM providers via LiteLLM — local Ollama models or any cloud API
• 10 parallel sub-agents (free vs Claude Code's $100/mo limit)
• Persistent shell sessions that remember `cd` and `export`
• Hot-reloadable skills — create trigger-based automations without restarting
• Docker sandbox for isolated code execution (network-disabled, memory-limited)
• Full voice pipeline — wake word → STT → TTS, all local
• 6 communication channels — Discord, Telegram, Slack, Email, IRC, Matrix
• 50 built-in skills across finance, productivity, knowledge, system, entertainment
• AST code graph with semantic search — understands your codebase
• Self-healing 3-layer recovery

**Quick start (one command):**
```
git clone https://github.com/Pavankumar-p-k/agi.git
cd agi
docker compose up --build -d
```

Or native: `pip install jarvis-ai-os && jarvis setup`

**Security:** Pre-launch audit fixed 8 critical issues including hardcoded API keys, shell injection vectors, and 82 swallowed exceptions. Every API key comes from env vars — zero hardcoded secrets.

**What's next:** WhatsApp channel, plugin hot-reload, mobile companion, multi-user mode. See ROADMAP.md.

I built this because I wanted an AI that respects my privacy. Would love your feedback.

---

# Reddit Launch Post — Draft

## Subreddit: r/MachineLearning / r/selfhosted / r/LocalLLaMA

## Title: Show HN: JARVIS — open-source privacy-first AI OS with 126 providers and local-first design

## Body:

I've been working on JARVIS for a while — it's an AI operating system that runs on your hardware, not in someone else's cloud.

**Key features:**

- **Local-first by default:** Ollama on your GPU, all data stays local. 3-tier privacy routing (LOCAL/HYBRID/CLOUD) with automatic PII stripping.
- **126 LLM providers:** One `.env` line switches between OpenAI, Anthropic, Gemini, Groq, DeepSeek, local Ollama — any LiteLLM provider.
- **10 parallel sub-agents:** Nexus, Forge, Oracle, Atlas, etc. — specialized agents that run concurrently, not serially.
- **Stateful shell:** Persistent sessions that remember `cd`, `export`, and virtualenvs. `sandbox:` prefix runs commands in Docker.
- **Hot-reloadable skills:** Create trigger-based automations with `create_skill` — generates .md + .py, live instantly.
- **Voice pipeline:** Wake word (Porcupine) → STT (Faster-Whisper) → TTS (Kokoro). All local, no cloud.
- **6 chat channels:** Discord, Telegram, Slack, Email, IRC, Matrix.
- **Self-healing:** 3-layer detection/recovery for crashes.

**One-command deploy:**
```
docker compose up --build -d
```
Or: `pip install jarvis-ai-os && jarvis setup`

**Why this matters:** Claude Code is $100/mo. OpenClaw had 512 CVEs. ChatGPT trains on your data. JARVIS is MIT-licensed, free forever, and audited for 8 security fixes before launch.

**Stack:** Python 3.11+, FastAPI, LiteLLM, Ollama, Docker, SQLite/PostgreSQL.

GitHub: https://github.com/Pavankumar-p-k/agi
Roadmap: ROADMAP.md

Would love feedback, contributions, and ideas for v1.2.
