# core/tools/execution/__init__.py
# Public API for the execution package.
# All symbols previously exported from core.tools.execution are re-exported
# here explicitly. This is the frozen stable interface.

# Constants (re-exported for backward compat)
from core.tools._constants import MAX_OUTPUT_CHARS, MAX_READ_CHARS

# Security
from core.tools.execution.security import (
    _is_sensitive_path,
    _resolve_tool_path,
    _tool_path_roots,
)

# Subprocess
from core.tools.execution.subprocess import (
    _run_subprocess_streaming,
    DEFAULT_BASH_TIMEOUT,
    DEFAULT_PYTHON_TIMEOUT,
)

# Plugins
from core.tools.execution.plugins import (
    _PLUGIN_TOOL_HANDLERS,
    register_plugin_tool,
    unregister_plugin_tool,
)

# MCP
from core.tools.execution.mcp import (
    _MCP_TOOL_MAP,
    _call_mcp_tool,
    get_mcp_manager,
)

# Authorization
from core.tools.execution.authorization import (
    check_approval,
    check_rbac,
)

# Metrics
from core.tools.execution.metrics import (
    record_tool_metric,
)

# Direct tools (bash, python, file I/O, web)
from core.tools.execution.direct_tools import (
    _BG_MARKERS,
    _direct_fallback,
    _split_bg_marker,
    _truncate,
)

# Edit tools
from core.tools.execution.edit_tools import (
    _get_backup_dir,
    _generate_refactor_plan,
    do_batch_edit_file,
    do_edit_file,
    do_refactor,
    do_undo_edit_file,
)

# Handlers (main dispatch)
from core.tools.execution.handlers import (
    _ADMIN_TOOLS,
    _ensure_browser_artifact_dir,
    _owner_is_admin,
    _register_email_artifact,
    _resolve_artifact_attachments,
    BROKEN_TOOLS,
    execute_tool_block,
    get_registered_tools,
)

# Formatting
from core.tools.execution.formatting import (
    _detect_errors,
    _ERROR_PATTERNS,
    _FORMATTER_HANDLED_KEYS,
    format_tool_result,
)

__all__ = [
    "BROKEN_TOOLS",
    "DEFAULT_BASH_TIMEOUT",
    "DEFAULT_PYTHON_TIMEOUT",
    "MAX_OUTPUT_CHARS",
    "MAX_READ_CHARS",
    "_ADMIN_TOOLS",
    "_BG_MARKERS",
    "_ERROR_PATTERNS",
    "_FORMATTER_HANDLED_KEYS",
    "_MCP_TOOL_MAP",
    "_PLUGIN_TOOL_HANDLERS",
    "_call_mcp_tool",
    "_detect_errors",
    "_direct_fallback",
    "_ensure_browser_artifact_dir",
    "_generate_refactor_plan",
    "_get_backup_dir",
    "_is_sensitive_path",
    "_owner_is_admin",
    "_register_email_artifact",
    "_resolve_artifact_attachments",
    "_resolve_tool_path",
    "_run_subprocess_streaming",
    "_split_bg_marker",
    "_tool_path_roots",
    "_truncate",
    "check_approval",
    "check_rbac",
    "do_batch_edit_file",
    "do_edit_file",
    "do_refactor",
    "do_undo_edit_file",
    "execute_tool_block",
    "format_tool_result",
    "get_mcp_manager",
    "record_tool_metric",
    "register_plugin_tool",
    "unregister_plugin_tool",
]
