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

import pytest
import json
import os
from pathlib import Path
from core.settings.store import SettingsStore
from core.settings.schema import JarvisSettings
from pydantic import ValidationError

@pytest.fixture
def temp_config_dir(tmp_path):
    return tmp_path / ".jarvis"

@pytest.fixture
def settings_store(temp_config_dir):
    return SettingsStore(config_dir=temp_config_dir)

def test_load_defaults(settings_store):
    settings = settings_store.load()
    assert isinstance(settings, JarvisSettings)
    assert settings.llm.ollama_host == "http://127.0.0.1:11434"

def test_save_and_load(settings_store, temp_config_dir):
    settings_store.load()
    settings_store.set("llm.ollama_host", "http://test:11434")
    
    # Create new store instance to check persistence
    new_store = SettingsStore(config_dir=temp_config_dir)
    new_settings = new_store.load()
    assert new_settings.llm.ollama_host == "http://test:11434"

def test_set_validation(settings_store):
    settings_store.load()
    with pytest.raises(ValidationError):
        # api_port should be int, but server settings in schema has port: int
        settings_store.set("server.port", "not-an-int")

def test_get_dot_notation(settings_store):
    settings_store.load()
    assert settings_store.get("llm.ollama_host") == "http://127.0.0.1:11434"

def test_mask_sensitive(settings_store):
    settings_store.load()
    settings_store.set("openai_api_key", "sk-1234567890abcdef")
    exported = settings_store.export()
    assert exported["openai_api_key"] == "sk-123***"

def test_migrate_env(temp_config_dir, monkeypatch):
    monkeypatch.setenv("OLLAMA_URL", "http://env-host:11434")
    monkeypatch.setenv("PORT", "9000")
    
    store = SettingsStore(config_dir=temp_config_dir)
    settings = store.load()
    
    assert settings.llm.ollama_host == "http://env-host:11434"
    assert settings.server.port == 9000

def test_flat_key_support(settings_store):
    settings_store.load()
    # autonomous_enabled is under agi
    assert settings_store.get("autonomous_enabled") == False
    settings_store.set("autonomous_enabled", True)
    assert settings_store.get("agi.autonomous_enabled") == True
