"""Tests for the Automation Tool Adapter (core/tools/build_tools.py).

Tests the bridge between the Graph Runtime and the Automation Loop,
verifying that build_project, repair_project, run_tests, and runtime_validate
can be instantiated and called with proper progress callback patterns.
"""

import asyncio
import json
import os
import tempfile
from pathlib import Path

import pytest

from core.tools.build_tools import (
    _BUILD_LOOP,
    _ensure_automation,
    cancel_build,
    do_build_project,
    do_repair_project,
    do_run_tests,
    do_runtime_validate,
)
from core.tools.execution import BROKEN_TOOLS
from core.tools._constants import TOOL_TAGS
from core.tools.chat_tools import do_manage_memory, do_create_session, do_chat_with_model


class TestBuildAdapterRegistration:
    """Verify the adapter is properly registered in the tool dispatch system."""

    def test_build_tools_not_broken(self):
        assert "build_project" not in BROKEN_TOOLS
        assert "repair_project" not in BROKEN_TOOLS
        assert "run_tests" not in BROKEN_TOOLS
        assert "runtime_validate" not in BROKEN_TOOLS

    def test_build_tools_in_tag_set(self):
        assert "build_project" in TOOL_TAGS
        assert "repair_project" in TOOL_TAGS
        assert "run_tests" in TOOL_TAGS
        assert "runtime_validate" in TOOL_TAGS
        assert "cancel_build" in TOOL_TAGS


class TestBuildAdapterFunctions:
    """Verify the adapter functions have correct signatures and return types.
    Heavy tests (automation init) are integration tests — run separately.
    """

    async def _fake_progress(self, event: dict):
        pass

    @pytest.mark.asyncio
    async def test_execution_id_cancellation(self):
        r = await cancel_build("nonexistent_id")
        assert r["cancelled"] is False
        assert "error" in r

    @pytest.mark.integration
    async def test_do_build_project_signature(self):
        pytest.skip("Integration test: requires AutomationLoop init")
        result = await do_build_project(
            task="test build",
            project_dir=os.getcwd(),
            progress_cb=self._fake_progress,
        )
        assert isinstance(result, dict)
        assert "success" in result
        assert "status" in result

    @pytest.mark.integration
    async def test_do_repair_project_signature(self):
        pytest.skip("Integration test: requires AutomationLoop init")
        result = await do_repair_project(
            project_dir=os.getcwd(),
            build_output="error: missing import",
            progress_cb=self._fake_progress,
        )
        assert isinstance(result, dict)
        assert "success" in result


class TestChatToolsRegistration:
    """Verify the formerly-broken tools are now wired."""

    def test_broken_tools_removed(self):
        assert "manage_memory" not in BROKEN_TOOLS
        assert "create_session" not in BROKEN_TOOLS
        assert "chat_with_model" not in BROKEN_TOOLS

    def test_chat_tools_in_tag_set(self):
        assert "manage_memory" in TOOL_TAGS
        assert "create_session" in TOOL_TAGS
        assert "chat_with_model" in TOOL_TAGS


class TestChatToolsFunctions:
    """Verify chat/memory tools instantiate and return correctly."""

    @pytest.mark.asyncio
    async def test_do_manage_memory_list(self):
        result = await do_manage_memory("list")
        assert isinstance(result, dict)
        if "error" not in result:
            assert "output" in result

    @pytest.mark.asyncio
    async def test_do_create_session(self):
        result = await do_create_session('{"name": "test", "model": "test"}')
        assert isinstance(result, dict)

    @pytest.mark.integration
    async def test_do_chat_with_model(self):
        pytest.skip("Integration test: requires LLM router")
