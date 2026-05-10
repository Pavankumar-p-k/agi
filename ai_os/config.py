import os
from dataclasses import dataclass, field

@dataclass
class AIOSConfig:
    ollama_host: str = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    planner_model: str = os.getenv("AIOS_PLANNER_MODEL", "qwen2.5-coder:3b")
    reasoning_model: str = os.getenv("AIOS_REASONING_MODEL", "llama3.1:8b")
    fast_model: str = os.getenv("AIOS_FAST_MODEL", "phi3:mini")
    coder_model: str = os.getenv("AIOS_CODER_MODEL", "qwen3:4b")
    lightweight_model: str = os.getenv("AIOS_LIGHT_MODEL", "tinyllama:latest")
    tool_policy_allow_apps: list[str] = field(default_factory=lambda: ["notepad.exe", "mspaint.exe"])
    tool_policy_block_words: list[str] = field(default_factory=lambda: ["rm -rf", "del ", "format "])
    sqlite_path: str = os.getenv("AIOS_MEMORY_DB", "ai_os_memory.db")
    max_response_tokens: int = int(os.getenv("AIOS_MAX_RESPONSE_TOKENS", "512"))
    verbose: bool = os.getenv("AIOS_VERBOSE", "1") != "0"
