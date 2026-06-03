from __future__ import annotations
import os
import json
import shutil
import logging
from pathlib import Path
from typing import Any, Optional
from pydantic import ValidationError

from core.settings.schema import JarvisSettings
from ai_os.event_bus import EventBus

logger = logging.getLogger("jarvis.settings")

class SettingsStore:
    def __init__(self, config_dir: Optional[Path] = None, event_bus: Optional[EventBus] = None):
        self.config_dir = config_dir or Path.home() / ".jarvis"
        self.settings_file = self.config_dir / "settings.json"
        self.backup_file = self.config_dir / "settings.json.bak"
        self.event_bus = event_bus
        self._settings: JarvisSettings = JarvisSettings()
        
        # Ensure config directory exists
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def load(self) -> JarvisSettings:
        """Load settings from file, with fallback to migration or defaults."""
        if self.settings_file.exists():
            try:
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._settings = JarvisSettings.model_validate(data)
                return self._settings
            except (json.JSONDecodeError, ValidationError) as e:
                logger.error(f"Failed to load settings from {self.settings_file}: {e}")
                # If backup exists, try loading it
                if self.backup_file.exists():
                    logger.info("Attempting to load settings from backup...")
                    try:
                        with open(self.backup_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        self._settings = JarvisSettings.model_validate(data)
                        return self._settings
                    except Exception as be:
                        logger.error(f"Failed to load settings from backup: {be}")

        # If we're here, either file doesn't exist or load failed.
        # Try migration if it's the first time.
        self._migrate_legacy_configs()
        self.save()
        return self._settings

    def _migrate_legacy_configs(self):
        """Migrate settings from .env and config.yaml."""
        logger.info("Migrating legacy configurations...")
        
        # Migration from .env (via os.getenv which should have it loaded)
        def env_to_bool(val: Optional[str]) -> Optional[bool]:
            if val is None: return None
            return val.lower() in ("1", "true", "yes", "on")

        # LLM
        if os.getenv("OLLAMA_URL"): self._settings.llm.ollama_host = os.getenv("OLLAMA_URL")
        if os.getenv("AIOS_PLANNER_MODEL"): self._settings.llm.planner_model = os.getenv("AIOS_PLANNER_MODEL")
        if os.getenv("AIOS_REASONING_MODEL"): self._settings.llm.reasoning_model = os.getenv("AIOS_REASONING_MODEL")
        if os.getenv("AIOS_FAST_MODEL"): self._settings.llm.fast_model = os.getenv("AIOS_FAST_MODEL")
        
        # Voice
        if os.getenv("WAKE_WORD_ENABLED"): self._settings.voice.wake_word_enabled = env_to_bool(os.getenv("WAKE_WORD_ENABLED"))
        if os.getenv("STT_MODEL"): self._settings.voice.stt_model = os.getenv("STT_MODEL")
        if os.getenv("TTS_VOICE"): self._settings.voice.tts_voice = os.getenv("TTS_VOICE")
        
        # Server
        if os.getenv("HOST"): self._settings.server.host = os.getenv("HOST")
        if os.getenv("PORT"): self._settings.server.port = int(os.getenv("PORT"))
        if os.getenv("JARVIS_DEV_MODE"): self._settings.server.dev_mode = env_to_bool(os.getenv("JARVIS_DEV_MODE"))
        
        # Logging
        if os.getenv("LOG_LEVEL"): self._settings.logging.level = os.getenv("LOG_LEVEL")
        
        # API Keys
        self._settings.news_api_key = os.getenv("NEWS_API_KEY")
        self._settings.openweather_api_key = os.getenv("OPENWEATHER_API_KEY")
        self._settings.alpha_vantage_key = os.getenv("ALPHA_VANTAGE_KEY")
        self._settings.composio_api_key = os.getenv("COMPOSIO_API_KEY")
        self._settings.groq_api_key = os.getenv("GROQ_API_KEY")
        self._settings.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self._settings.openai_api_key = os.getenv("OPENAI_API_KEY")
        self._settings.github_token = os.getenv("GITHUB_TOKEN")
        self._settings.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self._settings.pexels_api_key = os.getenv("PEXELS_API_KEY")
        self._settings.nvidia_api_key = os.getenv("NVIDIA_API_KEY")
        self._settings.meta_whatsapp_token = os.getenv("META_WHATSAPP_TOKEN")
        self._settings.meta_whatsapp_phone_id = os.getenv("META_WHATSAPP_PHONE_ID")

        # Migration from config.yaml (Plugin system)
        import yaml
        config_yaml_path = Path("config.yaml")
        if config_yaml_path.exists():
            try:
                with open(config_yaml_path, "r", encoding="utf-8") as f:
                    yaml_data = yaml.safe_load(f)
                # Currently config.yaml only has plugin info, but we could migrate it here if needed.
                # For now, we'll keep it simple.
            except Exception as e:
                logger.warning(f"Failed to read config.yaml for migration: {e}")

    def save(self) -> bool:
        """Save settings to file with backup."""
        try:
            # Create backup
            if self.settings_file.exists():
                shutil.copy2(self.settings_file, self.backup_file)
            
            # Save new settings
            with open(self.settings_file, "w", encoding="utf-8") as f:
                f.write(self._settings.model_dump_json(indent=2))
            return True
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
            return False

    def get(self, key: str) -> Any:
        """Get a setting value using dot-notation or flat key."""
        try:
            parts = key.split(".")
            val = self._settings
            for part in parts:
                if hasattr(val, part):
                    val = getattr(val, part)
                elif isinstance(val, dict) and part in val:
                    val = val[part]
                else:
                    raise KeyError
            return val
        except (KeyError, AttributeError):
            # Try searching for the key in nested models (flat key support)
            for field_name in self._settings.model_fields:
                field_val = getattr(self._settings, field_name)
                if hasattr(field_val, key):
                    return getattr(field_val, key)
            raise KeyError(f"Setting '{key}' not found.")

    def set(self, key: str, value: Any) -> bool:
        """Set a setting value using dot-notation or flat key, and validate."""
        parts = key.split(".")
        try:
            if len(parts) == 1:
                # Try root level first
                if hasattr(self._settings, parts[0]):
                    old_value = getattr(self._settings, parts[0])
                    setattr(self._settings, parts[0], value)
                else:
                    # Try searching in nested models
                    found = False
                    for field_name in self._settings.model_fields:
                        field_val = getattr(self._settings, field_name)
                        if hasattr(field_val, parts[0]):
                            old_value = getattr(field_val, parts[0])
                            setattr(field_val, parts[0], value)
                            found = True
                            break
                    if not found:
                        raise KeyError
            else:
                # Nested attribute (dot-notation)
                target = self._settings
                for part in parts[:-1]:
                    if hasattr(target, part):
                        target = getattr(target, part)
                    else:
                        raise KeyError
                
                if not hasattr(target, parts[-1]):
                    raise KeyError
                
                old_value = getattr(target, parts[-1])
                setattr(target, parts[-1], value)
        except (KeyError, AttributeError):
            raise KeyError(f"Setting '{key}' not found.")

        # Validate by re-parsing the whole model
        try:
            self._settings = JarvisSettings.model_validate(self._settings.model_dump())
        except ValidationError as e:
            # Revert change on validation failure
            self.load() # Reload from file to ensure consistent state
            raise e

        if self.save():
            if self.event_bus:
                self.event_bus.publish("settings.changed", {
                    "key": key,
                    "old_value": old_value,
                    "new_value": value
                })
            return True
        return False

    def reset(self, key: Optional[str] = None):
        """Reset one key or all to defaults."""
        defaults = JarvisSettings()
        if key:
            value = self._get_from_model(defaults, key)
            self.set(key, value)
        else:
            self._settings = defaults
            self.save()
            if self.event_bus:
                self.event_bus.publish("settings.changed", {"key": "all", "new_settings": self._settings.model_dump()})

    def _get_from_model(self, model: BaseModel, key: str) -> Any:
        parts = key.split(".")
        val = model
        for part in parts:
            if hasattr(val, part):
                val = getattr(val, part)
            else:
                raise KeyError(f"Key '{key}' not found in defaults.")
        return val

    def export(self) -> dict:
        """Export settings as a dict, masking sensitive values."""
        data = self._settings.model_dump()
        self._mask_sensitive(data)
        return data

    def _mask_sensitive(self, data: Any):
        sensitive_keys = {
            "news_api_key", "openweather_api_key", "alpha_vantage_key", 
            "composio_api_key", "groq_api_key", "gemini_api_key", 
            "openai_api_key", "github_token", "telegram_bot_token", 
            "pexels_api_key", "nvidia_api_key", "meta_whatsapp_token", 
            "meta_whatsapp_phone_id"
        }
        if isinstance(data, dict):
            for k, v in data.items():
                if k in sensitive_keys and v:
                    data[k] = f"{v[:6]}***" if len(v) > 6 else "***"
                else:
                    self._mask_sensitive(v)
        elif isinstance(data, list):
            for item in data:
                self._mask_sensitive(item)

    def import_from_json(self, file_path: str) -> bool:
        """Import settings from a JSON file."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            new_settings = JarvisSettings.model_validate(data)
            self._settings = new_settings
            return self.save()
        except Exception as e:
            logger.error(f"Failed to import settings from {file_path}: {e}")
            return False

# Singleton instance
_store: Optional[SettingsStore] = None

def get_settings_store() -> SettingsStore:
    global _store
    if _store is None:
        from ai_os.event_bus import event_bus as global_bus
        _store = SettingsStore(event_bus=global_bus)
        _store.load()
    return _store
