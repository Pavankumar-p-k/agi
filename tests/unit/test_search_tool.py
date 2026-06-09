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

"""tests/test_search_tool.py — Tests for tools/search_tool.py SearXNGSearch + SearchDecisionGate."""
import httpx
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from tools.search_tool import SearchDecisionGate, SearXNGSearch, SearchResult


class TestSearchDecisionGate:
    @pytest.fixture
    def gate(self):
        return SearchDecisionGate()

    def test_keyword_trigger(self, gate):
        assert gate.should_search("latest news today", 0.9) is True
        assert gate.should_search("who is president", 0.9) is True

    def test_low_confidence_trigger(self, gate):
        assert gate.should_search("some random query", 0.5) is True

    def test_high_confidence_no_keyword(self, gate):
        assert gate.should_search("hello world", 0.9) is False

    def test_entity_heuristic(self, gate):
        assert gate.should_search("Elon Musk's latest company", 0.8) is True
        assert gate.should_search("hello world", 0.8) is False


class TestSearchResult:
    def test_defaults(self):
        r = SearchResult(title="Test", url="https://example.com", snippet="desc")
        assert r.title == "Test"
        assert r.url == "https://example.com"
        assert r.snippet == "desc"
        assert r.content == ""
        assert r.score == 1.0

    def test_with_content(self):
        r = SearchResult(title="T", url="U", snippet="S", content="C", score=0.5)
        assert r.content == "C"
        assert r.score == 0.5


class TestSearXNGSearch:
    @pytest.fixture
    def engine(self):
        return SearXNGSearch(base_url="http://localhost:8888")

    @pytest.mark.asyncio
    async def test_search_returns_results(self, engine):
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.json.return_value = {
            "results": [
                {"title": "R1", "url": "https://r1.com", "content": "Content 1"},
                {"title": "R2", "url": "https://r2.com", "content": "Content 2"},
            ]
        }
        mock_resp.raise_for_status.return_value = None
        mock_client.get = AsyncMock(return_value=mock_resp)
        engine._http = mock_client
        result = await engine.search("test query")
        assert result.is_ok()
        items = result.unwrap()
        assert len(items) == 2
        assert items[0].title == "R1"
        assert items[1].url == "https://r2.com"

    @pytest.mark.asyncio
    async def test_search_empty_results(self, engine):
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.json.return_value = {"results": []}
        mock_resp.raise_for_status.return_value = None
        mock_client.get = AsyncMock(return_value=mock_resp)
        engine._http = mock_client
        result = await engine.search("empty query")
        assert result.is_ok()
        assert result.unwrap() == []

    @pytest.mark.asyncio
    async def test_search_connection_error(self, engine):
        from core.result import Err
        from core.errors import ProviderError
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(side_effect=Exception("Error"))
        engine._http = mock_client
        result = await engine.search("test")
        assert result.is_err()
        assert isinstance(result._error, ProviderError)

    def test_score_freshness(self, engine):
        from datetime import datetime, timedelta
        old_date = (datetime.now() - timedelta(days=400)).isoformat()
        fresh_date = (datetime.now() - timedelta(days=1)).isoformat()
        results = [
            SearchResult(title="Old", url="https://old.com", snippet="old", published_date=old_date),
            SearchResult(title="Fresh", url="https://fresh.com", snippet="fresh", published_date=fresh_date),
        ]
        scored = engine._score_results(results)
        assert scored[0].title == "Fresh"

    def test_score_no_date(self, engine):
        results = [SearchResult(title="No date", url="https://x.com", snippet="x")]
        scored = engine._score_results(results)
        assert len(scored) == 1
        assert scored[0].score == 1.0

    @pytest.mark.asyncio
    async def test_scrape_top_empty(self, engine):
        results = []
        contents = await engine.scrape_top(results)
        assert contents == []

    @pytest.mark.asyncio
    async def test_multi_hop_no_results(self, engine):
        from core.result import Ok
        with patch.object(engine, "search", new=AsyncMock(return_value=Ok([]))):
            result = await engine.multi_hop("test")
            assert result == ""
