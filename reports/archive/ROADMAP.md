# JARVIS Roadmap

> **Mission:** Make local-first AI as capable as cloud-only assistants — without compromising privacy.

## v1.1 — Current Release
- [x] Local-first chat with 126+ LLM providers via LiteLLM
- [x] 3-tier privacy routing (LOCAL / HYBRID / CLOUD)
- [x] 10 parallel sub-agents (Nexus, Forge, Oracle, Phantom, Cipher, Herald, Scribe, Atlas, Sentinel, Maestro)
- [x] 6 communication channels (Discord, Telegram, Slack, Email, IRC, Matrix)
- [x] Voice pipeline (wake word → STT → TTS)
- [x] Docker sandbox for isolated code execution
- [x] Hot-reloadable trigger skills
- [x] Persistent shell sessions (Windows + Unix)
- [x] AST code graph with semantic search
- [x] Self-healing 3-layer recovery
- [x] 50 built-in skills (finance, productivity, knowledge, system, entertainment)
- [x] JarvisHub skill marketplace

## v1.2 — Next (Q3 2026)
- [ ] **WhatsApp Channel Plugin** — Wire WhatsApp into `ChannelPlugin` base class for unified message routing
- [ ] **Plugin SDK v2** — Standalone installable SDK with type stubs, docs, and PyPI distribution
- [ ] **E2E test suite** — Full channel pipeline integration tests (Discord, Telegram, Slack, IRC, Matrix)
- [ ] **Benchmark dashboard** — Track response times, tool latency, memory usage across releases
- [ ] **MCP server marketplace** — Browse and install MCP servers from a public registry
- [ ] **Windows installer** — One-click MSI installer bundling Python + Ollama + JARVIS

## v1.3 — Medium Term (Q4 2026)
- [ ] **Plugin hot-reload** — Install and enable plugins without restarting the server
- [ ] **Multi-user mode** — Session isolation, per-user config, shared skills
- [ ] **Mobile companion app** — React Native client for voice + text on iOS/Android
- [ ] **Knowledge base import** — Ingest PDFs, websites, Notion, Confluence into vector memory
- [ ] **Tool execution audit trail** — Full replay log of every tool call for debugging
- [ ] **CI/CD for skills** — GitHub Action to validate and test skills on push

## v2.0 — Long Term (2027)
- [ ] **Federated skill network** — Share skills across JARVIS instances (opt-in)
- [ ] **P2P agent collaboration** — Multiple JARVIS instances collaborate on tasks via MCP
- [ ] **On-device fine-tuning** — Fine-tune models locally with user data (never leaves your machine)
- [ ] **Visual skill builder** — Drag-and-drop UI to create skills without writing code
- [ ] **Enterprise SSO** — SAML/OIDC integration for team deployments
- [ ] **Offline-first** — Full functionality without any internet connection

---

*Roadmap is a living document. [Open an issue](https://github.com/Pavankumar-p-k/agi/issues) to suggest priorities.*
