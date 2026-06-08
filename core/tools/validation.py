import json
import logging
from typing import Optional

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)


class BashArgs(BaseModel):
    model_config = {"populate_by_name": True}
    code: str = Field(alias="command")


class PythonArgs(BaseModel):
    model_config = {"populate_by_name": True}
    code: str


class ReadFileArgs(BaseModel):
    model_config = {"populate_by_name": True}
    path: str


class WriteFileArgs(BaseModel):
    model_config = {"populate_by_name": True}
    path: str
    content: str


class WebSearchArgs(BaseModel):
    model_config = {"populate_by_name": True}
    query: str
    queries: Optional[list[str]] = None
    time_filter: Optional[str] = None


class WebFetchArgs(BaseModel):
    model_config = {"populate_by_name": True}
    url: str


class ManageMemoryArgs(BaseModel):
    model_config = {"populate_by_name": True}
    action: str
    text: Optional[str] = None
    memory_id: Optional[str] = None
    category: Optional[str] = None


class EditDocumentArgs(BaseModel):
    model_config = {"populate_by_name": True}
    edits: list[dict]


class UIControlArgs(BaseModel):
    model_config = {"populate_by_name": True}
    action: str
    name: Optional[str] = None
    value: Optional[str] = None
    uid: Optional[str] = None
    folder: Optional[str] = None
    mode: Optional[str] = None
    colors: Optional[dict] = None


class ManageSessionArgs(BaseModel):
    model_config = {"populate_by_name": True}
    action: str
    session_id: Optional[str] = None
    value: Optional[str] = None
    keyword: Optional[str] = None


_VALIDATION_MODEL_MAP = {
    "bash": BashArgs,
    "python": PythonArgs,
    "read_file": ReadFileArgs,
    "write_file": WriteFileArgs,
    "web_search": WebSearchArgs,
    "web_fetch": WebFetchArgs,
    "manage_memory": ManageMemoryArgs,
    "edit_document": EditDocumentArgs,
    "ui_control": UIControlArgs,
    "manage_session": ManageSessionArgs,
}


def validate_tool_call(name: str, args: dict) -> tuple[bool, Optional[str]]:
    """Validate tool call arguments against the matching Pydantic model.

    Returns (is_valid, error_message). Unknown tools pass through as valid.
    """
    model_cls = _VALIDATION_MODEL_MAP.get(name)
    if model_cls is None:
        return True, None
    try:
        model_cls(**args)
        return True, None
    except ValidationError as e:
        return False, str(e)


def try_parse_partial_json(s: str) -> Optional[dict]:
    """Attempt to parse partial/incomplete JSON from streaming tool calls.

    Tries a plain parse first. On failure, attempts to repair by appending
    closing brackets and braces. Returns None if all attempts fail.
    """
    if not isinstance(s, str) or not s.strip():
        return None
    s = s.strip()
    try:
        return json.loads(s)
    except (json.JSONDecodeError, ValueError):
        pass

    closers = []
    stack = []
    for ch in s:
        if ch in ("{", "["):
            stack.append(ch)
        elif ch == "}":
            if stack and stack[-1] == "{":
                stack.pop()
        elif ch == "]":
            if stack and stack[-1] == "[":
                stack.pop()
    for ch in reversed(stack):
        closers.append("}" if ch == "{" else "]")

    candidates = [s + "".join(closers)]
    if closers:
        candidates.append(s + "}")
        if len(closers) > 1:
            candidates.append(s + "]")

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            continue

    return None
