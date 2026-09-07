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
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ToolResult:
    output: str = ""
    error: str | None = None
    retryable: bool = False

    def is_ok(self) -> bool:
        return self.error is None


@dataclass
class ToolDefinition:
    name: str
    description: str
    category: str = "general"
    input_schema: dict[str, Any] = field(default_factory=dict)
    handler: Callable | None = None
    read_only: bool = False
    risk_tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    permission: str | None = None
    capabilities: list[str] = field(default_factory=list)
    examples: list[dict] | None = None
