"""Integration tests for Result-returning functions.

Tests that embedding_memory and search_tool correctly return
Ok/Err types, not bare values or silently swallowed errors.
"""
import json
from unittest.mock import patch, MagicMock
import numpy as np
import pytest

from core.result import Ok, Err
from core.errors import ProviderError


class TestEmbeddingMemoryResult:
    """embed() now returns Result[np.ndarray, ProviderError]."""

    def test_embed_returns_ok(self):
        from memory.embedding_memory import EmbeddingMemory
        mem = EmbeddingMemory()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"embedding": [0.1, 0.2, 0.3]}
        with patch("memory.embedding_memory.requests.post", return_value=mock_resp):
            result = mem.embed("hello")
            assert result.is_ok()
            assert isinstance(result.unwrap(), np.ndarray)
            assert result.unwrap().tolist() == pytest.approx([0.1, 0.2, 0.3])

    def test_embed_returns_err_on_failure(self):
        from memory.embedding_memory import EmbeddingMemory
        mem = EmbeddingMemory()
        with patch("memory.embedding_memory.requests.post", side_effect=ConnectionError("refused")):
            result = mem.embed("hello")
            assert result.is_err()
            assert isinstance(result._error, ProviderError)
            assert "refused" in str(result._error)
            # unwrap_or works
            assert result.unwrap_or(np.array([])).tolist() == []

    def test_store_handles_embed_failure_gracefully(self):
        """store() catches embed() failure and returns None (no crash)."""
        from memory.embedding_memory import EmbeddingMemory
        mem = EmbeddingMemory()
        with patch("memory.embedding_memory.requests.post", side_effect=ConnectionError("no server")):
            # Should not raise — store handles Err internally
            result = mem.store("test", {"key": "val"})
            assert result is None

    def test_semantic_search_returns_ok(self):
        from memory.embedding_memory import EmbeddingMemory
        mem = EmbeddingMemory()
        mock_embed_resp = MagicMock()
        mock_embed_resp.json.return_value = {"embedding": [0.1, 0.2, 0.3]}
        with (
            patch("memory.embedding_memory.requests.post", return_value=mock_embed_resp),
            patch("memory.embedding_memory.sqlite3.connect") as mock_db,
        ):
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            # Empty database
            mock_cursor.__iter__.return_value = []
            mock_conn.execute.return_value = mock_cursor
            mock_db.return_value = mock_conn

            result = mem.semantic_search("query")
            assert result.is_ok()
            assert result.unwrap() == []

    def test_semantic_search_returns_err_on_embed_failure(self):
        from memory.embedding_memory import EmbeddingMemory
        mem = EmbeddingMemory()
        with patch("memory.embedding_memory.requests.post", side_effect=TimeoutError("timed out")):
            result = mem.semantic_search("query")
            assert result.is_err()
            assert isinstance(result._error, ProviderError)


class TestSearXNGResult:
    """search() now returns Result[List[SearchResult], ProviderError]."""

    def test_search_returns_ok(self):
        from tools.search_tool import SearXNGSearch
        engine = SearXNGSearch(base_url="http://localhost:8888")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [
                {"title": "Result 1", "url": "https://example.com/1", "content": "Content 1", "publishedDate": ""},
                {"title": "Result 2", "url": "https://example.com/2", "content": "Content 2", "publishedDate": ""},
            ]
        }
        with patch("tools.search_tool.requests.get", return_value=mock_resp):
            result = engine.search_sync("test query")
            assert result.is_ok()
            items = result.unwrap()
            assert len(items) == 2
            assert items[0].title == "Result 1"
            assert items[1].url == "https://example.com/2"

    def test_search_returns_err_on_failure(self):
        from tools.search_tool import SearXNGSearch
        engine = SearXNGSearch(base_url="http://localhost:8888")
        with patch("tools.search_tool.requests.get", side_effect=ConnectionError("network down")):
            result = engine.search_sync("test")
            assert result.is_err()
            assert isinstance(result._error, ProviderError)
            # Backward compat: unwrap_or returns []
            assert result.unwrap_or([]) == []

    def test_search_on_http_error(self):
        from tools.search_tool import SearXNGSearch
        engine = SearXNGSearch(base_url="http://localhost:8888")
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.raise_for_status.side_effect = Exception("HTTP 503")
        with patch("tools.search_tool.requests.get", return_value=mock_resp):
            result = engine.search_sync("test")
            assert result.is_err()

    @pytest.mark.asyncio
    async def test_multi_hop_breaks_on_err(self):
        """multi_hop should stop iterating when search returns an Err."""
        from tools.search_tool import SearXNGSearch
        engine = SearXNGSearch(base_url="http://localhost:8888")
        with patch.object(engine, "search", return_value=Err(ProviderError("down"))):
            result = await engine.multi_hop("query", max_iterations=3)
            assert result == ""
