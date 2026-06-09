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
import json
import logging

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
    queries: list[str] | None = None
    time_filter: str | None = None


class WebFetchArgs(BaseModel):
    model_config = {"populate_by_name": True}
    url: str


class ManageMemoryArgs(BaseModel):
    model_config = {"populate_by_name": True}
    action: str
    text: str | None = None
    memory_id: str | None = None
    category: str | None = None


class EditDocumentArgs(BaseModel):
    model_config = {"populate_by_name": True}
    edits: list[dict]


class UIControlArgs(BaseModel):
    model_config = {"populate_by_name": True}
    action: str
    name: str | None = None
    value: str | None = None
    uid: str | None = None
    folder: str | None = None
    mode: str | None = None
    colors: dict | None = None


class ManageSessionArgs(BaseModel):
    model_config = {"populate_by_name": True}
    action: str
    session_id: str | None = None
    value: str | None = None
    keyword: str | None = None


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


def validate_tool_call(name: str, args: dict) -> tuple[bool, str | None]:
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


def try_parse_partial_json(s: str) -> dict | None:
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
