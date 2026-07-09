import logging
import os
import threading
from pathlib import Path

from core.configuration import configuration

logger = logging.getLogger(__name__)

_initialized = False
_init_lock = threading.Lock()


def init_config(
    config_yaml: str | None = None,
    settings_file: str | None = None,
    auto_create_data_dir: bool = True,
) -> None:
    """Load config from yaml + settings.json + env vars. Idempotent. Thread-safe."""
    global _initialized
    if _initialized:
        return
    with _init_lock:
        if _initialized:
            return

        yaml_path = config_yaml or os.environ.get("JARVIS_CONFIG_FILE", "./config.yaml")
        settings_path = settings_file or os.environ.get(
            "JARVIS_SETTINGS_FILE", "./data/settings.json"
        )

        if auto_create_data_dir:
            data_dir = Path(settings_path).parent
            data_dir.mkdir(parents=True, exist_ok=True)

        configuration.load(config_yaml_path=yaml_path, settings_path=settings_path)

        _initialized = True

        logger.info("=" * 60)
        logger.info("Jarvis config loaded")
        logger.info(f"  yaml:      {yaml_path}")
        logger.info(f"  settings:  {settings_path}")
        logger.info(f"  chat model: {configuration.get('llm.chat_model')}")
        logger.info(f"  code model: {configuration.get('llm.code_model')}")
        logger.info(f"  reasoning:  {configuration.get('llm.reasoning_model')}")
        logger.info(f"  failover:  {'enabled' if configuration.get('failover.enabled') else 'disabled'}")
        logger.info("=" * 60)
