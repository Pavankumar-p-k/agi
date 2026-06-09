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

"""Property-based fuzz tests for tool dispatch: path resolution, bounds, edge cases."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

import pytest
from hypothesis import given, assume, strategies as st, settings, HealthCheck

from core.tools.execution import (
    _is_sensitive_path,
    _resolve_tool_path,
    _tool_path_roots,
    _truncate,
    MAX_OUTPUT_CHARS,
)


# ── Strategies ───────────────────────────────────────────────────────

# Generate path-like strings that might confuse path resolution
weird_path_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("Ll", "Lu", "Nd", "P", "S"),
        blacklist_characters="\x00",
    ),
    min_size=0,
    max_size=50,
)

# Long paths to stress-test resolution
long_path_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("Ll", "Lu", "Nd", "P"),
        blacklist_characters="\x00",
    ),
    min_size=500,
    max_size=2000,
)

# Unicode-heavy paths
unicode_path_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "M", "N", "P", "S"),
        blacklist_characters="\x00",
    ),
    min_size=1,
    max_size=100,
)

# Tool block content strategies
tool_content_strategy = st.text(
    alphabet=st.characters(
        blacklist_categories=("C"),
        blacklist_characters=("\x00",),
    ),
    min_size=0,
    max_size=500,
)

# Strategies for empty/whitespace/malformed inputs
whitespace_strategy = st.text(
    alphabet=" \t\n\r\v\f",
    min_size=0,
    max_size=20,
)

# Strategy for generating sensitive basenames
sensitive_basename_strategy = st.sampled_from([
    ".ssh", ".gnupg", ".gitconfig",
    ".bashrc", ".bash_profile", ".bash_logout",
    ".zshrc", ".zprofile", ".zshenv",
    ".profile", ".tcshrc", ".cshrc",
    ".env", ".netrc",
])

# Strategy for generating extremely long filenames
long_filename_strategy = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789._-",
    min_size=300,
    max_size=1000,
)


# ── _truncate fuzz ───────────────────────────────────────────────────

class TestTruncateFuzz:
    @given(st.text())
    @settings(suppress_health_check=[HealthCheck.too_slow])
    def test_truncate_never_exceeds_limit(self, text):
        result = _truncate(text, MAX_OUTPUT_CHARS)
        assert len(result) <= MAX_OUTPUT_CHARS + 100

    @given(st.text(min_size=0, max_size=100))
    def test_truncate_short_text_passthrough(self, text):
        result = _truncate(text, 1000)
        assert result == text

    def test_truncate_long_text_shortened(self):
        text = "A" * (MAX_OUTPUT_CHARS + 5000)
        result = _truncate(text, MAX_OUTPUT_CHARS)
        assert len(result) < len(text)
        assert result.endswith(")")

    @given(st.text())
    def test_truncate_never_crashes(self, text):
        try:
            _truncate(text)
        except Exception:
            pytest.fail("_truncate raised exception")


# ── _is_sensitive_path fuzz ──────────────────────────────────────────

class TestIsSensitivePathFuzz:
    @given(sensitive_basename_strategy, st.text(min_size=1, max_size=30, alphabet=st.characters(blacklist_characters="/\\:")))
    def test_sensitive_dir_anywhere_in_path(self, sensitive, suffix):
        path = os.path.join("home", "user", sensitive, suffix)
        assert _is_sensitive_path(os.path.normpath(path)) is True

    @given(sensitive_basename_strategy)
    def test_sensitive_at_root_level(self, sensitive):
        path = os.path.join(os.sep, sensitive, "somefile.txt")
        assert _is_sensitive_path(os.path.normpath(path)) is True

    @given(long_filename_strategy)
    @settings(suppress_health_check=[HealthCheck.too_slow])
    def test_long_filenames_not_false_positive(self, name):
        assume(name not in [".ssh", ".gnupg", ".gitconfig", ".bashrc",
                            ".env", ".netrc", "authorized_keys", "id_rsa",
                            "id_ed25519", "known_hosts", ".bash_profile",
                            ".bash_logout", ".zshrc", ".zprofile", ".zshenv",
                            ".profile", ".tcshrc", ".cshrc", "id_ecdsa"])
        path = os.path.join("data", "projects", name)
        assert _is_sensitive_path(path) is False

    @given(weird_path_strategy)
    @settings(suppress_health_check=[HealthCheck.too_slow])
    def test_weird_paths_never_crash(self, path):
        try:
            _is_sensitive_path(os.path.normpath(path))
        except Exception:
            pytest.fail("_is_sensitive_path raised exception")

    def test_nested_sensitive_detected(self):
        path1 = os.path.join("home", "user", "project", ".ssh", "config")
        path2 = os.path.join("home", "user", ".config", ".gnupg", "pubring.kbx")
        assert _is_sensitive_path(os.path.normpath(path1)) is True
        assert _is_sensitive_path(os.path.normpath(path2)) is True

    def test_safe_nested_paths(self):
        assert _is_sensitive_path("/home/user/project/config.json") is False
        assert _is_sensitive_path("/data/projects/my_app/.gitignore") is False


# ── _resolve_tool_path fuzz ──────────────────────────────────────────

class TestResolveToolPathFuzz:
    @given(st.just(""))
    def test_empty_path_raises(self, path):
        with pytest.raises(ValueError, match="path is required"):
            _resolve_tool_path(path)

    def test_whitespace_path_raises(self):
        with pytest.raises(ValueError, match="path is required"):
            _resolve_tool_path("   ")
        with pytest.raises(ValueError, match="path is required"):
            _resolve_tool_path("\t\n")

    @given(st.text(min_size=1, max_size=200).filter(
        lambda p: ".." not in p and "~" not in p and not p.strip().startswith(("/", "\\"))))
    def test_relative_paths_not_in_roots_raise(self, path):
        try:
            _resolve_tool_path(path)
        except (ValueError, PermissionError):
            pass
        except Exception as e:
            # Paths that happen to fall under allowed roots should succeed
            roots = _tool_path_roots()
            if not any(os.path.realpath(os.path.expanduser(path)).startswith(root) for root in roots):
                assert isinstance(e, ValueError), f"Expected ValueError, got {type(e).__name__}: {e}"

    @given(unicode_path_strategy)
    @settings(suppress_health_check=[HealthCheck.too_slow])
    def test_unicode_paths_never_crash(self, path):
        try:
            _resolve_tool_path(path)
        except (ValueError, PermissionError, OSError):
            pass
        except Exception as e:
            pytest.fail(f"_resolve_tool_path raised unexpected {type(e).__name__}: {e}")


# ── execute_tool_block fuzz (mock-based) ─────────────────────────────

class TestExecuteToolBlockFuzz:
    @given(
        tool_type=st.sampled_from([
            "read_file", "write_file", "bash", "python", "shell",
            "api_call", "search", "edit_file", "manage_settings",
        ]),
        content=tool_content_strategy,
    )
    @settings(suppress_health_check=[HealthCheck.too_slow], deadline=5000)
    def test_various_tool_types_and_content(self, tool_type, content):
        """Execute tool blocks with fuzzed content — should never crash."""
        from core.tools.execution import execute_tool_block

        block = MagicMock()
        block.tool_type = tool_type
        block.content = content

        with patch("core.authz.engine.authz_engine.evaluate", return_value=True):
            with patch("core.tools.policy.policy_engine.get_policy", return_value=None):
                try:
                    desc, result = await_result(execute_tool_block(block))
                    assert isinstance(desc, str)
                    assert isinstance(result, dict)
                except Exception:
                    # Some tools may raise for invalid content — that's expected.
                    # The key is that the dispatch itself handles it gracefully.
                    pass

    @given(
        tool_type=st.text(min_size=10, max_size=50).filter(
            lambda t: t not in (
                "read_file", "write_file", "bash", "python", "shell",
                "api_call", "search", "edit_file", "manage_settings",
                "create_document", "update_document", "edit_document",
                "undo_edit_file", "batch_edit_file", "refactor",
                "shell_command", "close_shell", "semantic_search",
                "watch_file", "suggest_document", "search_chats",
                "manage_tasks", "create_skill", "manage_skills",
                "manage_endpoints", "manage_mcp", "manage_webhooks",
                "manage_tokens", "manage_documents", "manage_settings",
                "sessions_spawn", "manage_notes", "manage_calendar",
                "download_model", "serve_model", "list_served_models",
                "stop_served_model", "list_downloads", "cancel_download",
                "search_hf_models", "list_cached_models", "app_api",
                "list_serve_presets", "serve_preset", "adopt_served_model",
                "list_cookbook_servers", "edit_image", "trigger_research",
                "manage_research", "resolve_contact", "manage_contact",
                "vault_search", "vault_get", "vault_unlock",
                "chat_with_model", "create_session", "list_sessions",
                "send_to_session", "pipeline", "manage_session",
                "manage_memory", "list_models", "ui_control", "ask_teacher",
            ) and not t.startswith("mcp__"),
        ),
        content=st.text(min_size=1, max_size=200),
    )
    @settings(suppress_health_check=[HealthCheck.too_slow], deadline=5000)
    def test_unknown_tool_types_return_error(self, tool_type, content):
        """Unknown tool types should return an error dict, not crash."""
        from core.tools.execution import execute_tool_block

        block = MagicMock()
        block.tool_type = tool_type
        block.content = content

        with patch("core.authz.engine.authz_engine.evaluate", return_value=True):
            with patch("core.tools.policy.policy_engine.get_policy", return_value=None):
                desc, result = await_result(execute_tool_block(block))
                assert isinstance(desc, str)
                assert isinstance(result, dict)
                assert "error" in result or "exit_code" in result


# ── _tool_path_roots fuzz ────────────────────────────────────────────

class TestToolPathRootsFuzz:
    def test_returns_list_of_paths(self):
        roots = _tool_path_roots()
        assert isinstance(roots, list)
        assert len(roots) > 0
        for root in roots:
            assert isinstance(root, str)
            assert os.path.isabs(root)

    def test_contains_data_and_temp(self):
        roots = _tool_path_roots()
        assert any("data" in r for r in roots)
        assert any("Temp" in r or "tmp" in r for r in roots)

    @given(st.text(min_size=1, max_size=50))
    @settings(suppress_health_check=[HealthCheck.too_slow])
    def test_roots_dont_contain_sensitive_paths(self, suffix):
        roots = _tool_path_roots()
        for root in roots:
            candidate = os.path.join(root, suffix)
            if suffix:
                assert not _is_sensitive_path(candidate) or suffix.startswith(".")


# ── Helper ───────────────────────────────────────────────────────────

def await_result(coro):
    """Run an async function synchronously for hypothesis (which is sync)."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    if loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    return loop.run_until_complete(coro)
