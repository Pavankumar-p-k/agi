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
import logging

logger = logging.getLogger(__name__)


async def dispatch_ai_tool(
    tool: str,
    content: str,
    session_id: str | None = None,
    owner: str | None = None,
) -> tuple[str, dict]:
    logger.debug(f"AI tool dispatch: {tool} (no native handler available)")
    desc = f"{tool}: (unavailable)"
    result = {"output": f"Tool '{tool}' is not available in this build", "exit_code": 1}
    return desc, result


async def _resolve_model(owner: str = "") -> str | None:
    return None
