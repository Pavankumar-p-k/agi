from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_root():
    root = tempfile.mkdtemp()
    yield root
    shutil.rmtree(root, ignore_errors=True)


@pytest.fixture
def clean_registry(temp_root):
    from core.providers.registry import ProviderRegistry
    reg = ProviderRegistry()
    settings_dir = Path(temp_root) / "provider_settings"
    settings_dir.mkdir(parents=True, exist_ok=True)
    reg._PROVIDER_SETTINGS_DIR = settings_dir
    reg._PROVIDER_SETTINGS_FILE = settings_dir / "registry.json"
    reg._providers.clear()
    reg._priorities.clear()
    reg._capability_index.clear()
    reg._pending_settings.clear()
    return reg
