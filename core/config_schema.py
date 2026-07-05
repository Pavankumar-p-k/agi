"""DEPRECATED — use `core.configuration.configuration` (ConfigurationService) instead.

This module is a backward-compatibility shim. All configuration reads are
delegated to the canonical ConfigurationService at runtime.
"""
from __future__ import annotations

import json
import logging
import os
import warnings
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_warned = False


def _warn() -> None:
    global _warned
    if not _warned:
        warnings.warn(
            "core.config_schema is deprecated. "
            "Use 'from core.configuration import configuration' instead.",
            DeprecationWarning, stacklevel=3,
        )
        _warned = True


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"


def _resolve_path(path: str) -> str:
    p = Path(path)
    return str(p if p.is_absolute() else BASE_DIR / p)


@dataclass
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8000
    secret_key: str = ""
    dev_mode: bool = True
    allowed_origins: list[str] = field(default_factory=lambda: ["http://localhost:3000"])
    firebase_credentials: str = ""


@dataclass
class DatabaseConfig:
    url: str = f"sqlite+aiosqlite:///{(DATA_DIR / 'jarvis.db').as_posix()}"


@dataclass
class OllamaConfig:
    url: str = "http://localhost:11434"
    default_model: str = "qwen2.5:7b"
    ports: dict[str, int] = field(default_factory=lambda: {
        "tinyllama": 11434,
        "deepseek-r1:1.5b": 11434,
        "qwen2.5-coder:3b": 11434,
        "qwen3:4b": 11434,
        "qwen2.5:7b": 11434,
        "mistral:7b": 11434,
        "llama3.1:8b": 11434,
        "phi3:mini": 11434,
        "moondream": 11434,
    })


@dataclass
class PluginConfig:
    hot_reload_enabled: bool = True
    poll_interval: float = 2.0
    directories: list[str] = field(default_factory=lambda: ["plugins/", "core/plugins/", "skills/library/"])
    config_dir: str = "data/plugin_configs"


@dataclass
class HardwareConfig:
    faces_dir: str = str(DATA_DIR / "faces")
    face_recognition_model: str = "VGG-Face"
    face_detection_backend: str = "opencv"
    face_distance_threshold: float = 0.38
    music_dir: str = str(Path.home() / "Music")
    vosk_model_path: str = str(BASE_DIR / "models" / "vosk-model-small-en-us-0.15")


@dataclass
class BuildSystemConfig:
    max_retries: int = 5
    daemon_mode: bool = False
    vault_path: str = str(Path.home() / ".jarvis" / "api_keys.json")
    max_parallel_builds: int = 2
    projects_dir: str = str(Path.home() / ".jarvis" / "projects")
    codex_cli_path: str = str(BASE_DIR / "tools" / "codex-cli")

    max_spawn_depth: int = 5
    max_child_agents: int = 10
    orphan_grace_period_seconds: int = 300


@dataclass
class LLMFallback:
    endpoint_id: str
    model: str


@dataclass
class LLMConfig:
    chat_model: str = "ollama/qwen2.5:7b"
    code_model: str = "ollama/qwen2.5:7b"
    analysis_model: str = "ollama/qwen2.5:7b"
    reasoning_model: str = "ollama/deepseek-r1:1.5b"
    vision_model: str = "ollama/moondream:latest"

    default_endpoint_id: str = "ollama"
    default_model: str = "ollama/qwen2.5:7b"
    default_model_fallbacks: list[LLMFallback] = field(default_factory=list)

    utility_endpoint_id: str = "ollama"
    utility_model: str = "llama3"
    utility_model_fallbacks: list[LLMFallback] = field(default_factory=list)

    research_endpoint_id: str = "ollama"
    research_model: str = "llama3.1:8b"

    vision_enabled: bool = True
    vision_model_fallbacks: list[str] = field(default_factory=list)

    agent_max_tool_calls: int = 0
    agent_input_token_budget: int = 6000
    agent_input_token_hard_max: int = 200000
    agent_stream_timeout_seconds: int = 300

    hybrid_max_retries: int = 3
    hybrid_timeout_seconds: int = 30


@dataclass
class SearchConfig:
    provider: str = "searxng"
    fallback_chain: list[str] = field(default_factory=lambda: ["duckduckgo"])
    url: str = ""
    result_count: int = 5
    safesearch: str = "strict"

    brave_api_key: str | None = None
    google_pse_key: str | None = None
    google_pse_cx: str | None = None
    tavily_api_key: str | None = None
    serper_api_key: str | None = None


@dataclass
class ResearchConfig:
    max_tokens: int = 16384
    extraction_timeout_seconds: int = 90
    extraction_concurrency: int = 3
    run_timeout_seconds: int = 1800


@dataclass
class FeatureConfig:
    web_search: bool = True
    web_fetch: bool = True
    deep_research: bool = False
    memory: bool = True
    document_editor: bool = True
    rag: bool = True
    sensitive_filter: bool = True
    gallery: bool = True


@dataclass
class VoiceConfig:
    stt_enabled: bool = False
    stt_provider: str = "disabled"
    stt_model: str = "base"
    stt_language: str = "en"

    tts_enabled: bool = True
    tts_provider: str = "edge-tts"
    tts_model: str = "tts-1"
    tts_voice: str = "alloy"
    tts_speed: float = 1.0


@dataclass
class BrowserConfig:
    headed: bool = True
    timeout: int = 30000
    viewport_width: int = 1280
    viewport_height: int = 720
    session_timeout: int = 1800


@dataclass
class SandboxPolicy:
    allow_tools: list[str] = field(default_factory=lambda: ["*"])
    deny_tools: list[str] = field(default_factory=list)
    allow_network: bool = False
    allow_bind_mounts: bool = False
    max_memory: str = "512m"
    max_cpu: float = 1.0
    timeout_seconds: int = 60


@dataclass
class SandboxConfig:
    enabled: bool = True
    use_persistent_containers: bool = True
    image: str = "python:3.11-slim"
    workspace_root: str = "data/sandbox_workspaces"
    browser_image: str = "mcr.microsoft.com/playwright:v1.44.0-jammy"
    gc_interval_seconds: int = 3600
    default_policy: SandboxPolicy = field(default_factory=SandboxPolicy)


@dataclass
class AuthProfile:
    name: str
    api_key: str
    provider: str
    priority: int = 10
    cooldown_seconds: int = 300


@dataclass
class FailoverConfig:
    enabled: bool = True
    profiles: list[AuthProfile] = field(default_factory=list)
    max_retries_per_profile: int = 2
    retry_delay_seconds: float = 1.0
    auto_discovery: bool = True
    cooldown_backoff_base: int = 60


_SUB_CONFIG_NAMES: set[str] = {
    "server", "db", "ollama", "plugins", "hardware", "build",
    "llm", "search", "research", "features", "voice", "sandbox",
    "failover", "browser",
}

_SUB_CONFIG_DEFAULTS: dict[str, dataclass] = {
    "server": ServerConfig(),
    "db": DatabaseConfig(),
    "ollama": OllamaConfig(),
    "plugins": PluginConfig(),
    "hardware": HardwareConfig(),
    "build": BuildSystemConfig(),
    "llm": LLMConfig(),
    "search": SearchConfig(),
    "research": ResearchConfig(),
    "features": FeatureConfig(),
    "voice": VoiceConfig(),
    "sandbox": SandboxConfig(),
    "failover": FailoverConfig(),
    "browser": BrowserConfig(),
}


class _ConfigFieldProxy:
    """Proxies a single field read: tries ConfigurationService, falls back to default."""

    def __init__(self, prefix: str, fallback: Any):
        self._prefix = prefix
        self._fallback = fallback

    @property
    def _proxy(self) -> _ConfigFieldProxy:
        return self

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        full_key = f"{self._prefix}.{name}"
        try:
            from core.configuration import configuration
            val = configuration.get(full_key)
            if val is not None:
                return val
        except Exception:
            pass
        if hasattr(self._fallback, name):
            return getattr(self._fallback, name)
        raise AttributeError(f"Config has no key: {full_key}")

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            super().__setattr__(name, value)
            return
        full_key = f"{self._prefix}.{name}"
        try:
            from core.configuration import configuration
            configuration.set(full_key, value)
        except Exception:
            pass

    def __repr__(self) -> str:
        return f"<ConfigProxy {self._prefix}>"


class _LegacyTopLevelAttrs:
    """Provides backward-compat top-level attrs like claude_api_key, supabase_url."""

    @staticmethod
    def claude_api_key() -> str | None:
        return os.getenv("CLAUDE_API_KEY") or os.getenv("JARVIS_CLAUDE_API_KEY")

    @staticmethod
    def openai_api_key() -> str | None:
        return os.getenv("OPENAI_API_KEY") or os.getenv("JARVIS_OPENAI_API_KEY")

    @staticmethod
    def gemini_api_key() -> str | None:
        return os.getenv("GEMINI_API_KEY") or os.getenv("JARVIS_GEMINI_API_KEY")

    @staticmethod
    def github_token() -> str | None:
        return os.getenv("GITHUB_TOKEN") or os.getenv("JARVIS_GITHUB_TOKEN")

    @staticmethod
    def supabase_url() -> str | None:
        return os.getenv("SUPABASE_URL")

    @staticmethod
    def supabase_service_key() -> str | None:
        return os.getenv("SUPABASE_SERVICE_KEY")


_legacy_attrs = _LegacyTopLevelAttrs()


class JarvisConfig:
    """DEPRECATED — backward-compat shim over ConfigurationService.

    Access is routed to ConfigurationService at runtime with dataclass
    defaults as fallback. New code should use::

        from core.configuration import configuration
        configuration.get("server.host")
    """

    def __init__(self, overrides: dict | None = None) -> None:
        _warn()

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        if name in _SUB_CONFIG_NAMES:
            return _ConfigFieldProxy(name, _SUB_CONFIG_DEFAULTS[name])
        api_key = getattr(_legacy_attrs, name, None)
        if api_key is not None:
            return api_key() if callable(api_key) else api_key
        raise AttributeError(f"JarvisConfig has no attribute {name!r}")

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            super().__setattr__(name, value)
            return
        full_key = name
        try:
            from core.configuration import configuration
            configuration.set(full_key, value)
        except Exception:
            pass

    @classmethod
    def load(cls, overrides: dict | None = None) -> JarvisConfig:
        _warn()
        return cls(overrides)

    def get_api_key(self, name: str) -> str | None:
        return os.getenv(name.upper()) or os.getenv(f"JARVIS_{name.upper()}")


jarvis_config = JarvisConfig()

__all__ = ["jarvis_config", "JarvisConfig"]
