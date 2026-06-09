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

"""Test get_info routing dispatches to correct integration handler."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from core.result import Ok


@pytest.mark.asyncio
async def test_get_info_weather():
    from core.integrations import get_info
    mock_fn = AsyncMock(return_value="Sunny, 22C")
    with patch.dict("core.integrations._INTENT_MAP", {"weather": mock_fn}):
        result = await get_info("weather", "London")
        assert result == "Sunny, 22C"
        mock_fn.assert_called_once_with("London")


@pytest.mark.asyncio
async def test_get_info_news():
    from core.integrations import get_info
    mock_fn = AsyncMock(return_value="Top stories: ...")
    with patch.dict("core.integrations._INTENT_MAP", {"news": mock_fn}):
        result = await get_info("news", "technology")
        assert "Top stories" in result
        mock_fn.assert_called_once_with("technology")


@pytest.mark.asyncio
async def test_get_info_stocks():
    from core.integrations import get_info
    mock_fn = AsyncMock(return_value="$185.50")
    with patch.dict("core.integrations._INTENT_MAP", {"stocks": mock_fn}):
        result = await get_info("stocks", "AAPL")
        assert result == "$185.50"
        mock_fn.assert_called_once_with("AAPL")


@pytest.mark.asyncio
async def test_get_info_sports():
    from core.integrations import get_info
    mock_fn = AsyncMock(return_value="Lakers 110-102")
    with patch.dict("core.integrations._INTENT_MAP", {"sports": mock_fn}):
        result = await get_info("sports", "NBA")
        assert "Lakers" in result
        mock_fn.assert_called_once_with("NBA")


@pytest.mark.asyncio
async def test_get_info_time():
    from core.integrations import get_info
    mock_fn = AsyncMock(return_value="12:30 PM JST")
    with patch.dict("core.integrations._INTENT_MAP", {"time": mock_fn}):
        result = await get_info("time", "Tokyo")
        assert result == "12:30 PM JST"
        mock_fn.assert_called_once_with("Tokyo")


@pytest.mark.asyncio
async def test_get_info_unknown_intent():
    from core.integrations import get_info
    result = await get_info("unknown_intent", "test")
    assert "Unknown info type" in result


@pytest.mark.asyncio
async def test_execute_action_routes_info_intents():
    """Verify core/main.py execute_action dispatches to get_info for info intents."""
    from core.main import execute_action
    for intent in ("weather", "news", "stocks", "sports", "time"):
        with patch("core.integrations.get_info", AsyncMock(return_value=f"mock {intent}")):
            result = await execute_action({"intent": intent, "target": "test", "parameters": {}}, message=f"test {intent}")
            assert result.get("executed") is True
            assert f"mock {intent}" in result.get("action", "")
