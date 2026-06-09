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

import pytest
from unittest.mock import patch, MagicMock, AsyncMock


@pytest.fixture(autouse=True)
def patch_agi_module():
    with patch("api.agi_routes.get_agi") as mock:
        yield mock


class TestAgiStatusStubHandling:
    @pytest.mark.asyncio
    async def test_status_with_all_stubs_none(self, patch_agi_module):
        mock_agi = MagicMock()
        mock_agi.memory = None
        mock_agi.reflector = None
        mock_agi.predictor = None
        mock_agi.get_status.return_value = {"loop_count": 0}
        patch_agi_module.return_value = mock_agi

        from api.agi_routes import agi_status
        result = await agi_status()
        assert result["memory_stats"] == {"info": "not connected"}
        assert result["reflector_stats"] == {}
        assert result["last_predictions"] == []

    @pytest.mark.asyncio
    async def test_status_with_connected_stubs(self, patch_agi_module):
        mock_agi = MagicMock()
        mock_agi.memory = AsyncMock()
        mock_agi.memory.get_stats = AsyncMock(return_value={"total": 100})
        mock_agi.reflector = MagicMock()
        mock_agi.reflector.get_stats.return_value = {"reflections": 5}
        mock_agi.predictor = MagicMock()
        mock_agi.predictor.get_last_predictions.return_value = [{"prediction": "test"}]
        mock_agi.get_status.return_value = {"loop_count": 42}
        patch_agi_module.return_value = mock_agi

        from api.agi_routes import agi_status
        result = await agi_status()
        assert result["memory_stats"] == {"total": 100}
        assert result["reflector_stats"] == {"reflections": 5}
        assert result["last_predictions"] == [{"prediction": "test"}]


class TestAgiPatternsStubHandling:
    @pytest.mark.asyncio
    async def test_patterns_all_none(self, patch_agi_module):
        mock_agi = MagicMock()
        mock_agi.patterns = None
        mock_agi.habits = None
        patch_agi_module.return_value = mock_agi

        from api.agi_routes import get_patterns
        result = await get_patterns()
        assert result["patterns"] == []
        assert result["habits"] == []

    @pytest.mark.asyncio
    async def test_patterns_with_data(self, patch_agi_module):
        mock_agi = MagicMock()
        mock_agi.patterns = MagicMock()
        mock_agi.patterns.get_all_patterns.return_value = [{"name": "morning"}]
        mock_agi.habits = MagicMock()
        mock_agi.habits.get_habits.return_value = [{"name": "exercise"}]
        mock_agi.habits.get_daily_summary.return_value = {"count": 3}
        patch_agi_module.return_value = mock_agi

        from api.agi_routes import get_patterns
        result = await get_patterns()
        assert result["patterns"] == [{"name": "morning"}]
        assert result["habits"] == [{"name": "exercise"}]
        assert result["habit_summary"] == {"count": 3}


class TestAgiPredictionsStubHandling:
    @pytest.mark.asyncio
    async def test_predictions_predictor_none(self, patch_agi_module):
        mock_agi = MagicMock()
        mock_agi.predictor = None
        mock_agi._observe = AsyncMock(return_value=MagicMock(hour=14, pavan_mood="neutral", is_weekend=False))
        patch_agi_module.return_value = mock_agi

        from api.agi_routes import get_predictions
        result = await get_predictions()
        assert result["predictions"] == []

    @pytest.mark.asyncio
    async def test_predictions_with_predictor(self, patch_agi_module):
        mock_agi = MagicMock()
        mock_agi.predictor = MagicMock()
        mock_agi.predictor.predict = AsyncMock(return_value=[{"action": "check_email"}])
        mock_agi._observe = AsyncMock(return_value=MagicMock(hour=9, pavan_mood="positive", is_weekend=False))
        patch_agi_module.return_value = mock_agi

        from api.agi_routes import get_predictions
        result = await get_predictions()
        assert result["predictions"] == [{"action": "check_email"}]


class TestAgiHabitStubHandling:
    @pytest.mark.asyncio
    async def test_add_habit_when_habits_none(self, patch_agi_module):
        mock_agi = MagicMock()
        mock_agi.habits = None
        patch_agi_module.return_value = mock_agi

        from api.agi_routes import add_habit, HabitRequest
        req = HabitRequest(description="test", trigger_hour=8)
        response = await add_habit(req)
        assert response.status_code == 501

    @pytest.mark.asyncio
    async def test_add_habit_when_habits_available(self, patch_agi_module):
        mock_agi = MagicMock()
        mock_agi.habits = MagicMock()
        mock_agi.habits.add_habit.return_value = "habit_123"
        patch_agi_module.return_value = mock_agi

        from api.agi_routes import add_habit, HabitRequest
        req = HabitRequest(description="exercise", trigger_hour=7)
        response = await add_habit(req)
        assert response["habit_id"] == "habit_123"
        assert response["status"] == "added"


class TestAgiReflectionsStubHandling:
    @pytest.mark.asyncio
    async def test_reflections_when_reflector_none(self, patch_agi_module):
        mock_agi = MagicMock()
        mock_agi.reflector = None
        patch_agi_module.return_value = mock_agi

        from api.agi_routes import get_reflections
        response = await get_reflections()
        assert response.status_code == 501

    @pytest.mark.asyncio
    async def test_reflections_with_reflector(self, patch_agi_module):
        mock_agi = MagicMock()
        mock_agi.reflector = MagicMock()
        mock_agi.reflector.get_stats.return_value = {"insights": 10}
        patch_agi_module.return_value = mock_agi

        from api.agi_routes import get_reflections
        result = await get_reflections()
        assert result == {"insights": 10}


class TestAgiTriggerStubHandling:
    @pytest.mark.asyncio
    async def test_trigger_with_predictor_none(self, patch_agi_module):
        mock_agi = MagicMock()
        mock_agi.patterns = MagicMock()
        mock_agi.patterns.learn_from_state = AsyncMock()
        mock_agi.predictor = None
        mock_agi._observe = AsyncMock(return_value=MagicMock(hour=12, pavan_mood="neutral"))
        mock_agi._loop_count = 5
        patch_agi_module.return_value = mock_agi

        from api.agi_routes import manual_trigger
        result = await manual_trigger()
        assert result["predictions"] == []
        assert result["loop_count"] == 5

    @pytest.mark.asyncio
    async def test_trigger_without_patterns(self, patch_agi_module):
        mock_agi = MagicMock()
        mock_agi.patterns = None
        mock_agi.predictor = MagicMock()
        mock_agi.predictor.predict = AsyncMock(return_value=[{"x": 1}])
        mock_agi._observe = AsyncMock(return_value=MagicMock(hour=12, pavan_mood="neutral"))
        mock_agi._loop_count = 3
        patch_agi_module.return_value = mock_agi

        from api.agi_routes import manual_trigger
        result = await manual_trigger()
        assert result["predictions"] == [{"x": 1}]
        assert result["loop_count"] == 3


class TestAgiConfigStubHandling:
    @pytest.mark.asyncio
    async def test_config_dnd_when_goal_planner_none(self, patch_agi_module):
        mock_agi = MagicMock()
        mock_agi.goal_planner = None
        patch_agi_module.return_value = mock_agi

        from api.agi_routes import configure_agi, ConfigRequest
        req = ConfigRequest(dnd_mode=True, dnd_hours=[22, 23])
        response = await configure_agi(req)
        assert response.status_code == 501

    @pytest.mark.asyncio
    async def test_config_dnd_with_goal_planner(self, patch_agi_module):
        mock_agi = MagicMock()
        mock_agi.goal_planner = MagicMock()
        patch_agi_module.return_value = mock_agi

        from api.agi_routes import configure_agi, ConfigRequest
        req = ConfigRequest(dnd_mode=True, dnd_hours=[22, 23])
        response = await configure_agi(req)
        assert response["updated"] == {"dnd_mode": True}
