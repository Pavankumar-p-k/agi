from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

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
    allowed_origins: List[str] = field(default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:8000"])
    firebase_credentials: str = ""


@dataclass
class DatabaseConfig:
    url: str = f"sqlite+aiosqlite:///{(DATA_DIR / 'jarvis.db').as_posix()}"


@dataclass
class OllamaConfig:
    url: str = "http://localhost:11434"
    default_model: str = "llama3"
    ports: Dict[str, int] = field(default_factory=lambda: {
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
    directories: List[str] = field(default_factory=lambda: ["plugins/", "core/plugins/", "skills/library/"])
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
    
    # Subagent spawning limits
    max_spawn_depth: int = 5
    max_child_agents: int = 10
    orphan_grace_period_seconds: int = 300


@dataclass
class LLMFallback:
    endpoint_id: str
    model: str


@dataclass
class LLMConfig:
    chat_model: str = "ollama/llama3.1:8b"
    code_model: str = "openai/gpt-4o"
    analysis_model: str = "anthropic/claude-sonnet-4-20250514"
    reasoning_model: str = "gemini/gemini-2.5-flash"
    vision_model: str = "openai/gpt-4o"

    default_endpoint_id: str = "ollama"
    default_model: str = "llama3.1:8b"
    default_model_fallbacks: List[LLMFallback] = field(default_factory=list)

    utility_endpoint_id: str = "ollama"
    utility_model: str = "llama3"
    utility_model_fallbacks: List[LLMFallback] = field(default_factory=list)

    research_endpoint_id: str = "openai"
    research_model: str = "gpt-4o"

    vision_enabled: bool = True
    vision_model_fallbacks: List[str] = field(default_factory=list)

    agent_max_tool_calls: int = 0
    agent_input_token_budget: int = 6000
    agent_input_token_hard_max: int = 200000
    agent_stream_timeout_seconds: int = 300

    hybrid_max_retries: int = 3
    hybrid_timeout_seconds: int = 30


@dataclass
class SearchConfig:
    provider: str = "searxng"
    fallback_chain: List[str] = field(default_factory=lambda: ["duckduckgo"])
    url: str = ""
    result_count: int = 5
    safesearch: str = "strict"

    brave_api_key: Optional[str] = None
    google_pse_key: Optional[str] = None
    google_pse_cx: Optional[str] = None
    tavily_api_key: Optional[str] = None
    serper_api_key: Optional[str] = None


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
    tts_provider: str = "disabled"
    tts_model: str = "tts-1"
    tts_voice: str = "alloy"
    tts_speed: float = 1.0


@dataclass
class SandboxPolicy:
    allow_tools: List[str] = field(default_factory=lambda: ["*"])
    deny_tools: List[str] = field(default_factory=list)
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
    enabled: bool = False
    profiles: List[AuthProfile] = field(default_factory=list)
    max_retries_per_profile: int = 2
    retry_delay_seconds: float = 1.0
    auto_discovery: bool = True
    cooldown_backoff_base: int = 60


_SUB_CONFIGS = {
    "server": ServerConfig,
    "db": DatabaseConfig,
    "ollama": OllamaConfig,
    "plugins": PluginConfig,
    "hardware": HardwareConfig,
    "build": BuildSystemConfig,
    "llm": LLMConfig,
    "search": SearchConfig,
    "research": ResearchConfig,
    "features": FeatureConfig,
    "voice": VoiceConfig,
    "sandbox": SandboxConfig,
    "failover": FailoverConfig,
}



def _coerce_type(val, target_type):
    if target_type is bool:
        if isinstance(val, str):
            return val.lower() in ("1", "true", "yes", "on")
        return bool(val)
    if val == "null":
        return None
    return val


def _dataclass_from_dict(cls, data: dict):
    """Recursively build a dataclass from a dict, handling nested dataclasses."""
    kw = {}
    for f in fields(cls):
        if f.name not in data:
            continue
        val = data[f.name]
        ftype = f.type
        if hasattr(ftype, "__origin__"):
            origin = ftype.__origin__
            if origin is list and hasattr(ftype.__args__[0], "__dataclass_fields__"):
                kw[f.name] = [_dataclass_from_dict(ftype.__args__[0], item) for item in val]
                continue
            if origin is dict:
                kw[f.name] = val
                continue
        if hasattr(ftype, "__dataclass_fields__"):
            kw[f.name] = _dataclass_from_dict(ftype, val) if isinstance(val, dict) else val
        else:
            kw[f.name] = _coerce_type(val, ftype)
    return cls(**kw)


def _deep_merge(base: dict, update: dict):
    for k, v in update.items():
        if isinstance(v, dict) and k in base and isinstance(base[k], dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


def _map_flat_settings(sdata: dict) -> dict:
    """Map flat settings.json keys to nested structure for backward compat."""
    mapped: dict = {}
    for key, val in sdata.items():
        seg = key.split("_", 1)
        if len(seg) == 2 and seg[0] in _SUB_CONFIGS:
            mapped.setdefault(seg[0], {})[seg[1]] = val
        else:
            mapped[key] = val
    return mapped


class JarvisConfig:
    """Unified configuration for JARVIS.

    Loads from multiple sources with override priority:
      1. config.yaml
      2. data/settings.json  (deprecated, backward compat)
      3. Environment variables (JARVIS_ prefix)
      4. Programmatic overrides
    """

    def __init__(self, overrides: Optional[dict] = None):
        merged = self._load_all()
        if overrides:
            _deep_merge(merged, overrides)
        for name, cls in _SUB_CONFIGS.items():
            setattr(self, name, _dataclass_from_dict(cls, merged.get(name, {})))
            
        # Top-level attributes for backward compat and easy access
        self.claude_api_key = self.get_api_key("CLAUDE_API_KEY")
        self.openai_api_key = self.get_api_key("OPENAI_API_KEY")
        self.gemini_api_key = self.get_api_key("GEMINI_API_KEY")
        self.github_token = self.get_api_key("GITHUB_TOKEN")
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_service_key = os.getenv("SUPABASE_SERVICE_KEY")

    def _load_all(self) -> dict:
        merged: dict = {}

        yaml_path = BASE_DIR / "config.yaml"
        if yaml_path.exists():
            try:
                import yaml
                with open(yaml_path, "r") as f:
                    ydata = yaml.safe_load(f)
                    if ydata:
                        _deep_merge(merged, ydata)
            except Exception as _e1:
                logger.debug("merge_yaml: yaml load failed: %s", _e1)

        settings_path = DATA_DIR / "settings.json"
        if settings_path.exists():
            try:
                with open(settings_path, "r") as f:
                    sdata = json.load(f)
                    if sdata:
                        _deep_merge(merged, _map_flat_settings(sdata))
            except Exception as _e2:
                logger.debug("merge_settings: json load failed: %s", _e2)

        features_path = DATA_DIR / "features.json"
        if features_path.exists():
            try:
                with open(features_path, "r") as f:
                    fdata = json.load(f)
                    if fdata:
                        _deep_merge(merged, {"features": fdata})
            except Exception as _e3:
                logger.debug("merge_features: json load failed: %s", _e3)

        for key, val in os.environ.items():
            if key.startswith("JARVIS_"):
                self._apply_env(merged, key.removeprefix("JARVIS_").lower(), val)

        return merged

    @staticmethod
    def _apply_env(target: dict, key: str, val: str):
        """Apply a JARVIS_* env var into the config dict handling nested keys."""
        parts = key.split("__", 1)
        if len(parts) == 2:
            target.setdefault(parts[0], {})
            if isinstance(target[parts[0]], dict):
                target[parts[0]][parts[1]] = val
            else:
                target[parts[0]] = {parts[1]: val}
        else:
            target[parts[0]] = val

    @classmethod
    def load(cls, overrides: Optional[dict] = None) -> "JarvisConfig":
        return cls(overrides)

    def get_api_key(self, name: str) -> Optional[str]:
        return os.getenv(name.upper()) or os.getenv(f"JARVIS_{name.upper()}")


jarvis_config = JarvisConfig.load()

__all__ = ["jarvis_config", "JarvisConfig"]
