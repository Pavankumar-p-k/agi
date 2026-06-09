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

import os
from dataclasses import dataclass, field

@dataclass
class AIOSConfig:
    @property
    def _settings(self):
        from core.settings.store import get_settings_store
        return get_settings_store()

    @property
    def ollama_host(self) -> str:
        return self._settings.get("llm.ollama_host")
    
    @property
    def planner_model(self) -> str:
        return self._settings.get("llm.planner_model")
    
    @property
    def reasoning_model(self) -> str:
        return self._settings.get("llm.reasoning_model")
    
    @property
    def fast_model(self) -> str:
        return self._settings.get("llm.fast_model")
    
    @property
    def coder_model(self) -> str:
        return self._settings.get("llm.coder_model")
    
    @property
    def lightweight_model(self) -> str:
        return self._settings.get("llm.lightweight_model")
    
    tool_policy_allow_apps: list[str] = field(default_factory=lambda: ["notepad.exe", "mspaint.exe"])
    tool_policy_block_words: list[str] = field(default_factory=lambda: ["rm -rf", "del ", "format "])
    
    @property
    def sqlite_path(self) -> str:
        return self._settings.get("memory.db_path")
    
    @property
    def max_response_tokens(self) -> int:
        return self._settings.get("llm.max_response_tokens")
    
    @property
    def verbose(self) -> bool:
        return self._settings.get("ui.debug")
