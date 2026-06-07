# JARVIS Use Cases — What You Can Actually Do

> This document catalogs every real, working capability in JARVIS — tested against the actual codebase, not aspirational. Each entry links to the implementing files.

---

## 💬 Chat & Assistant

| Use Case | How | Status | Key Files |
|----------|-----|--------|-----------|
| Chat with local LLM | `jarvis cli` → type anything → routes to Ollama | ✅ Working | `core/llm_router.py`, `core/routes/chat.py` |
| Chat with any cloud LLM | Set `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` in `.env` → model auto-routes | ✅ Working | `core/model_router.py` |
| Switch models mid-conversation | `/model` slash command | ✅ Working | `cli_slash_commands.py` |
| Multi-model comparison | `chat_with_model` tool asks a different model | ✅ Working | `core/agent_prompts.py` |
| Streaming responses | WebSocket at `/ws/chat_stream` → word-by-word | ✅ Working | `core/routes/websocket.py` |
| Chat history | `/sessions` lists, `/session-switch` resumes | ✅ Working | `core/database_models.py` |
| Epistemic tagging | Responses tagged with confidence/source/provenance | ✅ Working | `brain/epistemic_tagger.py` |

## 🛠️ Developer Tools

| Use Case | How | Status | Key Files |
|----------|-----|--------|-----------|
| Edit any file | `edit_file` tool — FIND/REPLACE with backup | ✅ Working | `core/tools/document_tools.py` |
| Undo file edits | `undo_edit_file` restores from backup | ✅ Working | `core/tools/document_tools.py` |
| Batch edit files | `batch_edit_file` applies same change to glob matches | ✅ Working | `core/tools/document_tools.py` |
| Refactor code | `refactor` tool — decompose goal → plan → execute | ✅ Working | `core/tools/refactor_tool.py` |
| Run shell commands | `shell` tool — persistent sessions, remembers `cd` | ✅ Working | `core/tools/persistent_shell.py` |
| Sandboxed execution | Prefix `sandbox:` → Docker container, network-disabled | ✅ Working | `ai_os/docker_sandbox.py` |
| Semantic code search | `semantic_search` — natural language → BM25 + vector + symbols | ✅ Working | `core/codebase_indexer.py` |
| Watch log files | `watch_file` — polling file watcher for log tailing | ✅ Working | `core/tools/hot_files.py` |
| Code review | FORGE agent reviews PRs for bugs and security | ✅ Working | `core/sub_agents/forge/` |
| Git operations | `shell` → `git commit`, `git push`, etc. | ✅ Working | (shell passthrough) |
| Run tests | `shell` → `pytest tests/` | ✅ Working | (shell passthrough) |

## 🤖 Sub-Agents (Parallel)

| Agent | Specialty | Status | Key Files |
|-------|-----------|--------|-----------|
| **NEXUS** | Integration & automation | ✅ Working | `core/sub_agents/nexus/` |
| **FORGE** | Code generation & review | ✅ Working | `core/sub_agents/forge/` |
| **ORACLE** | Chain-of-thought planning | ✅ Working | `core/sub_agents/oracle/` |
| **PHANTOM** | Analysis & summarization | ✅ Working | `core/sub_agents/phantom/` |
| **CIPHER** | Security & governance | ✅ Working | `core/sub_agents/cipher/` |
| **HERALD** | Social & communication | ✅ Working | `core/sub_agents/herald/` |
| **SCRIBE** | Quality & grading | ✅ Working | `core/sub_agents/scribe/` |
| **ATLAS** | Deep research & multi-hop search | ✅ Working | `core/sub_agents/atlas/` |
| **SENTINEL** | Monitoring & alerting | ✅ Working | `core/sub_agents/sentinel/` |
| **MAESTRO** | Orchestration & planning | ✅ Working | `core/sub_agents/maestro/` |

## 🎙️ Voice Pipeline

| Use Case | How | Status | Key Files |
|----------|-----|--------|-----------|
| Wake word detection | "Hey JARVIS" — two-stage VAD + Whisper confirmation | ✅ Working | `assistant/wake_word.py` |
| Speech-to-text | Faster-Whisper (local, default), Deepgram, Azure Speech | ✅ Working | `assistant/providers/` |
| Text-to-speech | Kokoro-TTS (local, 24kHz WAV output) | ✅ Working | `assistant/tts.py` |
| Full voice pipeline | Audio → emotion → STT → LLM → TTS → playback | ✅ Working | `assistant/voice_pipeline.py` |
| Voice integration tests | `test_voice_pipeline_integration.py` — 7 tests, all passing | ✅ Tested | `tests/integration/` |

## 📡 Communication Channels

| Channel | What You Can Do | Status | Key Files |
|---------|-----------------|--------|-----------|
| **Discord** | Bot responds to messages, slash commands | ✅ Working | `channels/discord_channel.py` |
| **Telegram** | Bot responds to messages, inline queries | ✅ Working | `channels/telegram_channel.py` |
| **Slack** | Socket Mode bot, event handling | ✅ Working | `channels/slack_channel.py` |
| **Email** | IMAP fetch → AI triage → draft reply → SMTP send | ✅ Working | `channels/email_channel.py` |
| **IRC** | Responds in channels, handles private messages | ✅ Working | `channels/irc_channel.py` |
| **Matrix** | Room messaging, login authentication | ✅ Working | `channels/matrix_channel.py` |
| **WhatsApp** | Webhook-based messaging via Meta Cloud API | ✅ Working | `routers/whatsapp.py`, `tools/whatsapp_sender.py` |

## 🖥️ PC Automation

| Use Case | How | Status | Key Files |
|----------|-----|--------|-----------|
| Open applications | "open Chrome" → subprocess launch | ✅ Working | `pc_agent/computer_agent.py` |
| File operations | "create folder", "move files" | ✅ Working | `pc_agent/computer_agent.py` |
| Browser automation | Playwright integration for web tasks | ✅ Working | `automation/pc_automation.py` |
| Screenshot + describe | Vision agent captures screen, describes it | ✅ Working | `core/vision_agent.py` |
| Keyboard/mouse control | Natural language → automation | ✅ Working | `pc_agent/computer_agent.py` |

## 🧩 Skills (50 Built-in)

| Category | Skills | Status | Key Files |
|----------|--------|--------|-----------|
| **Finance** (10) | stocks, crypto, budget, expenses, tax_calc, bill_reminder, gold_price, inflation, loan_emi, upi_gen | ✅ Working | `skills/library/finance/*/main.py` |
| **Productivity** (10) | calendar, email_summarizer, github_issues, habit_tracker, linkedin_drafter, meeting_minutes, pdf_extractor, pomodoro, todoist, url_shortener | ✅ Working | `skills/library/productivity/*/main.py` |
| **Knowledge** (10) | code_snippet, dictionary, fact_check, latex_math, paper_summarizer, regex_helper, sql_assistant, thesaurus, translator, wikipedia | ✅ Working | `skills/library/knowledge/*/main.py` |
| **System** (10) | clipboard, file_organizer, ip_lookup, password_gen, qr_gen, screenshot, speedtest, system_monitor, timer, unit_converter | ✅ Working | `skills/library/system/*/main.py` |
| **Entertainment** (10) | games, joke, movie_rec, news, quiz, quote, recipe, sports, spotify, weather | ✅ Working | `skills/library/entertainment/*/main.py` |
| **Hot-reloadable** | Create your own with `create_skill` tool | ✅ Working | `core/tools/skill_tools.py` |

## 🔧 System Administration

| Use Case | How | Status | Key Files |
|----------|-----|--------|-----------|
| Health diagnostics | `jarvis doctor` — checks deps, disk, ports, Docker, git | ✅ Working | `core/diagnostics.py` |
| Setup wizard | `jarvis setup` — 6 checks, detects missing deps | ✅ Working | `cli_commands.py` |
| Self-healing | 3-layer: detect → diagnose → restart | ✅ Working | `core/lifespan.py` |
| Process monitoring | SENTINEL agent watches system health | ✅ Working | `core/sub_agents/sentinel/` |
| Docker management | Start/stop containers, check status via shell | ✅ Working | (shell passthrough) |

## 🔌 Extensibility

| Use Case | How | Status | Key Files |
|----------|-----|--------|-----------|
| Create custom skills | `create_skill` tool → `.md` + `.py`, hot-reloads | ✅ Working | `core/tools/skill_tools.py` |
| Plugin SDK | `@hook` decorator, 7 lifecycle hooks, pip-installable | ✅ Working | `jarvis_plugin_sdk/` |
| MCP servers | Built-in MCP server, connect external MCP tools | ✅ Working | `mcp/server.py`, `core/tools/admin_tools.py` |
| Custom tools | Register in `_TOOL_HANDLERS` → available to agent | ✅ Working | `core/tools/execution.py` |
| Custom channels | Extend `ChannelPlugin` base class | ✅ Working | `channels/base.py` |

## 🌐 Deployment

| Use Case | How | Status | Key Files |
|----------|-----|--------|-----------|
| Docker one-command | `docker compose up --build -d` | ✅ Working | `Dockerfile`, `docker-compose.yml` |
| Native pip | `pip install jarvis-ai-os` then `jarvis setup` | ✅ Working | `pyproject.toml` |
| Windows native | `python jarvis.py` on Windows with cmd.exe | ✅ Working | `jarvis.py` |
| Linux/macOS native | `python jarvis.py` on Unix with /bin/sh | ✅ Working | `jarvis.py` |
| API-only (headless) | Run `core/main.py` via uvicorn, no GUI | ✅ Working | `core/main.py` |
| Development install | `pip install -e .` for editable mode | ✅ Working | `pyproject.toml` |

---

**Every item above is backed by actual code in this repository.** Not a single "coming soon" or "planned" feature. Run `jarvis doctor` to verify your environment, then `jarvis cli` to start.
