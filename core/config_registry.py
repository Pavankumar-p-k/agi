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
"""
core/config_registry.py — Config singleton with priority-chain resolution.

Priority: env var > settings.json > config.yaml > code default

Usage:
    from core.config_registry import config
    model = config.get("llm.chat_model")
    config.set("llm.chat_model", "ollama/mistral:7b")
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ── ConfigEntry ───────────────────────────────────────────────────────────────

@dataclass
class ConfigEntry:
    key: str
    default: Any
    type: str = "str"
    category: str = "general"
    description: str = ""
    ui: str = "input"
    env_var: Optional[str] = None
    options: Optional[list] = None
    options_provider: Optional[str] = None
    restart_required: bool = False
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    secret: bool = False


# ── The Registry ──────────────────────────────────────────────────────────────

_REGISTRY: list[ConfigEntry] = [
    # ── LLM models ────────────────────────────────────────────────────────
    ConfigEntry("llm.chat_model",        "ollama/llama3.1:8b",            "str",  "models",       "Chat completion model",            ui="model_select", env_var="CHAT_MODEL"),
    ConfigEntry("llm.code_model",        "ollama/qwen2.5-coder:3b",      "str",  "models",       "Code generation model",            ui="model_select", env_var="CODE_MODEL"),
    ConfigEntry("llm.analysis_model",    "ollama/qwen2.5:7b",            "str",  "models",       "Analysis/reasoning model",         ui="model_select", env_var="ANALYSIS_MODEL"),
    ConfigEntry("llm.reasoning_model",   "ollama/deepseek-r1:1.5b",      "str",  "models",       "Step-by-step reasoning model",     ui="model_select", env_var="REASONING_MODEL"),
    ConfigEntry("llm.vision_model",      "ollama/moondream:latest",      "str",  "models",       "Vision/image model",               ui="model_select", env_var="VISION_MODEL"),
    ConfigEntry("llm.embedding_model",   "ollama/nomic-embed-text:latest", "str", "models",      "Embedding model",                  ui="model_select", env_var="EMBEDDING_MODEL"),
    ConfigEntry("llm.grader_model",      "ollama/phi3:mini",              "str", "models",       "Quality grading model",            ui="model_select", env_var="GRADER_MODEL"),
    ConfigEntry("llm.orchestrator_model","ollama/qwen2.5:7b",            "str",  "models",       "Orchestrator/planner model",       ui="model_select", env_var="ORCHESTRATOR_MODEL"),
    ConfigEntry("llm.fallback_model",    "ollama/llama3.1:8b",           "str",  "models",       "Fallback when primary fails",      ui="model_select", env_var="FALLBACK_MODEL"),
    ConfigEntry("llm.cloud_model",       "",                              "str",  "models",       "Cloud model override (e.g. claude-sonnet-4-20250514)", ui="model_select"),
    ConfigEntry("llm.ping_model",        "tinyllama",                     "str",  "models",       "Small model for health checks",    ui="hidden"),

    # ── Model groups ──────────────────────────────────────────────────────
    ConfigEntry("model_groups.reasoning_group", "chat", "str", "models", "Model group used by reasoning engine", ui="select", options=["chat","reasoning","analysis"], env_var="REASONING_MODEL_GROUP"),

    # ── Role models ───────────────────────────────────────────────────────
    ConfigEntry("role_models.default",   "ollama/llama3.1:8b",            "str",  "models",       "Default role model",               ui="model_select"),

    # ── Ollama ────────────────────────────────────────────────────────────
    ConfigEntry("ollama.base_url",       "http://localhost:11434",        "str",  "ollama",       "Ollama server URL",                env_var="OLLAMA_BASE_URL"),
    ConfigEntry("ollama.timeout",        120,                              "int",  "ollama",       "Ollama request timeout seconds",   env_var="OLLAMA_TIMEOUT", min_value=5, max_value=600),
    ConfigEntry("ollama.keep_alive",     "5m",                             "str",  "ollama",       "Keep model loaded duration",       env_var="OLLAMA_KEEP_ALIVE"),

    # ── Server ────────────────────────────────────────────────────────────
    ConfigEntry("server.host",           "127.0.0.1",                     "str",  "server",       "HTTP server bind address",         env_var="JARVIS_HOST"),
    ConfigEntry("server.port",           8000,                             "int",  "server",       "HTTP server port",                 env_var="JARVIS_PORT", min_value=1, max_value=65535),
    ConfigEntry("server.dev_mode",       True,                             "bool", "server",       "Development mode",                 env_var="JARVIS_DEV_MODE"),
    ConfigEntry("server.secret_key",     "",                               "str",  "server",       "Server secret key (set via env)",  env_var="JARVIS_SECRET_KEY", secret=True),

    # ── Voice ─────────────────────────────────────────────────────────────
    ConfigEntry("voice.tts_provider",    "edge-tts",                      "str",  "voice",        "TTS provider (edge-tts, pyttsx3)", ui="select", options=["edge-tts", "pyttsx3", "none"], env_var="TTS_PROVIDER"),
    ConfigEntry("voice.tts_voice",       "en-US-ChristopherNeural",       "str",  "voice",        "TTS voice name",                   env_var="TTS_VOICE"),
    ConfigEntry("voice.stt_provider",    "faster-whisper",                "str",  "voice",        "STT provider",                     ui="select", options=["faster-whisper", "whisper", "google", "none"], env_var="STT_PROVIDER"),
    ConfigEntry("voice.stt_model",       "small",                          "str",  "voice",        "STT model size",                   ui="select", options=["tiny", "small", "medium", "large"], env_var="STT_MODEL"),
    ConfigEntry("voice.wake_word",       "hey jarvis",                    "str",  "voice",        "Wake word phrase",                 env_var="WAKE_WORD"),
    ConfigEntry("voice.wake_word_enabled", True,                          "bool", "voice",        "Enable wake word detection",       env_var="WAKE_WORD_ENABLED"),
    ConfigEntry("voice.mic_device",      "",                               "str",  "voice",        "Microphone device index (empty=default)"),
    ConfigEntry("voice.vad_threshold",   0.5,                             "float","voice",        "Voice activity detection threshold", min_value=0.0, max_value=1.0),
    ConfigEntry("voice.system_prompt",   "",                               "str",  "voice",        "Custom system prompt for voice mode"),
    ConfigEntry("voice.record_seconds",  5,                                "int",  "voice",        "Seconds to record per utterance",  min_value=1, max_value=30),
    ConfigEntry("voice.sample_rate",     16000,                            "int",  "voice",        "Audio sample rate",                min_value=8000, max_value=48000),
    ConfigEntry("voice.think_timeout",   10,                               "int",  "voice",        "Voice LLM call timeout (seconds)", min_value=1, max_value=120),
    ConfigEntry("voice.think_timeout_fallback", 15,                        "int",  "voice",        "Voice LLM fallback timeout (seconds)", min_value=1, max_value=120),
    ConfigEntry("voice.vad_mode",            3,                             "int",  "voice",        "WebRTC VAD aggressiveness (0-3)",  min_value=0, max_value=3),
    ConfigEntry("voice.energy_threshold",    0.008,                         "float","voice",        "VAD energy threshold",             min_value=0.0, max_value=1.0),
    ConfigEntry("voice.require_speech_seconds", 1.2,                        "float","voice",        "Min speech duration for wake detection", min_value=0.1, max_value=10.0),
    ConfigEntry("voice.wake_cooldown_trigger",5.0,                          "float","voice",        "Cooldown after wake word trigger (seconds)", min_value=0.0, max_value=30.0),
    ConfigEntry("voice.wake_cooldown_skip",   3.0,                          "float","voice",        "Cooldown after wake word skip (seconds)", min_value=0.0, max_value=30.0),
    ConfigEntry("voice.ring_buffer_seconds",  4.0,                          "float","voice",        "Audio ring buffer length (seconds)", min_value=1.0, max_value=30.0),

    # ── Failover ──────────────────────────────────────────────────────────
    ConfigEntry("failover.enabled",         False,   "bool", "failover",  "Enable cloud failover providers",  env_var="FAILOVER_ENABLED"),
    ConfigEntry("failover.openai_api_key",  "",      "str",  "failover",  "OpenAI API key for failover",      env_var="OPENAI_API_KEY", secret=True),
    ConfigEntry("failover.anthropic_api_key","",     "str",  "failover",  "Anthropic API key for failover",   env_var="ANTHROPIC_API_KEY", secret=True),
    ConfigEntry("failover.openai_model",    "gpt-4o-mini", "str", "failover", "OpenAI failover model",         ui="model_select", env_var="FAILOVER_OPENAI_MODEL"),
    ConfigEntry("failover.anthropic_model", "claude-3-haiku-20240307", "str", "failover", "Anthropic failover model", ui="model_select", env_var="FAILOVER_ANTHROPIC_MODEL"),
    ConfigEntry("failover.cooldown_seconds", 60,    "int",  "failover",  "Cooldown after failure",           env_var="FAILOVER_COOLDOWN", min_value=0, max_value=3600),
    ConfigEntry("failover.max_retries",      3,      "int",  "failover",  "Max retries per provider",         env_var="FAILOVER_MAX_RETRIES", min_value=0, max_value=10),

    # ── Brain / Reasoning ─────────────────────────────────────────────────
    ConfigEntry("brain.reasoning_timeout",      60,   "int",   "reasoning", "Reasoning engine timeout seconds",        env_var="REASONING_TIMEOUT", min_value=5, max_value=300),
    ConfigEntry("brain.max_reasoning_loops",    3,     "int",   "reasoning", "Max reasoning loops before giving up",   env_var="MAX_REASONING_LOOPS", min_value=1, max_value=20),
    ConfigEntry("brain.enable_critique",        True,  "bool",  "reasoning", "Enable self-critique in reasoning",      env_var="ENABLE_CRITIQUE"),
    ConfigEntry("brain.critique_threshold",     0.7,   "float", "reasoning", "Critique acceptance threshold",          env_var="CRITIQUE_THRESHOLD", min_value=0.0, max_value=1.0),

    # ── Tools ─────────────────────────────────────────────────────────────
    ConfigEntry("tools.bash_timeout",         3600,   "int",   "tools",     "Bash command timeout seconds",          env_var="BASH_TIMEOUT", min_value=1, max_value=86400),
    ConfigEntry("tools.python_timeout",       300,    "int",   "tools",     "Python execution timeout seconds",      env_var="PYTHON_TIMEOUT", min_value=1, max_value=86400),
    ConfigEntry("tools.max_output_chars",     50000,  "int",   "tools",     "Max tool output characters",            env_var="MAX_OUTPUT_CHARS", min_value=1000, max_value=500000),

    # ── Memory ────────────────────────────────────────────────────────────
    ConfigEntry("memory.provider",           "mem0",  "str",   "memory",    "Memory provider",                   ui="select", options=["mem0", "chroma", "simple"], env_var="MEMORY_PROVIDER"),
    ConfigEntry("memory.recall_limit",       10,      "int",   "memory",    "Max memory recall results",         env_var="MEMORY_RECALL_LIMIT", min_value=1, max_value=100),
    ConfigEntry("memory.auto_prune",         True,    "bool",  "memory",    "Auto-prune old memories",          env_var="MEMORY_AUTO_PRUNE"),

    # ── Plugins ───────────────────────────────────────────────────────────
    ConfigEntry("plugins.hot_reload",        True,    "bool",  "plugins",   "Hot reload plugins on file change", env_var="PLUGIN_HOT_RELOAD"),
    ConfigEntry("plugins.poll_interval",     2.0,     "float", "plugins",   "Plugin directory poll interval (s)", env_var="PLUGIN_POLL_INTERVAL", min_value=0.5, max_value=30.0),

    # ── Logging ───────────────────────────────────────────────────────────
    ConfigEntry("logging.level",             "INFO",  "str",   "logging",   "Log level",                         ui="select", options=["DEBUG","INFO","WARNING","ERROR"], env_var="LOG_LEVEL"),
    ConfigEntry("logging.max_bytes",         10485760, "int", "logging",    "Log file max bytes before rotation", env_var="LOG_MAX_BYTES"),
    ConfigEntry("logging.backup_count",      5,        "int", "logging",    "Log file backup count",              env_var="LOG_BACKUP_COUNT"),

    # ── Monitoring ─────────────────────────────────────────────────────────
    ConfigEntry("monitor.check_interval",    60,       "int", "monitor",    "Environment monitor check interval (s)", min_value=5, max_value=3600),
]

_REGISTRY_MAP: dict[str, ConfigEntry] = {e.key: e for e in _REGISTRY}


# ── Helpers ───────────────────────────────────────────────────────────────────

def all_categories() -> list[str]:
    """Return all unique category names."""
    seen: set[str] = set()
    result: list[str] = []
    for e in _REGISTRY:
        if e.category not in seen:
            seen.add(e.category)
            result.append(e.category)
    return result


def entries_by_category(category: str) -> list[ConfigEntry]:
    return [e for e in _REGISTRY if e.category == category]


def get_entry(key: str) -> ConfigEntry:
    if key not in _REGISTRY_MAP:
        raise KeyError(f"Unknown config key: {key}")
    return _REGISTRY_MAP[key]


# ── Type coercion ─────────────────────────────────────────────────────────────

def _coerce(value: Any, target_type: str, entry: ConfigEntry) -> Any:
    if value is None:
        return value
    if target_type == "int":
        return int(value)
    if target_type == "float":
        return float(value)
    if target_type == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("1", "true", "yes", "on")
        return bool(value)
    if target_type == "list":
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            return [v.strip() for v in value.split(",") if v.strip()]
        return [value]
    return str(value)


# ── Priority-chain resolver ───────────────────────────────────────────────────

_CONFIG_SOURCES = {
    "env": {},         # Populated from environment variables
    "overrides": {},   # In-memory overrides (set via config.set())
    "settings": {},    # From data/settings.json
    "yaml": {},        # From config.yaml
}


class Config:
    """
    Singleton config with priority-chain resolution.

    Priority (highest wins):
        1. In-memory overrides (config.set())
        2. Environment variables
        3. data/settings.json
        4. config.yaml
        5. Code default from ConfigEntry
    """

    def __init__(self):
        self._loaded = False

    def load(self, config_yaml_path: str = "./config.yaml", settings_path: str = "./data/settings.json"):
        """Load settings from yaml + json files."""
        # Load yaml
        yaml_path = Path(config_yaml_path)
        if yaml_path.exists():
            try:
                import yaml
                with open(yaml_path, encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                _CONFIG_SOURCES["yaml"] = self._flatten(data)
                logger.debug(f"[Config] Loaded yaml: {yaml_path}")
            except Exception as e:
                logger.warning(f"[Config] Failed to load yaml {yaml_path}: {e}")

        # Load settings.json
        settings_path_obj = Path(settings_path)
        if settings_path_obj.exists():
            try:
                with open(settings_path_obj, encoding="utf-8") as f:
                    data = json.load(f)
                _CONFIG_SOURCES["settings"] = data
                logger.debug(f"[Config] Loaded settings: {settings_path_obj}")
            except Exception as e:
                logger.warning(f"[Config] Failed to load settings {settings_path_obj}: {e}")

        # Scan environment variables for registered keys
        for entry in _REGISTRY:
            if entry.env_var:
                val = os.environ.get(entry.env_var)
                if val is not None:
                    _CONFIG_SOURCES["env"][entry.key] = val

        self._loaded = True

    def _flatten(self, data: dict, prefix: str = "") -> dict:
        """Flatten nested dict to dot-separated keys."""
        result = {}
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                result.update(self._flatten(value, full_key))
            else:
                result[full_key] = value
        return result

    def get(self, key: str, default: Any = None) -> Any:
        """Resolve a config value by priority chain."""
        # 1. In-memory overrides
        if key in _CONFIG_SOURCES["overrides"]:
            return _CONFIG_SOURCES["overrides"][key]

        entry = _REGISTRY_MAP.get(key)

        # 2. Environment variable (pre-scanned)
        if entry and entry.env_var:
            env_val = _CONFIG_SOURCES["env"].get(key)
            if env_val is not None:
                return _coerce(env_val, entry.type, entry)

        # 3. settings.json
        if key in _CONFIG_SOURCES["settings"]:
            val = _CONFIG_SOURCES["settings"][key]
            if entry:
                return _coerce(val, entry.type, entry)
            return val

        # 4. config.yaml
        if key in _CONFIG_SOURCES["yaml"]:
            val = _CONFIG_SOURCES["yaml"][key]
            if entry:
                return _coerce(val, entry.type, entry)
            return val

        # 5. Code default (from entry or caller's default)
        if entry:
            return entry.default
        if default is not None:
            return default
        raise KeyError(f"Unknown config key: {key} — not in registry and no default provided")

    def set(self, key: str, value: Any, persist: bool = True):
        """
        Set a config value in memory. Persists to settings.json if persist=True.
        """
        entry = _REGISTRY_MAP.get(key)
        if entry:
            value = _coerce(value, entry.type, entry)

        _CONFIG_SOURCES["overrides"][key] = value

        if persist:
            settings_path = os.environ.get(
                "JARVIS_SETTINGS_FILE",
                str(Path(os.environ.get("JARVIS_DATA_DIR", "data")) / "settings.json")
            )
            settings_obj = Path(settings_path)
            try:
                current = {}
                if settings_obj.exists():
                    with open(settings_obj, encoding="utf-8") as f:
                        current = json.load(f)
                current[key] = value
                settings_obj.parent.mkdir(parents=True, exist_ok=True)
                with open(settings_obj, "w", encoding="utf-8") as f:
                    json.dump(current, f, indent=2, default=str)
            except Exception as e:
                logger.warning(f"[Config] Failed to persist {key}={value}: {e}")

        # Fire on_change callback
        if entry:
            self._fire_on_change(key, value)

    def reset(self, key: str):
        """Remove in-memory override for a key (falls back to env/json/yaml/default)."""
        _CONFIG_SOURCES["overrides"].pop(key, None)

    def reset_all(self):
        """Clear all in-memory overrides."""
        _CONFIG_SOURCES["overrides"].clear()

    def as_dict(self, category: Optional[str] = None) -> dict:
        """Return all resolved values as a flat dict, optionally filtered by category."""
        result = {}
        for entry in _REGISTRY:
            if category and entry.category != category:
                continue
            result[entry.key] = self.get(entry.key)
        return result

    def _mask_secret(self, value: Any) -> Any:
        if value and isinstance(value, str) and len(value) > 8:
            return value[:4] + "****" + value[-4:]
        return value

    def as_api_dict(self, category: Optional[str] = None) -> list[dict]:
        """Return all settings with metadata for the REST API. Secrets are masked."""
        result = []
        for entry in _REGISTRY:
            if category and entry.category != category:
                continue
            is_overridden = entry.key in _CONFIG_SOURCES["overrides"]
            resolved = self.get(entry.key)
            display_value = self._mask_secret(resolved) if entry.secret else resolved
            result.append({
                "key": entry.key,
                "value": display_value,
                "default": entry.default,
                "type": entry.type,
                "category": entry.category,
                "description": entry.description,
                "ui": entry.ui,
                "options": entry.options,
                "options_provider": entry.options_provider,
                "restart_required": entry.restart_required,
                "min_value": entry.min_value,
                "max_value": entry.max_value,
                "env_var": entry.env_var,
                "is_overridden": is_overridden,
            })
        return result

    def _fire_on_change(self, key: str, value: Any):
        """Call registered on_change callbacks."""
        for cb in _ON_CHANGE_CALLBACKS.get(key, []):
            try:
                cb(value)
            except Exception as e:
                logger.warning(f"[Config] on_change callback failed for {key}: {e}")

    def on_change(self, key: str, callback):
        """Register a callback for when a key changes."""
        _ON_CHANGE_CALLBACKS.setdefault(key, []).append(callback)

    # ── Backward-compatible dot access ────────────────────────────────────────
    class _Proxy:
        def __init__(self, config, prefix):
            self._config = config
            self._prefix = prefix

        def __getattr__(self, name):
            full_key = f"{self._prefix}.{name}" if self._prefix else name
            try:
                return self._config.get(full_key)
            except KeyError:
                raise AttributeError(f"Config has no key: {full_key}")

        def __setattr__(self, name, value):
            if name.startswith("_"):
                super().__setattr__(name, value)
            else:
                full_key = f"{self._prefix}.{name}" if self._prefix else name
                self._config.set(full_key, value)

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self._Proxy(self, name)


# Callbacks registry
_ON_CHANGE_CALLBACKS: dict[str, list] = {}

# Singleton
config = Config()
