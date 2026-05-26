# JARVIS Post-Audit Implementation Plan

**Date**: 2026-05-24
**Based on**: Full competitive analysis vs Claude Code, Claude Cowork, OpenClaw + line-by-line codebase audit

---

## Phase 1: Router Unification (~5 min)

**Goal**: Eliminate contradictory model configs between `model_router.py` and `llm_router.py`.

| Step | File | Change |
|------|------|--------|
| 1.1 | `core/llm_router.py:8` | Change `ollama/llama3.1:8b` → `ollama/qwen3:4b` for `model_name: "chat"` |
| 1.2 | `core/llm_router.py` | Verify all `model_name` entries match `model_router.py` `ROLE_MODELS` keys |

**Verify**: Both routers output the same model name for "chat".

---

## Phase 2: CLI → `/api/chat` Redirect (~2 hrs)

**Goal**: CLI conversation loop uses the feature-complete `/api/chat` endpoint.

| Step | File | Change |
|------|------|--------|
| 2.1 | `jarvis.py:130-186` | Add `conversation_history = []` before the `while True` loop |
| 2.2 | `jarvis.py:161-186` | Change POST target from `/os/agent/think` to `/api/chat` for regular messages |
| 2.3 | `jarvis.py:161-186` | Append user message to `conversation_history`, pass in payload |
| 2.4 | `jarvis.py:161-186` | On response, append assistant reply to `conversation_history`, cap at 20 |
| 2.5 | `jarvis.py` | Keep `/os/agents/run` only for `/plan`, `/goal`, `/develop` slash commands |
| 2.6 | `jarvis.py:171` | Handle auth: send dummy/internal auth header or skip token verification for local calls |

**Verify**: `> my name is Pavan` → `> what is my name` → returns "Pavan Kumar"

---

## Phase 3: MythosBrain Integration (~3 hrs)

**Goal**: Every `/api/chat` response passes through the brain's 6 cognitive patterns + epistemic tagger.

| Step | File | Change |
|------|------|--------|
| 3.1 | `core/main.py:1840` | After `reply.choices[0].message.content`, call `UnifiedBrain.get_instance().enhance(task=sanitized_message, response=reply)` |
| 3.2 | `core/main.py:1840` | Apply `epistemic_tagger.tag_response(enhanced_reply, sources=..., confidence=...)` |
| 3.3 | `core/main.py:1849-1855` | Add `"epistemic_tags": patterns` to response JSON |
| 3.4 | `brain/UnifiedBrain.py:342` | Change `_call()` to use `llm_router.acompletion()` instead of `self.router.complete()` (LiteLLM path for fallback + cloud routing) |
| 3.5 | `brain/UnifiedBrain.py` | Add graceful fallback — if brain errors, return original reply, never crash |

**Verify**: `> what is the capital of France` → response includes epistemic tag (`[VERIFIED]`, `[ASSUMED]`, etc.)

---

## Phase 4: Sandbox Wiring (~4 hrs)

**Goal**: All execution goes through `SandboxedExecutor` with semantic governance.

| Step | File | Change |
|------|------|--------|
| 4.1 | `pc_agent/computer_agent.py:17` | Set `interpreter.auto_run = False` |
| 4.2 | `pc_agent/computer_agent.py:21` | Import + wire `SandboxedExecutor` — every generated command passes through sandbox before execution |
| 4.3 | `governance/GovernanceValidator.py` | Replace 5-keyword regex with TinyLlama semantic classification (`SAFE`/`UNSAFE`) |
| 4.4 | `ai_os/sandbox.py:23-27` | Expand blocklist: add `curl|sh`, `wget -O-`, path whitelist (only `$CWD` + `$HOME`) |
| 4.5 | `core/agent_executor.py:198,246` | Replace `create_subprocess_shell` → `SandboxedExecutor.execute()` |
| 4.6 | `core/goal_processor.py:201,237,248` | Replace `create_subprocess_shell` → `SandboxedExecutor.execute()` |
| 4.7 | `autonomy/l4_controller/controller_layer.py:127,265` | Replace `create_subprocess_shell` / `Popen(shell=True)` → `SandboxedExecutor.execute()` |

**Verify**: `open notepad` → SAFE → executes. `del C:\Windows\System32\*` → UNSAFE → blocked.

---

## Phase 5: Telegram Bot (~3 hrs)

**Goal**: JARVIS accessible from phone via Telegram.

| Step | File | Change |
|------|------|--------|
| 5.1 | New: `channels/telegram_bot.py` | Create bot: `/start`, `/chat`, `/status`, `/search` handlers |
| 5.2 | `channels/telegram_bot.py` | Wire to `/api/chat` via `httpx` (same pipeline CLI now uses) |
| 5.3 | `channels/telegram_bot.py` | Voice message support: receive → `/stt` → chat → `/tts` → send voice |
| 5.4 | `core/main.py` | Add lifespan startup to register Telegram webhook (`WEBHOOK_URL`) |
| 5.5 | `start.bat` | Add `start "" python channels/telegram_bot.py` |
| 5.6 | `apps/jarvis_app/lib/screens/settings_screen.dart:19` | Replace dead `_telegram` toggle with live HTTP health-check indicator |

**Verify**: `/start` → welcome. `what is ML` → Ollama response. `/status` → health. All from phone.

---

## Phase 6: Computer Use Vision (~4 hrs)

**Goal**: Computer agent sees the screen before acting.

| Step | File | Change |
|------|------|--------|
| 6.1 | `pc_agent/computer_agent.py` | Add `get_screen_context()` — screenshot → `ImageGrab.grab()` → base64 → gemma4:e4b vision description |
| 6.2 | `pc_agent/computer_agent.py` | Prepend screen description to system prompt before `interpreter.chat()` |
| 6.3 | `pc_agent/playbooks.py` | Add `REQUIRES_CONFIRMATION = ["delete", "remove", "uninstall", "format", "clear"]` |
| 6.4 | `pc_agent/playbooks.py` | Add `needs_confirmation()` gate — destructive playbook steps pause for user `y/N` |
| 6.5 | `tools/browser_tool.py` | Add `screenshot_and_describe()` — Playwright screenshot → moondream caption |
| 6.6 | `core/main.py` (`/computer` endpoint) | Add `format="vision"` parameter — returns screenshot description alongside result |

**Verify**: `open YouTube in browser` → sees screen → opens Chrome → navigates → confirms via follow-up screenshot.

---

## Phase 7: Cross-Cutting Polish (~2 hrs)

**Goal**: Address remaining orphaned code and dead paths.

| Step | File | Change |
|------|------|--------|
| 7.1 | `brain/UnifiedBrain.py` | Implement Patterns 7-10 (Recursive Decomposition, Socratic Depth, Working Scratchpad, Consistency Enforcement) |
| 7.2 | `brain/UnifiedBrain.py:317` | Wire `deep_think()` to the `/api/chat` "full" depth mode |
| 7.3 | `core/main.py:1793-1825` | Add conversation summarization — when history exceeds 30 messages, summarize oldest 20 into a single system message |
| 7.4 | `ai_os/sandbox.py` | Remove orphaned status — confirm it's imported in at least one active pipeline (from Phase 4) |
| 7.5 | `core/main.py` | Search entire file for unused imports leftover from the two-pipeline era |

**Verify**: No dead code paths. `deep_think()` reachable via `/api/chat?depth=full`.

---

## Dependency Graph

```
Phase 1 (Router) ─── no deps
     │
     ▼
Phase 2 (CLI→/api/chat) ─── needs Phase 1
     │
     ▼
Phase 3 (Brain) ─── needs Phase 2
     │
     ├─────────────────────────────────────┐
     ▼                                     ▼
Phase 4 (Sandbox) ─── no deps on 1-3     Phase 5 (Telegram) ─── needs Phase 2, 3
     │                                     │
     │                                     │
     ▼                                     ▼
Phase 6 (Vision) ─── needs Phase 4       Phase 7 (Polish) ─── needs Phase 3
```

## Effort Summary

| Phase | Hours | Files Changed | New Files |
|-------|-------|--------------|-----------|
| 1 — Router Unification | 0.1 | 2 | 0 |
| 2 — CLI → `/api/chat` | 2 | 1 | 0 |
| 3 — MythosBrain Integration | 3 | 2 | 0 |
| 4 — Sandbox Wiring | 4 | 6 | 0 |
| 5 — Telegram Bot | 3 | 3 | 1 |
| 6 — Computer Use Vision | 4 | 4 | 0 |
| 7 — Cross-Cutting Polish | 2 | 4 | 0 |
| **Total** | **~18 hrs** | **22** | **1** |
