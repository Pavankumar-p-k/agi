import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.routes.system.tools_api import ToolExecuteRequest, get_tool_schema, list_tools


async def test_headless_tools_list_contains_native_tool():
    result = await list_tools()

    assert result["count"] > 0
    assert {"name": "list_models", "kind": "native"} in result["tools"]


async def test_headless_tool_schema_for_known_tool():
    result = await get_tool_schema("list_models")

    assert result["name"] == "list_models"
    assert result["kind"] == "native"
    assert "args" in result["input"]


def test_tool_execute_request_accepts_args_payload():
    req = ToolExecuteRequest(tool="list_models", args={})

    assert req.tool == "list_models"
    assert req.args == {}
