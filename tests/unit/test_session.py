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

"""tests/test_session.py
Tests for ConversationManager — session persistence, stash, token trimming, etc.
"""

import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.session import (
    ConversationManager,
    get_last_session_id,
    list_sessions,
    SESSION_DIR,
    LAST_SESSION_FILE,
)


class TestConversationManager(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.home_patcher = patch("pathlib.Path.home", return_value=Path(self.tmp))
        self.home_patcher.start()
        import core.session as mod
        mod.SESSION_DIR = Path(self.tmp) / ".jarvis" / "sessions"
        mod.LAST_SESSION_FILE = Path(self.tmp) / ".jarvis" / "last_session"
        mod._ensure_dir()

    def tearDown(self):
        self.home_patcher.stop()
        import core.session as mod
        mod.SESSION_DIR = Path.home() / ".jarvis" / "sessions"
        mod.LAST_SESSION_FILE = Path.home() / ".jarvis" / "last_session"
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_create_session(self):
        cm = ConversationManager()
        self.assertIsNotNone(cm.session_id)
        self.assertEqual(cm.message_count, 0)
        self.assertEqual(cm.token_count, 2)  # base overhead

    def test_add_message(self):
        cm = ConversationManager()
        msg = cm.add_message("user", "hello")
        self.assertEqual(msg["role"], "user")
        self.assertEqual(msg["content"], "hello")
        self.assertEqual(cm.message_count, 1)

    def test_save_and_load(self):
        cm = ConversationManager()
        cm.add_message("user", "hello")
        cm.add_message("assistant", "hi there")
        cm.save()

        cm2 = ConversationManager(session_id=cm.session_id)
        cm2.load()
        self.assertEqual(cm2.message_count, 2)
        self.assertEqual(cm2.messages[0]["content"], "hello")
        self.assertEqual(cm2.messages[1]["content"], "hi there")

    def test_get_context(self):
        cm = ConversationManager()
        cm.add_message("user", "m1")
        cm.add_message("assistant", "m2")
        ctx = cm.get_context()
        self.assertEqual(len(ctx), 2)
        self.assertEqual(ctx[0]["role"], "user")
        self.assertEqual(ctx[1]["content"], "m2")

        ctx1 = cm.get_context(last_n=1)
        self.assertEqual(len(ctx1), 1)

    def test_rename(self):
        cm = ConversationManager()
        cm.rename("test-session")
        self.assertEqual(cm.name, "test-session")

        cm2 = ConversationManager(session_id=cm.session_id)
        cm2.load()
        self.assertEqual(cm2.name, "test-session")

    def test_export_transcript(self):
        cm = ConversationManager()
        cm.add_message("user", "hello")
        cm.add_message("assistant", "world")
        export_dir = Path(self.tmp) / "exports"
        path = cm.export_transcript(output_dir=export_dir)
        self.assertTrue(os.path.exists(path))
        content = Path(path).read_text(encoding="utf-8")
        self.assertIn("hello", content)
        self.assertIn("world", content)

    def test_fork(self):
        cm = ConversationManager()
        cm.add_message("user", "original")
        forked = cm.fork()
        self.assertNotEqual(forked.session_id, cm.session_id)
        self.assertEqual(forked.message_count, 1)
        self.assertEqual(forked.messages[0]["content"], "original")

    def test_compact(self):
        cm = ConversationManager()
        for i in range(10):
            cm.add_message("user", f"msg{i}")
            cm.add_message("assistant", f"resp{i}")
        self.assertEqual(cm.message_count, 20)
        cm.compact(keep_last=2)
        self.assertLess(cm.message_count, 20)
        self.assertGreater(cm.message_count, 0)

    def test_compact_noop_when_small(self):
        cm = ConversationManager()
        cm.add_message("user", "hello")
        cm.add_message("assistant", "hi")
        cm.compact(keep_last=10)
        self.assertEqual(cm.message_count, 2)

    def test_clear(self):
        cm = ConversationManager()
        cm.add_message("user", "hello")
        cm.clear()
        self.assertEqual(cm.message_count, 0)

    def test_delete(self):
        cm = ConversationManager()
        cm.save()
        path = cm.path
        self.assertTrue(path.exists())
        cm.delete()
        self.assertFalse(path.exists())

    def test_stash_prompt(self):
        cm = ConversationManager()
        idx = cm.stash_prompt("hello world", label="test")
        self.assertEqual(idx, 1)

        items = cm.list_stash()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["text"], "hello world")

        text = cm.load_stash(1)
        self.assertEqual(text, "hello world")

    def test_stash_empty_list(self):
        cm = ConversationManager()
        items = cm.list_stash()
        self.assertEqual(items, [])

    def test_stash_load_missing(self):
        cm = ConversationManager()
        text = cm.load_stash(999)
        self.assertEqual(text, "")

    def test_token_count_increases(self):
        cm = ConversationManager()
        t0 = cm.token_count
        cm.add_message("user", "a" * 1000)
        t1 = cm.token_count
        self.assertGreater(t1, t0)

    def test_repr(self):
        cm = ConversationManager()
        cm.add_message("user", "hello")
        r = repr(cm)
        self.assertIn("ConversationManager", r)
        self.assertIn("msgs=1", r)

    def test_get_last_session_id_no_file(self):
        result = get_last_session_id()
        self.assertIsNone(result)

    def test_get_last_session_id_with_file(self):
        cm = ConversationManager()
        cm.save()
        result = get_last_session_id()
        self.assertEqual(result, cm.session_id)

    def test_list_sessions_empty(self):
        sessions = list_sessions()
        self.assertEqual(sessions, [])


if __name__ == "__main__":
    unittest.main()
