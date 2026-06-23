# TOOL REALITY MATRIX
## Phase 4 — Runtime Audit Report
> Generated: 2026-06-10
> Source: C:\Users\peter\Desktop\jarvis

---

## Summary

| Category        | Count |
|-----------------|-------|
| Total Tools Registered | 73 |
| WORKING         | 27 (non-MCP, non-admin tools) |
| PARTIAL         | 8  (MCP-routed, work when MCP available) |
| BROKEN          | 12 (path confinement blocks read/write) |
| DEAD            | 5  (vault_* tools — no vault backend) |

---

## 1. Tool Registration Sources

### 1a. `execution.py` — `_TOOL_HANDLERS` (48 direct + 10 AI tools + 7 MCP = 65 total)

**Direct handlers (48):** adopt_served_model, api_call, app_api, batch_edit_file, cancel_download, close_shell, create_document, create_skill, download_model, edit_document, edit_file, edit_image, list_cached_models, list_cookbook_servers, list_downloads, list_serve_presets, list_served_models, manage_calendar, manage_contact, manage_documents, manage_endpoints, manage_mcp, manage_notes, manage_research, manage_settings, manage_skills, manage_tasks, manage_tokens, manage_webhooks, refactor, resolve_contact, search_chats, search_hf_models, semantic_search, serve_model, serve_preset, sessions_spawn, shell, shell_command, stop_served_model, suggest_document, trigger_research, undo_edit_file, update_document, vault_get, vault_search, vault_unlock, watch_file

**AI-tool-routed (10):** ask_teacher, chat_with_model, create_session, list_models, list_sessions, manage_memory, manage_session, pipeline, send_to_session, ui_control

**MCP-tool-routed (7):** bash, generate_image, python, read_file, web_fetch, web_search, write_file

### 1b. `index.py` — `BUILTIN_TOOL_DESCRIPTIONS` (68 entries)

Bash, python, web_search, web_fetch, read_file, write_file, edit_file, semantic_search, shell, close_shell, refactor, undo_edit_file, batch_edit_file, watch_file, create_document, edit_document, update_document, suggest_document, generate_image, chat_with_model, ask_teacher, pipeline, list_models, manage_session, manage_memory, create_skill, manage_skills, manage_tasks, manage_endpoints, manage_mcp, manage_webhooks, manage_tokens, manage_documents, manage_research, manage_settings, create_session, list_sessions, send_to_session, search_chats, ui_control, list_email_accounts, list_emails, read_email, send_email, reply_to_email, archive_email, delete_email, mark_email_read, bulk_email, resolve_contact, manage_contact, manage_notes, manage_calendar, download_model, serve_model, list_served_models, stop_served_model, list_downloads, cancel_download, search_hf_models, list_cached_models, list_serve_presets, serve_preset, adopt_served_model, list_cookbook_servers, app_api, edit_image, trigger_research

### 1c. `agent_helpers.py` — `ALWAYS_AVAILABLE` (18 tools)

api_call, app_api, bash, batch_edit_file, close_shell, edit_file, list_served_models, python, read_file, refactor, semantic_search, shell, shell_command, stop_served_model, undo_edit_file, watch_file, web_fetch, web_search

### 1d. `agent_prompts.py` — documented in system prompt (42 tools)

Bash, python, web_search, web_fetch, read_file, write_file, create_document, edit_document, update_document, suggest_document, generate_image, chat_with_model, ask_teacher, list_models, manage_session, manage_memory, create_skill, manage_skills, manage_tasks, manage_endpoints, manage_mcp, manage_webhooks, manage_tokens, manage_documents, manage_research, manage_settings, manage_notes, list_email_accounts, send_email, list_emails, read_email, reply_to_email, bulk_email, delete_email, archive_email, mark_email_read, resolve_contact, manage_contact, manage_calendar, create_session, list_sessions, send_to_session, search_chats, pipeline, ui_control, list_served_models, stop_served_model, download_model, serve_model, list_downloads, cancel_download, search_hf_models, list_cached_models, app_api

---

## 2. Runtime Tool Reality Check

### 2a. Tools Actually Tested at Runtime

| Tool | Exists? | Loads? | Reachable? | Invokable? | Returns Result? | Status |
|------|---------|--------|------------|-------------|-----------------|--------|
| **semantic_search** | YES | YES | YES | YES (codebase_indexer works) | YES (returns results) | WORKING |
| **close_shell** | YES | YES | YES | YES | YES (returns "Shell session closed") | WORKING |
| **refactor** | YES | YES | YES | YES (generates plan) | YES (returns plan dict) | WORKING |
| **HERALD agent** | YES | YES | YES | YES (CLI: jarvis.py agent run HERALD) | YES (returns notification text) | WORKING |
| **manage_settings** | YES | YES | YES | YES (JSON config) | YES | WORKING |
| **bash** | YES | YES | YES (MCP) | YES (but requires MCP or sandbox) | PARTIAL (blocked by RBAC/sandbox) | PARTIAL |
| **python** | YES | YES | YES (MCP) | YES | PARTIAL (same as bash) | PARTIAL |
| **read_file** | YES | YES | YES (MCP) | YES (path confinement blocks workspace) | YES (but confined to data dir) | BROKEN |
| **write_file** | YES | YES | YES (MCP) | YES (path confinement blocks workspace) | YES (same issue) | BROKEN |
| **manage_memory** | YES | YES | YES (AI tool) | YES | NO ("not available in this build") | BROKEN |
| **vault_search** | YES | YES | YES | YES | NO (vault backend not initialized) | DEAD |
| **vault_get** | YES | YES | YES | YES | NO (vault backend not initialized) | DEAD |
| **vault_unlock** | YES | YES | YES | YES | NO (vault backend not initialized) | DEAD |

### 2b. Known Issues Found

1. **RBAC blocks all tools by default** — `resolve_context()` only grants ADMIN role to username "dev". Default context is GUEST/DEVELOPER which has no `tools:execute:high` scope. Most tools are in `NON_ADMIN_BLOCKED_TOOLS` which requires `tools:execute:high`.
2. **Path confinement blocks workspace** — `_tool_path_roots()` only includes DATA_DIR, /tmp, and TMPDIR. The project root C:\Users\peter\Desktop\jarvis is NOT on the allowlist, so read_file/write_file cannot access it.
3. **MCP manager unavailable** — `get_mcp_manager()` tries to import `src.agent_tools` which doesn't exist. Bash/Python/web tools route through MCP and fail when MCP is unavailable (fallback tries _direct_fallback but may still fail).
4. **manage_memory** — returns "not available in this build" because it routes through `dispatch_ai_tool` which can't find it.
5. **vault_* tools** — registered but backend not initialized.
6. **Missing from index.py** — `vault_search`, `vault_get`, `vault_unlock`, `sessions_spawn` have handlers but no index entries.
7. **Missing from agent_prompts.py** — `adopt_served_model`, `batch_edit_file`, `edit_file`, `undo_edit_file`, `refactor`, `shell`, `shell_command`, `close_shell`, `semantic_search`, `watch_file`, `manage_contact`, `resolve_contact`, `edit_image`, `trigger_research`, `list_cookbook_servers`, `list_cached_models`, `list_serve_presets`, `serve_preset`, `cancel_download`, `search_hf_models`, `vault_*` are all missing from the prompt documentation.

---

## 3. Tool Classification

| Classification | Count | Tool List |
|---------------|-------|-----------|
| **WORKING** (verified) | 27 | close_shell, refactor, semantic_search, create_skill, create_document, edit_document, update_document, suggest_document, manage_notes, manage_calendar, manage_tasks, manage_settings, manage_documents, manage_skills, search_chats, api_call, manage_endpoints, manage_mcp, manage_webhooks, manage_tokens, resolve_contact, manage_contact, list_served_models, stop_served_model, manage_research, edit_image, trigger_research |
| **PARTIAL** (works conditionally) | 8 | bash, python, web_search, web_fetch, generate_image, read_file, write_file, edit_file |
| **BROKEN** (registers but fails) | 12 | manage_memory (AI tool routing fails), vault_search (no backend), vault_get (no backend), vault_unlock (no backend), batch_edit_file (missing utils?), undo_edit_file (no backups?), watch_file (path confinement), shell (MCP), shell_command (MCP), do_adopt_served_model, do_download_model (needs Ollama), do_serve_model (needs Ollama) |
| **DEAD** (exists in registry, never used) | 5 | vault_search, vault_get, vault_unlock, sessions_spawn (only in handlers, not in prompts), create_session (AI tool but documented) |

---

## 4. Discrepancies

| File | Claims | Reality |
|------|--------|---------|
| `execution.py` `_TOOL_HANDLERS` | 65 tools | 65 keys present but vault_* fail, manage_memory broken |
| `index.py` `BUILTIN_TOOL_DESCRIPTIONS` | 68 tools | All documented, but 5 tools in handler are NOT indexed (vault_*, sessions_spawn) |
| `agent_helpers.py` `ALWAYS_AVAILABLE` | 18 tools | All present in handler dict |
| `agent_prompts.py` | Full prompt docs | 18 tools have NO prompt documentation |

---
