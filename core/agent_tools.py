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
"""
agent_tools.py — Facade module.

Re-exports tool parsing, schemas, execution, and implementations
for backward compatibility. All importers continue to work unchanged.

Sub-modules:
  - tool_parsing.py: regex patterns, parse/strip functions
  - tool_schemas.py: FUNCTION_TOOL_SCHEMAS, function_call_to_tool_block
  - tool_execution.py: execute_tool_block, format_tool_result, MCP helpers
  - tool_implementations.py: all do_* tool functions
"""

import logging

from core.tools._constants import (
    MAX_OUTPUT_CHARS,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MCP Manager (kept here — used by execution and agent_loop)
# ---------------------------------------------------------------------------
_mcp_manager = None

def set_mcp_manager(manager):
    """Set the global MCP manager instance."""
    global _mcp_manager
    _mcp_manager = manager

def get_mcp_manager():
    """Get the global MCP manager instance."""
    return _mcp_manager

# ---------------------------------------------------------------------------
# Helpers (kept here — used by sub-modules)
# ---------------------------------------------------------------------------
def _truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    # Callers treat the result as text, so always return a string: coerce a
    # non-string (None -> "", otherwise str(...)) instead of returning it raw,
    # which would just move the crash downstream.
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    if len(text) > limit:
        return text[:limit] + f"\n... (truncated, {len(text)} chars total)"
    return text

# ---------------------------------------------------------------------------
# Re-exports from sub-modules
# ---------------------------------------------------------------------------

# Parsing
# Execution
from core.tools.execution import (  # noqa: E402, F401
    execute_tool_block,
    format_tool_result,
)

# Implementations
from core.tools.implementations import (  # noqa: E402, F401
    do_api_call,
    do_create_document,
    do_edit_document,
    do_manage_documents,
    do_manage_endpoints,
    do_manage_mcp,
    do_manage_settings,
    do_manage_skills,
    do_manage_tasks,
    do_manage_tokens,
    do_manage_webhooks,
    do_search_chats,
    do_suggest_document,
    do_update_document,
    get_active_document,
    set_active_document,
    set_active_model,
)
from core.tools.parsing import (  # noqa: E402, F401
    _TOOL_BLOCK_RE,
    _TOOL_CALL_RE,
    _TOOL_NAME_MAP,
    _XML_INVOKE_RE,
    _XML_PARAM_RE,
    _XML_TOOL_CALL_RE,
    parse_tool_blocks,
    strip_tool_blocks,
)

# Schemas
from core.tools.schemas import (  # noqa: E402, F401
    FUNCTION_TOOL_SCHEMAS,
    function_call_to_tool_block,
)
