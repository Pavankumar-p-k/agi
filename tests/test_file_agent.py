"""tests/test_file_agent.py
Tests for JarvisFileAgent — read, write, edit (exact + fuzzy), list, tree, run_command.
"""

import os
import sys
import json
import tempfile
import unittest
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.file_agent import JarvisFileAgent, file_agent


def async_test(coro):
    """Decorator to run async test methods."""
    def wrapper(*args, **kwargs):
        return asyncio.run(coro(*args, **kwargs))
    return wrapper


class TestFileAgentReadWrite(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.test_file = os.path.join(self.tmp, "test.txt")
        self.agent = JarvisFileAgent()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    @async_test
    async def test_read_file(self):
        with open(self.test_file, "w", encoding="utf-8") as f:
            f.write("hello world")
        content = await self.agent.read_file(self.test_file)
        self.assertEqual(content, "hello world")

    @async_test
    async def test_read_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            await self.agent.read_file("/nonexistent/path/file.txt")

    @async_test
    async def test_write_file_new(self):
        result = await self.agent.write_file(self.test_file, "hello", skip_confirm=True)
        self.assertTrue(result["changed"])
        self.assertEqual(result["size"], 5)
        with open(self.test_file, "r") as f:
            self.assertEqual(f.read(), "hello")

    @async_test
    async def test_write_file_unchanged(self):
        with open(self.test_file, "w") as f:
            f.write("same")
        result = await self.agent.write_file(self.test_file, "same", skip_confirm=True)
        self.assertFalse(result["changed"])

    @async_test
    async def test_write_file_creates_dirs(self):
        nested = os.path.join(self.tmp, "a", "b", "c", "nested.txt")
        result = await self.agent.write_file(nested, "nested", skip_confirm=True)
        self.assertTrue(result["changed"])
        self.assertTrue(os.path.exists(nested))

    @async_test
    async def test_write_file_with_diff(self):
        with open(self.test_file, "w") as f:
            f.write("old content")
        result = await self.agent.write_file(self.test_file, "new content", skip_confirm=True)
        self.assertIn("+++", result.get("diff", ""))


class TestFileAgentEdit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.test_file = os.path.join(self.tmp, "edit_test.txt")
        with open(self.test_file, "w") as f:
            f.write("line1\nline2\nline3\nline4\nline5\n")
        self.agent = JarvisFileAgent()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    @async_test
    async def test_edit_exact_match(self):
        result = await self.agent.edit_file(self.test_file, "line3", "REPLACED", skip_confirm=True)
        self.assertTrue(result.get("exact_match"))
        content = open(self.test_file).read()
        self.assertIn("REPLACED", content)
        self.assertNotIn("line3\n", content)

    @async_test
    async def test_edit_fuzzy_match(self):
        result = await self.agent.edit_file(
            self.test_file,
            "line3\nline4",
            "FUZZY1\nFUZZY2",
            skip_confirm=True,
        )
        self.assertTrue(result.get("changed"))
        content = open(self.test_file).read()
        self.assertIn("FUZZY1", content)
        self.assertIn("FUZZY2", content)

    @async_test
    async def test_edit_file_not_found(self):
        result = await self.agent.edit_file("/nonexistent/path.txt", "old", "new", skip_confirm=True)
        self.assertIn("error", result)

    @async_test
    async def test_edit_no_match(self):
        result = await self.agent.edit_file(
            self.test_file,
            "zzzzzzzz_not_there",
            "replacement",
            skip_confirm=True,
        )
        self.assertIn("error", result)

    @async_test
    async def test_edit_skip_confirm(self):
        result = await self.agent.edit_file(self.test_file, "line1", "START", skip_confirm=True)
        self.assertTrue(result["changed"])
        content = open(self.test_file).read()
        self.assertTrue(content.startswith("START"))


class TestFileAgentListTree(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.sub = os.path.join(self.tmp, "subdir")
        os.makedirs(self.sub)
        for fname in ["a.txt", "b.txt", "c.py"]:
            Path(os.path.join(self.tmp, fname)).write_text("content")
        Path(os.path.join(self.sub, "nested.txt")).write_text("nested")
        self.agent = JarvisFileAgent()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    @async_test
    async def test_list_files_non_recursive(self):
        files = await self.agent.list_files(self.tmp)
        names = [f["name"] for f in files]
        self.assertIn("a.txt", names)
        self.assertIn("b.txt", names)
        self.assertNotIn("nested.txt", names)

    @async_test
    async def test_list_files_recursive(self):
        files = await self.agent.list_files(self.tmp, recursive=True)
        names = [f["name"] for f in files]
        self.assertIn("a.txt", names)
        self.assertIn(os.path.join("subdir", "nested.txt"), names)

    @async_test
    async def test_list_files_with_pattern(self):
        files = await self.agent.list_files(self.tmp, pattern=".py")
        names = [f["name"] for f in files]
        self.assertIn("c.py", names)
        self.assertNotIn("a.txt", names)

    @async_test
    async def test_list_files_invalid_dir(self):
        files = await self.agent.list_files("/nonexistent_dir_xyz")
        self.assertEqual(files, [])

    @async_test
    async def test_tree_view(self):
        tree = await self.agent.tree_view(self.tmp)
        self.assertIn("a.txt", tree)
        self.assertIn("subdir", tree)
        self.assertIn("nested.txt", tree)


class TestFileAgentRunCommand(unittest.TestCase):
    def setUp(self):
        self.agent = JarvisFileAgent()
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    @async_test
    async def test_run_command_success(self):
        result = await self.agent.run_command("echo hello", skip_confirm=True)
        self.assertEqual(result["returncode"], 0)
        self.assertIn("hello", result["stdout"])

    @async_test
    async def test_run_command_blocked(self):
        result = await self.agent.run_command("rm -rf /", skip_confirm=True)
        self.assertIn("blocked", result.get("error", "").lower())

    @async_test
    async def test_run_command_blocked_mkfs(self):
        result = await self.agent.run_command("mkfs ext4 /dev/sda1", skip_confirm=True)
        self.assertIn("blocked", result.get("error", "").lower())

    @async_test
    async def test_run_command_timeout(self):
        result = await self.agent.run_command(
            "python -c \"import time; time.sleep(5)\"",
            timeout=1, skip_confirm=True,
        )
        self.assertEqual(result["returncode"], -1)

    @async_test
    async def test_run_command_with_cwd(self):
        result = await self.agent.run_command("echo %cd%", cwd=self.tmp, skip_confirm=True)
        self.assertEqual(result["returncode"], 0)

    @async_test
    async def test_run_command_truncates_output(self):
        long_output = "python -c \"print('x' * 20000)\""
        result = await self.agent.run_command(long_output, timeout=10, skip_confirm=True)
        self.assertLessEqual(len(result.get("stdout", "")), 10500)


class TestFileAgentOrganizeGenerate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        Path(os.path.join(self.tmp, "photo1.jpg")).write_text("data")
        Path(os.path.join(self.tmp, "photo2.jpg")).write_text("data")
        Path(os.path.join(self.tmp, "doc1.pdf")).write_text("data")
        self.agent = JarvisFileAgent()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    @async_test
    async def test_organize_folder_cancelled(self):
        result = await self.agent.organize_folder(self.tmp, "sort by type", skip_confirm=True)
        self.assertIn("summary", result)
        self.assertIsInstance(result["summary"], str)

    @async_test
    async def test_organize_invalid_dir(self):
        result = await self.agent.organize_folder("/nonexistent_xyz", "organize", skip_confirm=True)
        self.assertIn("error", result)

    @patch("core.file_agent.llm_complete", return_value="Hello World")
    @async_test
    async def test_generate_document(self, mock_llm):
        doc_path = os.path.join(self.tmp, "output.txt")
        result = await self.agent.generate_document(
            template="Hello {{name}}",
            data={"name": "World"},
            output_path=doc_path,
            skip_confirm=True,
        )
        self.assertTrue(result.get("changed"))
        self.assertEqual(result.get("size"), 11)
        with open(doc_path) as f:
            self.assertEqual(f.read(), "Hello World")


if __name__ == "__main__":
    unittest.main()
