# PHASE 6 — Tool Audit

Every registered tool verified against actual implementation.
No claims without file:line evidence.

---

## Registration Architecture

Tools are registered in 6 places:

| Step | Location | Purpose |
|------|----------|---------|
| 1 | `core/tools/{category}_tools.py` | Implementation functions |
| 2 | `core/tools/implementations.py` | Re-exports all implementations |
| 3 | `core/tools/execution.py:_TOOL_HANDLERS` | Dispatch map (tool_name → handler) |
| 4 | `core/agent_prompts.py:_TOOL_SECTIONS` | Usage documentation for LLM |
| 5 | `core/tools/index.py` | RAG index + ALWAYS_AVAILABLE list |
| 6 | `core/agent_helpers.py:ALWAYS_AVAILABLE` | Force-included tools per turn |

---

## IMPLEMENTED Tools (49)

### File Operations (MCP-backed with direct fallback)

| Tool | Handler | Implementation | Path Confinement | Notes |
|------|---------|---------------|-------------------|-------|
| `read_file` | `_hdl_mcp_tool` | MCP server / `_direct_fallback` | ✅ `_resolve_tool_path()` | Lines 628-666 |
| `write_file` | `_hdl_mcp_tool` | MCP server / `_direct_fallback` | ✅ | Lines 668-695 |
| `append_file` | `_hdl_mcp_tool` | MCP server / `_direct_fallback` | ✅ | Lines 697-718 |
| `delete_file` | `_hdl_mcp_tool` | MCP server / `_direct_fallback` | ✅ | Lines 718-737 |
| `list_folder` | `_hdl_mcp_tool` | MCP server / `_direct_fallback` | ✅ | Lines 739-762 |

### Code Execution (MCP-backed)

| Tool | Handler | Implementation | Notes |
|------|---------|---------------|-------|
| `bash` | `_hdl_mcp_tool` | MCP server / `_direct_fallback` | 1-hour timeout, progress streaming |
| `python` | `_hdl_mcp_tool` | MCP server / `_direct_fallback` | 1-hour timeout, progress streaming |

### Web Tools (MCP-backed)

| Tool | Handler | Implementation | Notes |
|------|---------|---------------|-------|
| `web_search` | `_hdl_mcp_tool` | `comprehensive_web_search()` | Lines 763-816 |
| `web_fetch` | `_hdl_mcp_tool` | `fetch_webpage_content()` | Lines 818-878 |
| `generate_image` | `_hdl_mcp_tool` | MCP server | Lines 880-882 |

### Document Tools

| Tool | Handler | Implementation | File:Line |
|------|---------|---------------|-----------|
| `create_document` | `_hdl_create_document` | `document_tools.do_create_document` | execution.py:1614 |
| `update_document` | `_hdl_update_document` | `document_tools.do_update_document` | execution.py:1614 |
| `edit_document` | `_hdl_edit_document` | `document_tools.do_edit_document` | execution.py:1614 |
| `suggest_document` | `_hdl_suggest_document` | `document_tools.do_suggest_document` | execution.py:1615 |
| `manage_documents` | `_hdl_manage_documents` | `document_tools.do_manage_documents` | execution.py:1639 |

### Edit Tools

| Tool | Handler | Implementation | Path Confinement | Security |
|------|---------|---------------|-------------------|----------|
| `edit_file` | `_hdl_edit_file` | `execution.do_edit_file` | ✅ | Lines 936-1113 |
| `undo_edit_file` | `_hdl_undo_edit_file` | `execution.do_undo_edit_file` | ❌ BYPASSED | Lines 1186-1189 |
| `batch_edit_file` | `_hdl_batch_edit_file` | `execution.do_batch_edit_file` | ❌ BYPASSED | Lines 1232 |
| `refactor` | `_hdl_refactor` | `execution.do_refactor` | ❌ BYPASSED | Lines 1126-1131 |
| `watch_file` | `_hdl_watch_file` | inline | ✅ | Lines 1448-1506 |

### Shell Tools

| Tool | Handler | Implementation | Notes |
|------|---------|---------------|-------|
| `shell` | `_hdl_shell_command` | `persistent_shell.get_or_create_shell()` | Persistent session, `shell=False` |
| `shell_command` | `_hdl_shell_command` | Same as `shell` | Alias |
| `close_shell` | `_hdl_close_shell` | `persistent_shell.close_shell()` | |

### Search Tools

| Tool | Handler | Implementation | File:Line |
|------|---------|---------------|-----------|
| `semantic_search` | `_hdl_semantic_search` | `codebase_indexer.search_codebase` | execution.py:1628 |
| `search_chats` | `_hdl_search_chats` | `skill_tools.do_search_chats` | execution.py:1630 |

### Skill Tools

| Tool | Handler | Implementation | File:Line |
|------|---------|---------------|-----------|
| `create_skill` | `_hdl_create_skill` | `skill_tools.do_create_skill` | execution.py:1632 |
| `manage_skills` | `_hdl_manage_skills` | `skill_tools.do_manage_skills` | execution.py:1633 |

### Task Tools

| Tool | Handler | Implementation | File:Line |
|------|---------|---------------|-----------|
| `manage_tasks` | `_hdl_manage_tasks` | `skill_tools.do_manage_tasks` | execution.py:1631 |

### Settings/API Tools

| Tool | Handler | Implementation | File:Line |
|------|---------|---------------|-----------|
| `manage_settings` | `_hdl_manage_settings` | `settings_tools.do_manage_settings` | execution.py:1640 |
| `api_call` | `_hdl_api_call` | `settings_tools.do_api_call` | execution.py:1634 |

### Admin Tools

| Tool | Handler | Implementation | Notes |
|------|---------|---------------|-------|
| `manage_endpoints` | `_hdl_manage_endpoints` | `admin_tools.do_manage_endpoints` | BROKEN_TOOLS (returns DISABLED) |
| `manage_mcp` | `_hdl_manage_mcp` | `admin_tools.do_manage_mcp` | BROKEN_TOOLS (returns DISABLED) |
| `manage_webhooks` | `_hdl_manage_webhooks` | `admin_tools.do_manage_webhooks` | BROKEN_TOOLS (returns DISABLED) |
| `manage_tokens` | `_hdl_manage_tokens` | `admin_tools.do_manage_tokens` | BROKEN_TOOLS (returns DISABLED) |

### Notes/Calendar Tools

| Tool | Handler | Implementation | File:Line |
|------|---------|---------------|-----------|
| `manage_notes` | `_hdl_manage_notes` | `settings_tools.do_manage_notes` | execution.py:1642 |
| `manage_calendar` | `_hdl_manage_calendar` | `settings_tools.do_manage_calendar` | execution.py:1643 |

### Model Serving Tools (Cookbook)

| Tool | Handler | Implementation | File:Line |
|------|---------|---------------|-----------|
| `download_model` | `_hdl_download_model` | `cookbook_tools.do_download_model` | execution.py:1618 |
| `serve_model` | `_hdl_serve_model` | `cookbook_tools.do_serve_model` | execution.py:1618 |
| `list_served_models` | `_hdl_list_served_models` | `cookbook_tools.do_list_served_models` | execution.py:1620 |
| `stop_served_model` | `_hdl_stop_served_model` | `cookbook_tools.do_stop_served_model` | execution.py:1620 |
| `list_downloads` | `_hdl_list_downloads` | `cookbook_tools.do_list_downloads` | execution.py:1621 |
| `cancel_download` | `_hdl_cancel_download` | `cookbook_tools.do_cancel_download` | execution.py:1621 |
| `search_hf_models` | `_hdl_search_hf_models` | `cookbook_tools.do_search_hf_models` | execution.py:1622 |
| `list_cached_models` | `_hdl_list_cached_models` | `cookbook_tools.do_list_cached_models` | execution.py:1623 |
| `list_serve_presets` | `_hdl_list_serve_presets` | `cookbook_tools.do_list_serve_presets` | execution.py:1624 |
| `serve_preset` | `_hdl_serve_preset` | `cookbook_tools.do_serve_preset` | execution.py:1624 |
| `adopt_served_model` | `_hdl_adopt_served_model` | `cookbook_tools.do_adopt_served_model` | execution.py:1625 |
| `list_cookbook_servers` | `_hdl_list_cookbook_servers` | `cookbook_tools.do_list_cookbook_servers` | execution.py:1625 |

### Research Tools

| Tool | Handler | Implementation | File:Line |
|------|---------|---------------|-----------|
| `trigger_research` | `_hdl_trigger_research` | `cookbook_tools.do_trigger_research` | execution.py:1626 |
| `manage_research` | `_hdl_manage_research` | `cookbook_tools.do_manage_research` | execution.py:1626 |

### Contact/Vault Tools

| Tool | Handler | Implementation | File:Line |
|------|---------|---------------|-----------|
| `resolve_contact` | `_hdl_resolve_contact` | `cookbook_tools.do_resolve_contact` | execution.py:1636 |
| `manage_contact` | `_hdl_manage_contact` | `cookbook_tools.do_manage_contact` | execution.py:1636 |
| `vault_search` | `_hdl_vault_search` | `cookbook_tools.do_vault_search` | execution.py:1637 |
| `vault_get` | `_hdl_vault_get` | `cookbook_tools.do_vault_get` | execution.py:1637 |
| `vault_unlock` | `_hdl_vault_unlock` | `cookbook_tools.do_vault_unlock` | execution.py:1638 |

### Vision Tools

| Tool | Handler | Implementation | File:Line |
|------|---------|---------------|-----------|
| `vision_browser` | `_hdl_vision_browser` | `vision_tools.do_vision_browser` | execution.py:1617 |

### Sub-Agent Tools

| Tool | Handler | Implementation | File:Line |
|------|---------|---------------|-----------|
| `sessions_spawn` | `_hdl_sessions_spawn` | `sub_agents.tool.do_sessions_spawn` | execution.py:1644 |

### Other Tools

| Tool | Handler | Implementation | File:Line |
|------|---------|---------------|-----------|
| `app_api` | `_hdl_app_api` | `cookbook_tools.do_app_api` | execution.py:1635 |
| `edit_image` | `_hdl_edit_image` | `cookbook_tools.do_edit_image` | execution.py:1627 |

---

## BROKEN Tools (10) — Return DISABLED

| Tool | Reason | File:Line |
|------|--------|-----------|
| `chat_with_model` | `BROKEN_TOOLS` set | `execution.py:40-45` |
| `create_session` | `BROKEN_TOOLS` set | `execution.py:40-45` |
| `list_sessions` | `BROKEN_TOOLS` set | `execution.py:40-45` |
| `send_to_session` | `BROKEN_TOOLS` set | `execution.py:40-45` |
| `pipeline` | `BROKEN_TOOLS` set | `execution.py:40-45` |
| `manage_session` | `BROKEN_TOOLS` set | `execution.py:40-45` |
| `manage_memory` | `BROKEN_TOOLS` set — **BUT has dedicated arg parser** | `execution.py:40-45, 383-401` |
| `list_models` | `BROKEN_TOOLS` set | `execution.py:40-45` |
| `ui_control` | `BROKEN_TOOLS` set — **BUT has 12-line prompt description** | `execution.py:40-45, agent_prompts.py:229` |
| `ask_teacher` | `BROKEN_TOOLS` set | `execution.py:40-45` |

**Note:** `manage_endpoints`, `manage_mcp`, `manage_webhooks`, `manage_tokens` are also broken but their handlers return "DISABLED" at runtime rather than being in the `BROKEN_TOOLS` set. They appear in both `_TOOL_HANDLERS` and `BROKEN_TOOLS`.

---

## GHOST Tools (2) — Described in Prompts, No Implementation

| Tool | Prompt Description Location | Handler Status |
|------|---------------------------|----------------|
| `build_repomap` | `agent_prompts.py:49` — "Project structure (symbols, imports). Call early." | No handler. Not in `_TOOL_HANDLERS`. Not in `BUILTIN_TOOL_DESCRIPTIONS`. |
| `code_graph` | `agent_prompts.py:51` — "Dependency graph between files. Shows what imports what." | No handler. Not in `_TOOL_HANDLERS`. Not in `BUILTIN_TOOL_DESCRIPTIONS`. |

**Impact:** The LLM is told these tools exist and may attempt to call them. The call will either fail silently or produce an error.

---

## ALWAYS_AVAILABLE Tools (22)

Force-included in every agent turn regardless of tool RAG retrieval.

| Tool | Source |
|------|--------|
| `bash`, `python`, `web_search`, `web_fetch` | `index.py:48-61` |
| `read_file`, `write_file`, `append_file`, `delete_file`, `list_folder` | `index.py:48-61` |
| `edit_file`, `undo_edit_file`, `batch_edit_file`, `watch_file` | `index.py:48-61` |
| `semantic_search`, `shell`, `shell_command`, `close_shell` | `index.py:48-61` |
| `refactor`, `api_call`, `list_served_models`, `stop_served_model`, `app_api` | `index.py:48-61` |

---

## NON_ADMIN_BLOCKED Tools (35)

Blocked for non-admin (public/anonymous) users:

| Category | Tools |
|----------|-------|
| Code execution | `bash`, `python`, `shell`, `shell_command` |
| File access | `read_file`, `write_file` |
| Data access | `search_chats`, `manage_memory`, `manage_skills`, `manage_tasks` |
| Admin | `manage_endpoints`, `manage_mcp`, `manage_webhooks`, `manage_tokens`, `manage_documents`, `manage_settings` |
| API | `api_call`, `app_api` |
| Email | `send_email`, `reply_to_email`, `list_emails`, `read_email` |
| Contacts/Calendar | `resolve_contact`, `manage_contact`, `manage_calendar` |
| Vault | `vault_search`, `vault_get`, `vault_unlock` |
| Model management | `download_model`, `serve_model`, `serve_preset`, `stop_served_model`, `cancel_download`, `adopt_served_model` |

---

## Summary Statistics

| Metric | Count |
|--------|-------|
| Total tools in `_TOOL_HANDLERS` | 49 |
| MCP-backed tools | 9 (read/write/append/delete/list, bash/python, web_search/fetch, generate_image) |
| ALWAYS_AVAILABLE tools | 22 |
| NON_ADMIN_BLOCKED tools | 35 |
| BROKEN tools | 10 |
| GHOST tools (prompt-only) | 2 |
| Implementation files | 9 (`admin_tools.py`, `cookbook_tools.py`, `document_tools.py`, `settings_tools.py`, `skill_tools.py`, `vision_tools.py`, `persistent_shell.py`, `execution.py`, `sub_agents/tool.py`) |
| Registration points | 6 (`implementations.py`, `execution.py`, `agent_prompts.py`, `index.py`, `agent_helpers.py`, `security.py`) |
