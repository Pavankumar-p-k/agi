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
core/config_init.py — Call init_config() ONCE at startup before any other jarvis imports.

    from core.config_init import init_config
    init_config()

    # Then everything else
    from core.llm_router import get_model
    from brain.reasoning_engine import ReasoningEngine
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_initialized = False


def init_config(
    config_yaml: str | None = None,
    settings_file: str | None = None,
    auto_create_data_dir: bool = True,
) -> None:
    """Load config from yaml + settings.json + env vars. Idempotent."""
    global _initialized
    if _initialized:
        return

    from core.config_registry import config

    yaml_path = config_yaml or os.environ.get("JARVIS_CONFIG_FILE", "./config.yaml")
    settings_path = settings_file or os.environ.get(
        "JARVIS_SETTINGS_FILE", "./data/settings.json"
    )

    if auto_create_data_dir:
        data_dir = Path(settings_path).parent
        data_dir.mkdir(parents=True, exist_ok=True)

    config.load(config_yaml_path=yaml_path, settings_path=settings_path)

    _initialized = True

    from core.config_registry import all_categories
    logger.info("=" * 60)
    logger.info("Jarvis config loaded")
    logger.info(f"  yaml:      {yaml_path}")
    logger.info(f"  settings:  {settings_path}")
    logger.info(f"  chat model: {config.get('llm.chat_model')}")
    logger.info(f"  code model: {config.get('llm.code_model')}")
    logger.info(f"  reasoning:  {config.get('llm.reasoning_model')} "
                f"(group: {config.get('model_groups.reasoning_group')})")
    logger.info(f"  TTS:       {config.get('voice.tts_provider')} / "
                f"{config.get('voice.tts_voice')}")
    logger.info(f"  failover:  {'enabled' if config.get('failover.enabled') else 'disabled'}")
    logger.info("=" * 60)
