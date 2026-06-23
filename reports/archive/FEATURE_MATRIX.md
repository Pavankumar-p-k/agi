# JARVIS Feature Matrix

| Feature | Status | Category | Enabled | Config | Health Check |
|---------|--------|----------|---------|--------|--------------|
| Model Providers (Ollama, OpenAI, Anthropic, Gemini, Groq, OpenRouter) | ✅ Stable | models | Yes | `llm.chat_model` | `health_check_all()` |
| Model Router (task-based routing) | ✅ Stable | models | Yes | `role_models.default` | Router health check |
| Integration Manager | 🟡 Beta | integrations | Yes | `integrations` | `health_check_all()` |
| Messaging Channels (Discord, Slack, Telegram, Matrix, IRC, Email) | ✅ Stable | integrations | Yes | — | Per-channel |
| WhatsApp (Meta Cloud API) | 🟡 Beta | integrations | Yes | `whatsapp` | Token verify |
| Gmail Monitor | 🟡 Beta | integrations | Yes | `gmail` | Monitor check |
| GitHub Integration | 📋 Planned | integrations | No | `github` | API check |
| Google Drive Integration | 📋 Planned | integrations | No | `google_drive` | API key check |
| Voice Assistant | 🟡 Beta | voice | Yes | `voice` | Pipeline health |
| Speech-to-Text (Faster-Whisper, Deepgram, Azure) | ✅ Stable | voice | Yes | `voice.stt_provider` | Provider health |
| Text-to-Speech (Kokoro, EdgeTTS) | 🟡 Beta | voice | Yes | `voice.tts_provider` | Provider health |
| Wake Word Detection | ✅ Stable | voice | Yes | `voice.wake_word_enabled` | Detector status |
| Plugin System | ✅ Stable | plugins | Yes | `plugins` | Framework check |
| Skill System | 🟡 Beta | skills | Yes | — | Loader check |
| Android Builder | 🟡 Beta | build | Yes | — | Build loop check |
| Webhook System | 🟡 Beta | integrations | Yes | `webhooks` | Dispatch stats |
| OAuth Login (Google, GitHub, Discord) | ✅ Stable | integrations | Yes | — | OAuth config |
| CLI Tool (45+ subcommands) | ✅ Stable | core | Yes | — | — |
| FastAPI Server | ✅ Stable | core | Yes | `server` | Health endpoint |
| Diagnostics & Doctor | ✅ Stable | core | Yes | — | `build_diagnostic_report()` |
| Memory System (RAG, Vector) | ✅ Stable | core | Yes | `memory` | Vector store |
| Web Search & Fetch | ✅ Stable | core | Yes | `web_search` | Search tool |

## Legend
- ✅ **Stable** — Production-ready, tested, documented
- 🟡 **Beta** — Functional, may have rough edges
- 🔵 **Experimental** — New, being iterated
- ❌ **Broken** — Known issues
- 📋 **Planned** — On roadmap, not yet implemented
