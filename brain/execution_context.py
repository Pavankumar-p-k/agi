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
from typing import Any, Dict, List, Optional


@dataclass
class BrainExecutionContext:
    goal: str = ""
    prompt: Optional[str] = None
    user_id: str = "system"
    session_id: str = "root"
    platform: str = "chat"
    context: Dict[str, Any] = field(default_factory=dict)
    variables: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    permissions: List[str] = field(default_factory=lambda: ["read", "execute"])
    working_directory: Optional[str] = None
    timeout: int = 300
    max_retries: int = 3

    @property
    def effective_prompt(self) -> str:
        return self.prompt or self.goal or ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "prompt": self.prompt,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "platform": self.platform,
            "context": self.context,
            "variables": self.variables,
            "metadata": self.metadata,
            "permissions": self.permissions,
            "working_directory": self.working_directory,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
        }
