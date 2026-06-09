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

MAX_OUTPUT_CHARS = 10_000
MAX_READ_CHARS = 20_000


def get_mcp_manager():
    from core import agent_tools
    return agent_tools.get_mcp_manager()


def _truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) > limit:
        return text[:limit] + f"\n... (truncated, {len(text)} chars total)"
    return text


logger = logging.getLogger(__name__)


def _parse_tool_args(content):
    if isinstance(content, str):
        try:
            args = json.loads(content) if content.strip() else {}
        except (json.JSONDecodeError, TypeError) as e:
            raise ValueError(str(e))
    elif isinstance(content, dict):
        args = content
    else:
        args = {}
    if (
        isinstance(args, dict)
        and len(args) == 1
        and "body" in args
        and isinstance(args["body"], dict)
        and "action" in args["body"]
    ):
        args = args["body"]
    return args
