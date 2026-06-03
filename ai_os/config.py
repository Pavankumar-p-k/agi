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
