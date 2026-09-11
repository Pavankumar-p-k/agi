import asyncio

from core.desktop.tool_bridge import register_desktop_tools
from tools.registry import ToolRegistry


def test_legacy_handlers_can_be_registered_without_changing_call_shape():
    def list_windows(limit=10):
        return f"windows:{limit}"

    registry = register_desktop_tools(
        ToolRegistry(),
        {"list_windows": list_windows},
        descriptions={"list_windows": "List desktop windows"},
    )

    result = asyncio.run(registry.execute("list_windows", {"limit": 2}))

    assert result.is_ok()
    assert result.output == "windows:2"
    assert registry.get("list_windows").category == "desktop"
    assert registry.get_capability("list_windows").owner_module == "Desktop AI"
