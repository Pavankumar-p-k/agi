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
from collections import namedtuple

MAX_AGENT_ROUNDS = 20
SHELL_TIMEOUT = 60
PYTHON_TIMEOUT = 30
MAX_OUTPUT_CHARS = 10_000
MAX_READ_CHARS = 20_000

TOOL_TAGS = {"bash", "python", "web_search", "web_fetch", "read_file", "write_file",
             "create_document", "update_document", "edit_document", "edit_file",
             "search_chats",
             "chat_with_model", "create_session", "list_sessions",
             "send_to_session",
             "pipeline",
             "manage_session", "manage_memory", "list_models",
             "ui_control", "generate_image",
             "manage_tasks", "api_call", "ask_teacher", "manage_skills",
             "suggest_document",
             "manage_endpoints", "manage_mcp", "manage_webhooks",
             "manage_tokens", "manage_documents", "manage_settings",
             "manage_notes", "manage_calendar",
             "resolve_contact", "manage_contact", "list_email_accounts", "send_email", "list_emails",
             "read_email", "reply_to_email", "bulk_email", "archive_email",
             "delete_email", "mark_email_read",
             "download_model", "serve_model",
             "list_served_models", "stop_served_model",
             "list_downloads", "cancel_download",
             "search_hf_models", "list_cached_models",
             "list_serve_presets", "serve_preset", "adopt_served_model",
             "list_cookbook_servers",
             "edit_image", "trigger_research", "manage_research",
             "app_api", "sessions_spawn", "watch_file",
             "undo_edit_file", "batch_edit_file", "semantic_search",
             "shell", "shell_command", "close_shell", "refactor",
             # Browser automation tools
             "vision_browser",
             "browser_navigate", "browser_find", "browser_find_interactive",
             "browser_click", "browser_fill", "browser_press",
             "browser_snapshot", "browser_get_url", "browser_get_title",
             "browser_screenshot", "browser_current_state", "browser_health",
             "browser_get_history", "browser_list_tabs", "browser_switch_tab",
             "browser_new_tab", "browser_close_tab",
              "browser_wait_visible", "browser_wait_text", "browser_wait_interactive",
              "browser_shadow_query", "browser_evaluate",
              # Build automation tools
               "build_project", "repair_project", "run_tests", "runtime_validate", "cancel_build",
               # Workflow engine tools
               "workflow_start", "workflow_resume", "workflow_cancel",
               "workflow_status", "workflow_list"}

ToolBlock = namedtuple("ToolBlock", ["tool_type", "content"])
