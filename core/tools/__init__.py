# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from core.tools.execution import _run_subprocess_streaming, execute_tool_block
from core.tools.executor import ToolExecutor, tool_executor
from core.tools.implementations import (
    do_adopt_served_model,
    do_api_call,
    do_app_api,
    do_cancel_download,
    do_create_document,
    do_download_model,
    do_edit_document,
    do_edit_image,
    do_list_cached_models,
    do_list_cookbook_servers,
    do_list_downloads,
    do_list_serve_presets,
    do_list_served_models,
    do_manage_calendar,
    do_manage_google_calendar,
    do_manage_contact,
    do_manage_documents,
    do_manage_endpoints,
    do_manage_mcp,
    do_manage_notes,
    do_manage_research,
    do_manage_settings,
    do_manage_skills,
    do_manage_tasks,
    do_manage_tokens,
    do_manage_webhooks,
    do_resolve_contact,
    do_search_chats,
    do_search_hf_models,
    do_serve_model,
    do_serve_preset,
    do_stop_served_model,
    do_suggest_document,
    do_trigger_research,
    do_update_document,
    do_vault_get,
    do_vault_search,
    do_vault_unlock,
)
from core.tools.index import ALWAYS_AVAILABLE, BUILTIN_TOOL_DESCRIPTIONS, ToolIndex
from core.tools.parsing import _TOOL_NAME_MAP, ToolBlock, parse_tool_blocks, strip_tool_blocks
from core.tools.registry import ToolRegistry, ToolRecord, tool_registry
from core.tools.resolver import ToolResolver, ResolutionResult, tool_resolver
from core.tools.schemas import FUNCTION_TOOL_SCHEMAS, function_call_to_tool_block
from core.tools.security import (
    NON_ADMIN_BLOCKED_TOOLS,
    blocked_tools_for_owner,
    is_public_blocked_tool,
    owner_is_admin_or_single_user,
)

__all__ = [
    "FUNCTION_TOOL_SCHEMAS", "function_call_to_tool_block",
    "NON_ADMIN_BLOCKED_TOOLS", "is_public_blocked_tool", "owner_is_admin_or_single_user", "blocked_tools_for_owner",
    "ResolutionResult", "ToolExecutor", "ToolIndex", "ToolRecord", "ToolRegistry", "ToolResolver",
    "tool_executor", "tool_registry", "tool_resolver",
    "ALWAYS_AVAILABLE", "BUILTIN_TOOL_DESCRIPTIONS",
    "parse_tool_blocks", "strip_tool_blocks", "ToolBlock", "_TOOL_NAME_MAP",
    "execute_tool_block", "_run_subprocess_streaming",
    "do_create_document", "do_update_document", "do_edit_document", "do_suggest_document",
    "do_search_chats", "do_manage_skills", "do_manage_tasks", "do_manage_endpoints",
    "do_manage_mcp", "do_manage_webhooks", "do_manage_tokens", "do_manage_documents",
    "do_manage_settings", "do_api_call", "do_manage_notes", "do_manage_calendar", "do_manage_google_calendar",
    "do_download_model", "do_serve_model", "do_list_served_models", "do_stop_served_model",
    "do_list_downloads", "do_cancel_download", "do_search_hf_models", "do_list_cached_models",
    "do_list_serve_presets", "do_serve_preset", "do_adopt_served_model", "do_list_cookbook_servers",
    "do_edit_image", "do_trigger_research", "do_manage_research", "do_resolve_contact",
    "do_manage_contact", "do_vault_search", "do_vault_get", "do_vault_unlock", "do_app_api",
    "do_build_project", "do_repair_project", "do_run_tests", "do_runtime_validate",
    "do_manage_memory", "do_create_session", "do_chat_with_model",
]
