"""core.tools package: execution dispatch, built-in implementations, parsing.

De-poisoned: the package init previously fabricated a DynamicStub for any
unknown attribute, which masked missing exports and (worse) could shadow real
submodules.  Attribute resolution is now:

1. Real re-exports below (execution + implementations + parsing/index/schemas/security).
2. Submodule fallback via importlib (``from core.tools import browser_tools``
   keeps working even before the submodule is imported anywhere).
3. Otherwise a normal AttributeError — missing names fail loudly.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Re-exports (real modules only)
from core.tools.execution import (  # noqa: F401
    _run_subprocess_streaming,
    execute_tool_block,
    register_plugin_tool,
    unregister_plugin_tool,
)
from core.tools.implementations import (  # noqa: F401
    async_do_api_call,
    async_do_browser_screenshot,
    async_do_browser_snapshot,
    async_do_search_chats,
    do_api_call,
    do_browser_screenshot,
    do_browser_snapshot,
    do_search_chats,
)
from core.tools.index import (  # noqa: F401
    ALWAYS_AVAILABLE,
    BUILTIN_TOOL_DESCRIPTIONS,
    ToolIndex,
)
from core.tools.parsing import (  # noqa: F401
    _TOOL_NAME_MAP,
    ToolBlock,
    parse_tool_blocks,
    strip_tool_blocks,
)
from core.tools.schemas import (  # noqa: F401
    FUNCTION_TOOL_SCHEMAS,
    function_call_to_tool_block,
)
from core.tools.security import (  # noqa: F401
    NON_ADMIN_BLOCKED_TOOLS,
    blocked_tools_for_owner,
    is_public_blocked_tool,
    owner_is_admin_or_single_user,
)


def __getattr__(name: str):
    # Submodule fallback: `from core.tools import <submodule>` must yield the
    # real module even when not yet imported (Python >= 3.7 behaviour).
    import importlib

    try:
        module = importlib.import_module(f"{__name__}.{name}")
    except ImportError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    globals()[name] = module
    return module
