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
    ConfigEntry("llm.chat_model",        "ollama/qwen2.5:7b",      "str",  "models",       "Chat completion model",            ui="model_select", env_var="CHAT_MODEL"),
    ConfigEntry("llm.code_model",        "ollama/qwen2.5:7b",      "str",  "models",       "Code generation model",            ui="model_select", env_var="CODE_MODEL"),
    ConfigEntry("llm.analysis_model",    "ollama/qwen2.5:7b",            "str",  "models",       "Analysis/reasoning model",         ui="model_select", env_var="ANALYSIS_MODEL"),
    ConfigEntry("llm.reasoning_model",   "ollama/deepseek-r1:1.5b",      "str",  "models",       "Step-by-step reasoning model",     ui="model_select", env_var="REASONING_MODEL"),
    ConfigEntry("llm.vision_model",      "ollama/moondream:latest",      "str",  "models",       "Vision/image model",               ui="model_select", env_var="VISION_MODEL"),
    ConfigEntry("llm.embedding_model",   "ollama/nomic-embed-text:latest", "str", "models",      "Embedding model",                  ui="model_select", env_var="EMBEDDING_MODEL"),
    ConfigEntry("llm.grader_model",      "ollama/phi3:mini",              "str", "models",       "Quality grading model",            ui="model_select", env_var="GRADER_MODEL"),
    ConfigEntry("llm.orchestrator_model","ollama/qwen2.5:7b",            "str",  "models",       "Orchestrator/planner model",       ui="model_select", env_var="ORCHESTRATOR_MODEL"),
    ConfigEntry("llm.fallback_model",    "ollama/qwen2.5:7b",           "str",  "models",       "Fallback when primary fails",      ui="model_select", env_var="FALLBACK_MODEL"),
    ConfigEntry("llm.cloud_model",       "",                              "str",  "models",       "Cloud model override (e.g. claude-sonnet-4-20250514)", ui="model_select"),
    ConfigEntry("llm.ping_model",        "tinyllama",                     "str",  "models",       "Small model for health checks",    ui="hidden"),

    # ── Model groups ──────────────────────────────────────────────────────
    ConfigEntry("model_groups.reasoning_group", "chat", "str", "models", "Model group used by reasoning engine", ui="select", options=["chat","reasoning","analysis"], env_var="REASONING_MODEL_GROUP"),

    # ── Role models ───────────────────────────────────────────────────────
    ConfigEntry("role_models.default",   "ollama/llama3.1:8b",            "str",  "models",       "Default role model",               ui="model_select"),

    # ── Hybrid platform ───────────────────────────────────────────────────
    ConfigEntry("model.mode",            "local",                         "str",  "models",       "Hybrid model mode: local, cloud, hybrid", ui="select", options=["local","cloud","hybrid"], env_var="MODEL_MODE"),

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
    ConfigEntry("voice.enabled",         True,                             "bool", "voice",        "Enable voice subsystem",           env_var="VOICE_ENABLED"),
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
    ConfigEntry("voice.mode",                "push-to-talk",                "str",  "voice",        "Voice mode (push-to-talk, continuous, wake-word)", ui="select", options=["push-to-talk", "continuous", "wake-word"]),
    ConfigEntry("voice.continuous_timeout",  30.0,                          "float","voice",        "Continuous listening timeout (seconds)", min_value=5.0, max_value=300.0),
    ConfigEntry("voice.push_to_talk_key",    "",                            "str",  "voice",        "Keyboard key for push-to-talk (empty=disabled)"),
    ConfigEntry("voice.speaker_device",      "",                            "str",  "voice",        "Speaker device index (empty=default)"),
    ConfigEntry("voice.auto_recovery",       True,                          "bool", "voice",        "Auto-recover STT/TTS on failure", env_var="VOICE_AUTO_RECOVER"),
    ConfigEntry("voice.recovery_interval",   5.0,                           "float","voice",        "Seconds between recovery attempts", min_value=1.0, max_value=60.0),
    ConfigEntry("voice.sensitivity_gain",    1.0,                           "float","voice",        "Wake word input gain multiplier",  min_value=0.1, max_value=10.0),
    ConfigEntry("voice.adaptive_threshold",  True,                          "bool", "voice",        "Adaptive noise floor for VAD"),
    ConfigEntry("voice.frame_ms",            30,                            "int",  "voice",        "Audio frame size in ms (10,20,30)", min_value=10, max_value=30),
    ConfigEntry("voice.wake_min_confidence", 0.6,                           "float","voice",        "Minimum confidence for wake word match", min_value=0.0, max_value=1.0),
    ConfigEntry("voice.wake_max_retries",    3,                             "int",  "voice",        "Max auto-restart attempts for detector", min_value=0, max_value=10),
    ConfigEntry("voice.wake_retry_delay",    1.0,                           "float","voice",        "Base delay (s) for restart backoff", min_value=0.5, max_value=30.0),

    # ── Failover ──────────────────────────────────────────────────────────
    ConfigEntry("failover.enabled",         False,   "bool", "failover",  "Enable cloud failover providers",  env_var="FAILOVER_ENABLED"),
    ConfigEntry("failover.openai_api_key",  "",      "str",  "failover",  "OpenAI API key for failover",      env_var="OPENAI_API_KEY", secret=True),
    ConfigEntry("failover.anthropic_api_key","",     "str",  "failover",  "Anthropic API key for failover",   env_var="ANTHROPIC_API_KEY", secret=True),
    ConfigEntry("failover.openai_model",    "gpt-4o-mini", "str", "failover", "OpenAI failover model",         ui="model_select", env_var="FAILOVER_OPENAI_MODEL"),
    ConfigEntry("failover.anthropic_model", "claude-3-haiku-20240307", "str", "failover", "Anthropic failover model", ui="model_select", env_var="FAILOVER_ANTHROPIC_MODEL"),
    ConfigEntry("failover.cooldown_seconds", 60,    "int",  "failover",  "Cooldown after failure",           env_var="FAILOVER_COOLDOWN", min_value=0, max_value=3600),
    ConfigEntry("failover.max_retries",      3,      "int",  "failover",  "Max retries per provider",         env_var="FAILOVER_MAX_RETRIES", min_value=0, max_value=10),

    # ── Brain / Reasoning ─────────────────────────────────────────────────
    ConfigEntry("brain.reasoning_timeout",      120,  "int",   "reasoning", "Reasoning engine timeout seconds",        env_var="REASONING_TIMEOUT", min_value=5, max_value=300),
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

    # ── Browser ───────────────────────────────────────────────────────────
    ConfigEntry("browser.headed",           True,     "bool", "browser",    "Show browser window (false=headless)", env_var="BROWSER_HEADED"),
    ConfigEntry("browser.timeout",          30000,    "int",  "browser",    "Browser action timeout (ms)",          env_var="BROWSER_TIMEOUT", min_value=1000, max_value=120000),
    ConfigEntry("browser.viewport_width",   1280,     "int",  "browser",    "Browser viewport width (px)",          env_var="BROWSER_VIEWPORT_WIDTH", min_value=320, max_value=3840),
    ConfigEntry("browser.viewport_height",  720,      "int",  "browser",    "Browser viewport height (px)",         env_var="BROWSER_VIEWPORT_HEIGHT", min_value=240, max_value=2160),
    ConfigEntry("browser.session_timeout",  1800,     "int",  "browser",    "Idle session timeout (seconds)",       env_var="BROWSER_SESSION_TIMEOUT", min_value=60, max_value=86400),

    # ── Monitoring ─────────────────────────────────────────────────────────
    ConfigEntry("monitor.check_interval",    60,       "int", "monitor",    "Environment monitor check interval (s)", min_value=5, max_value=3600),
]

_REGISTRY_MAP: dict[str, ConfigEntry] = {e.key: e for e in _REGISTRY}


# ── Helpers (data-only, used by settings API routes) ─────────────────────────

def all_categories() -> list[str]:
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


# ── Type coercion (used by settings API routes) ─────────────────────────────

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


# ── Backward-compat dict (kept for any code still checking _CONFIG_SOURCES) ─

_CONFIG_SOURCES = {
    "env": {},
    "overrides": {},
    "settings": {},
    "yaml": {},
}


# ── Config singleton — delegates to ConfigurationService with legacy fallback ─

def _init_sources(config_yaml_path: str, settings_path: str):
    """Populate _CONFIG_SOURCES for the legacy fallback path."""
    yaml_path = Path(config_yaml_path)
    if yaml_path.exists():
        try:
            import yaml
            with open(yaml_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            _CONFIG_SOURCES["yaml"] = _flatten_dot(data)
        except Exception as e:
            logger.warning("[Config] Failed to load yaml %s: %s", yaml_path, e)
    settings_path_obj = Path(settings_path)
    if settings_path_obj.exists():
        try:
            with open(settings_path_obj, encoding="utf-8") as f:
                data = json.load(f)
            _CONFIG_SOURCES["settings"] = data
        except Exception as e:
            logger.warning("[Config] Failed to load settings %s: %s", settings_path_obj, e)
    for entry in _REGISTRY:
        if entry.env_var:
            val = os.environ.get(entry.env_var)
            if val is not None:
                _CONFIG_SOURCES["env"][entry.key] = val


def _flatten_dot(data: dict, prefix: str = "") -> dict:
    result = {}
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            result.update(_flatten_dot(value, full_key))
        else:
            result[full_key] = value
    return result


class Config:
    def __init__(self):
        self._loaded = False

    def load(self, config_yaml_path: str = "./config.yaml", settings_path: str = "./data/settings.json"):
        _init_sources(config_yaml_path, settings_path)
        try:
            from core.configuration import configuration
            configuration.load(config_yaml_path, settings_path)
        except ImportError:
            pass
        self._loaded = True

    def get(self, key: str, default: Any = None) -> Any:
        try:
            from core.configuration import configuration
            return configuration.get(key, default)
        except (ImportError, AttributeError):
            pass
        # Legacy fallback during import-time circular deps
        if key in _CONFIG_SOURCES["overrides"]:
            return _CONFIG_SOURCES["overrides"][key]
        entry = _REGISTRY_MAP.get(key)
        if entry and entry.env_var and key in _CONFIG_SOURCES["env"]:
            return _coerce(_CONFIG_SOURCES["env"][key], entry.type, entry)
        if key in _CONFIG_SOURCES["settings"]:
            val = _CONFIG_SOURCES["settings"][key]
            return _coerce(val, entry.type, entry) if entry else val
        if key in _CONFIG_SOURCES["yaml"]:
            val = _CONFIG_SOURCES["yaml"][key]
            return _coerce(val, entry.type, entry) if entry else val
        if entry:
            return entry.default
        return default

    def set(self, key: str, value: Any, persist: bool = True):
        _CONFIG_SOURCES["overrides"][key] = value
        try:
            from core.configuration import configuration
            configuration.set(key, value, persist=persist)
        except ImportError:
            pass

    def reset(self, key: str):
        from core.configuration import configuration
        configuration.reset(key)

    def reset_all(self):
        from core.configuration import configuration
        configuration.reset_all()

    def as_dict(self, category: Optional[str] = None) -> dict:
        from core.configuration import configuration
        return configuration.as_dict(category)

    def as_api_dict(self, category: Optional[str] = None) -> list[dict]:
        from core.configuration import configuration
        return configuration.as_api_dict(category)

    def on_change(self, key: str, callback):
        from core.configuration import configuration
        configuration.on_change(key, callback)

    class _Proxy:
        def __init__(self, config, prefix):
            self._config = config
            self._prefix = prefix

        def __getattr__(self, name):
            full_key = f"{self._prefix}.{name}" if self._prefix else name
            val = self._config.get(full_key)
            if val is None:
                raise AttributeError(f"Config has no key: {full_key}")
            return val

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


# Singleton — NO auto-load at import time. Call config.load() explicitly.
config = Config()
