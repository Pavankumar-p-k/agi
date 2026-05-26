# tests/test_core.py
"""Basic unit tests for core functionality.
These tests focus on the execute_action helper and ensure that
play_media and web_search behave as expected when their HTTP calls are mocked.
"""

import asyncio
import unittest
from unittest.mock import patch, MagicMock

# Import the function under test
from core.main import execute_action

class TestExecuteAction(unittest.IsolatedAsyncioTestCase):
    @patch('httpx.get')
    async def test_play_media_success(self, mock_get):
        # Mock a YouTube page containing a video ID
        mock_resp = MagicMock()
        mock_resp.text = '<a href="/watch?v=VIDEOID12345">Video</a>'
        mock_get.return_value = mock_resp

        intent = {"intent": "play_media", "target": "test song"}
        result = await execute_action(intent, message='play test song')
        self.assertTrue(result.get('executed'))
        self.assertIn('Playing', result.get('action', ''))
        self.assertIn('test song', result.get('action', ''))

    @patch('httpx.get')
    async def test_web_search_fallback(self, mock_get):
        # Mock SearXNG returning no results
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"results": []}
        mock_get.return_value = mock_resp

        intent = {"intent": "web_search", "target": "nonexistent query"}
        result = await execute_action(intent, message='search nonexistent query')
        self.assertTrue(result.get('executed'))
        self.assertIn('Google search', result.get('action', ''))
        self.assertIn('nonexistent query', result.get('action', ''))

if __name__ == '__main__':
    unittest.main()
