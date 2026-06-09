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

"""tests/test_search_fallback.py
Tests for search_fallback module — SearXNG, DDGS, formatting, unified search.
"""

import unittest
from unittest.mock import patch, MagicMock
from tools.search_fallback import (
    search_searxng,
    search_ddgs,
    search,
    search_formatted,
    format_results,
)


class TestSearchSearXNG(unittest.TestCase):
    @patch("tools.search_fallback.httpx.get")
    def test_searxng_returns_results(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "results": [
                {"title": "Result 1", "content": "Content 1", "url": "https://example.com/1"},
                {"title": "Result 2", "content": "Content 2", "url": "https://example.com/2"},
            ]
        }
        mock_get.return_value = mock_resp
        results = search_searxng("test query")
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["title"], "Result 1")

    @patch("tools.search_fallback.httpx.get")
    def test_searxng_returns_empty(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"results": []}
        mock_get.return_value = mock_resp
        results = search_searxng("empty query")
        self.assertEqual(results, [])

    @patch("tools.search_fallback.httpx.get", side_effect=ConnectionError)
    def test_searxng_connection_error(self, mock_get):
        results = search_searxng("test")
        self.assertEqual(results, [])

    @patch("tools.search_fallback.httpx.get", side_effect=Exception("generic error"))
    def test_searxng_generic_error(self, mock_get):
        results = search_searxng("test")
        self.assertEqual(results, [])

    def test_searxng_empty_query(self):
        results = search_searxng("")
        results


class TestSearchDDGS(unittest.TestCase):
    @patch("tools.search_fallback.DDGS")
    def test_ddgs_returns_results(self, mock_ddgs_class):
        mock_instance = MagicMock()
        mock_instance.text.return_value = [
            {"title": "D1", "body": "Body 1", "href": "https://d1.com"},
            {"title": "D2", "body": "Body 2", "href": "https://d2.com"},
        ]
        mock_ddgs_class.return_value.__enter__.return_value = mock_instance
        results = search_ddgs("test")
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["title"], "D1")

    @patch("tools.search_fallback.DDGS")
    def test_ddgs_returns_empty(self, mock_ddgs_class):
        mock_instance = MagicMock()
        mock_instance.text.return_value = []
        mock_ddgs_class.return_value.__enter__.return_value = mock_instance
        results = search_ddgs("empty")
        self.assertEqual(results, [])

    @patch("tools.search_fallback.DDGS", side_effect=ImportError)
    def test_ddgs_import_error(self, mock_ddgs):
        results = search_ddgs("test")
        self.assertEqual(results, [])

    @patch("tools.search_fallback.DDGS")
    def test_ddgs_exception(self, mock_ddgs_class):
        mock_ddgs_class.side_effect = Exception("DDGS error")
        results = search_ddgs("test")
        self.assertEqual(results, [])


class TestSearch(unittest.TestCase):
    @patch("tools.search_fallback.search_searxng", return_value=[{"title": "S1", "content": "C1", "url": "https://s1.com"}])
    def test_search_uses_searxng_first(self, mock_searxng):
        results = search("test")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "S1")

    @patch("tools.search_fallback.search_searxng", return_value=[])
    @patch("tools.search_fallback.search_ddgs", return_value=[{"title": "D1", "content": "C1", "url": "https://d1.com"}])
    def test_search_fallsback_to_ddgs(self, mock_ddgs, mock_searxng):
        results = search("test")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "D1")

    @patch("tools.search_fallback.search_searxng", return_value=[])
    @patch("tools.search_fallback.search_ddgs", return_value=[])
    def test_search_both_empty(self, mock_ddgs, mock_searxng):
        results = search("test")
        self.assertEqual(results, [])


class TestFormatResults(unittest.TestCase):
    def test_format_with_all_fields(self):
        results = [
            {"title": "Title 1", "content": "Content 1", "url": "https://example.com/1"},
            {"title": "Title 2", "content": "Content 2", "url": ""},
        ]
        formatted = format_results(results)
        self.assertIn("Title 1", formatted)
        self.assertIn("Content 1", formatted)
        self.assertIn("https://example.com/1", formatted)
        self.assertIn("Title 2", formatted)

    def test_format_empty(self):
        self.assertEqual(format_results([]), "")

    def test_format_truncates_content(self):
        results = [{"title": "T", "content": "x" * 500, "url": ""}]
        formatted = format_results(results, max_len=50)
        self.assertLess(len(formatted.split(":")[1]) if ":" in formatted else len(formatted), 200)


class TestSearchFormatted(unittest.TestCase):
    @patch("tools.search_fallback.search", return_value=[{"title": "T1", "content": "C1", "url": ""}])
    def test_search_formatted_returns_string(self, mock_search):
        result = search_formatted("test")
        self.assertIn("T1", result)

    @patch("tools.search_fallback.search", return_value=[])
    def test_search_formatted_empty(self, mock_search):
        result = search_formatted("test")
        self.assertEqual(result, "")


if __name__ == "__main__":
    unittest.main()
