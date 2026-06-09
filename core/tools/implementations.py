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
from core.tools._tool_utils import (
    MAX_OUTPUT_CHARS,
    MAX_READ_CHARS,
    _parse_tool_args,
    _truncate,
    get_mcp_manager,
)
from core.tools.admin_tools import (
    do_manage_endpoints,
    do_manage_mcp,
    do_manage_tokens,
    do_manage_webhooks,
)
from core.tools.cookbook_tools import (
    do_adopt_served_model,
    do_app_api,
    do_cancel_download,
    do_download_model,
    do_edit_image,
    do_list_cached_models,
    do_list_cookbook_servers,
    do_list_downloads,
    do_list_serve_presets,
    do_list_served_models,
    do_manage_contact,
    do_manage_research,
    do_resolve_contact,
    do_search_hf_models,
    do_serve_model,
    do_serve_preset,
    do_stop_served_model,
    do_trigger_research,
    do_vault_get,
    do_vault_search,
    do_vault_unlock,
)
from core.tools.document_tools import (
    clear_active_document,
    do_create_document,
    do_edit_document,
    do_manage_documents,
    do_suggest_document,
    do_update_document,
    get_active_document,
    parse_suggest_blocks,
    set_active_document,
    set_active_model,
)
from core.tools.settings_tools import (
    do_api_call,
    do_manage_calendar,
    do_manage_notes,
    do_manage_settings,
)
from core.tools.skill_tools import (
    do_create_skill,
    do_manage_skills,
    do_manage_tasks,
    do_search_chats,
)

__all__ = [
    "MAX_OUTPUT_CHARS", "MAX_READ_CHARS",
    "get_mcp_manager", "_truncate", "_parse_tool_args",
    "set_active_document", "set_active_model", "get_active_document", "clear_active_document",
    "do_create_document", "do_update_document", "do_edit_document", "do_suggest_document",
    "do_manage_documents", "parse_suggest_blocks",
    "do_search_chats", "do_create_skill", "do_manage_skills", "do_manage_tasks",
    "do_manage_endpoints", "do_manage_mcp", "do_manage_webhooks", "do_manage_tokens",
    "do_manage_settings", "do_api_call", "do_manage_notes", "do_manage_calendar",
    "do_app_api", "do_download_model", "do_serve_model", "do_list_served_models",
    "do_stop_served_model", "do_list_downloads", "do_cancel_download", "do_search_hf_models",
    "do_list_cached_models", "do_list_serve_presets", "do_serve_preset", "do_adopt_served_model",
    "do_list_cookbook_servers", "do_edit_image", "do_trigger_research", "do_manage_research",
    "do_resolve_contact", "do_manage_contact", "do_vault_search", "do_vault_get", "do_vault_unlock",
]
