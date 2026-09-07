"""Lightweight conftest for CLI tests — mocks heavy operations."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def mock_heavy_imports(monkeypatch):
    """Prevent CLI commands from doing real I/O during tests."""
    monkeypatch.setattr("core.setup.detector.is_first_run", MagicMock(return_value=False))
    monkeypatch.setattr("core.setup.engine.SetupEngine", MagicMock())


@pytest.fixture(autouse=True)
def mock_config(monkeypatch):
    """Prevent config from trying to read/write real files."""
    monkeypatch.setattr("cli_config.JarvisConfig.load", MagicMock(return_value=MagicMock()))
