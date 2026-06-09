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
"""Read-only shim that bridges old flat-key API to the new SettingsStore.

Priority order for get_setting(key):
  1. SettingsStore (new Pydantic model — for keys that exist there)
  2. Old data/settings.json (for legacy keys not yet in schema)
  3. Supplied default

WRITES: rejected — all callers must migrate to get_settings_store().save()
"""

import json
import logging
from pathlib import Path
from typing import Any

from core.settings import get_settings_store

logger = logging.getLogger(__name__)

# Path to the legacy file — read ONLY, never written
_LEGACY_FILE = Path("data/settings.json")
_legacy_cache: dict | None = None


def _load_legacy() -> dict:
    global _legacy_cache
    if _legacy_cache is not None:
        return _legacy_cache
    if _LEGACY_FILE.exists():
        try:
            _legacy_cache = json.loads(_LEGACY_FILE.read_text())
        except Exception as _e:
            logger.debug("settings_legacy load failed: %s", _e)
            _legacy_cache = {}
    else:
        _legacy_cache = {}
    return _legacy_cache


def get_setting(key: str, default: Any = None) -> Any:
    # 1. Try new SettingsStore first (covers overlapping keys)
    try:
        val = get_settings_store().get(key)
        # None is a valid stored value — return it, don't fall through
        if val is not None:
            return val
    except KeyError:
        pass
    except Exception as _e:
        logger.debug("settings_legacy get_setting failed: %s", _e)

    # 2. Fall back to legacy file (covers the ~35 keys not yet in schema)
    legacy = _load_legacy()
    if key in legacy:
        return legacy[key]

    # 3. Return supplied default — no crash
    return default


def load_settings() -> dict:
    """Return merged view — new settings win over legacy on key conflicts."""
    merged = dict(_load_legacy())
    try:
        store_dict = get_settings_store().model_dump_flat()
        merged.update(store_dict)
    except Exception as _e:
        logger.debug("settings_legacy load_settings failed: %s", _e)
    return merged


def save_settings(*args, **kwargs):
    """Hard block — no silent divergence allowed."""
    raise RuntimeError(
        "settings_legacy.save_settings() is disabled. "
        "Use get_settings_store().set(key, value) instead."
    )


# Stub exports for backward compat — these were re-exported by src/settings.py
DEFAULT_SETTINGS: dict = {}
DEFAULT_FEATURES: dict = {}
load_features = load_settings
save_features = save_settings
is_setting_overridden = lambda _: False
get_user_setting = get_setting
