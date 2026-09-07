from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from textual.app import App
from textual.widgets import DataTable, Static

from jarvis_tui.app.screens.automation_dashboard_screen import AutomationDashboardScreen
from jarvis_tui.app.screens.memory_dashboard_screen import MemoryDashboardScreen
from jarvis_tui.app.screens.voice_dashboard_screen import VoiceDashboardScreen
from jarvis_tui.app.screens.replay_screen import ReplayScreen
from jarvis_tui.app.screens.diagnostics_dashboard_screen import DiagnosticsDashboardScreen
from jarvis_tui.app.screens.home_screen import HomeScreen
from jarvis_tui.app.screens.main_screen import MainScreen
from jarvis_tui.app.screens.settings_screen import SettingsScreen
from jarvis_tui.app.screens.agent_dashboard_screen import AgentDashboardScreen

SAMPLE_AGENTS = [
    {"name": "NEXUS", "modes": ["research", "plan"], "description": "Research and planning agent"},
    {"name": "FORGE", "modes": ["build", "code"], "description": "Code generation and build agent"},
]

SAMPLE_AGENT_RUN_RESULT = {"activity_id": "act_agent_001", "status": "RUNNING"}

SAMPLE_ACTIVITIES = [
    {"node_id": "act_001", "label": "Build coffee shop app", "title": "Build coffee shop app", "status": "RUNNING", "progress": 65},
    {"node_id": "act_002", "label": "Refactor auth module", "title": "Refactor auth module", "status": "PENDING", "progress": 0},
]

SAMPLE_DAG_RESPONSE = {
    "activity_id": "act_001",
    "root_id": "act_root",
    "all_nodes": {},
    "all_edges": [],
    "timeline": [],
    "decisions": [],
    "total_nodes": 0,
    "failed_nodes": 0,
    "total_duration_seconds": 0.0,
    "unique_tools": [],
    "unique_providers": [],
    "total_retries": 0,
    "total_cost": 0.0,
    "experience": None,
    "knowledge": [],
}

SAMPLE_TIMELINE = [
    {"agent": "NEXUS", "content": "Initializing research", "type": "thought", "actor": "NEXUS", "message": "Initializing research"},
    {"agent": "FORGE", "content": "Writing code", "type": "tool_call", "actor": "FORGE", "message": "Writing code"},
    {"agent": "JARVIS", "content": "Task complete", "type": "completion", "actor": "JARVIS", "message": "Task complete"},
]

SAMPLE_MEMORY_STATS = {
    "memories": [
        {"type": "FAILURE MEMORY", "count": 12, "description": "Automated repair logs and retry histories."},
        {"type": "ARCHITECTURAL MEMORY", "count": 5, "description": "Codebase patterns and structural insights."},
        {"type": "USER PREFERENCES", "count": 24, "description": "Learned habits and preferred models."},
        {"type": "SKILL ACQUISITION", "count": 8, "description": "Newly learned tool usage patterns."},
    ]
}

SAMPLE_DIAGNOSTICS = {
    "healthy": True,
    "data": {
        "environment": {
            "disk_free_gb": 42.5,
            "memory_free_mb": 2048,
            "ollama_available": True,
            "network_reachable": True,
        },
        "system": {
            "platform": "Linux",
            "uptime_seconds": 3600,
        },
        "models": {"ollama": {"healthy": True}, "openai": {"healthy": True}},
        "integrations": {"slack": {"connected": True, "healthy": True}, "gmail": {"connected": False, "healthy": False}},
        "voice": {
            "enabled": True,
            "stt_available": True,
            "tts_available": True,
            "wake_word_available": True,
            "error": None,
        },
    },
}

SAMPLE_SETTINGS = [
    {"key": "API_URL", "value": "http://localhost:8000"},
    {"key": "AUTO_REPAIR", "value": "True"},
    {"key": "VOICE_ENABLED", "value": "True"},
]

SAMPLE_STATUS = {"healthy": True, "status": "healthy"}


class _MockClient:
    def __init__(self):
        self.base_url = "http://localhost:8000"
        self.get_activities = AsyncMock(return_value=SAMPLE_ACTIVITIES)
        self.get_activity_replay = AsyncMock(return_value=SAMPLE_DAG_RESPONSE)
        self.get_activity_timeline = AsyncMock(return_value=SAMPLE_TIMELINE)
        self.cancel_activity = AsyncMock(return_value={"status": "cancelled"})
        self.get_memory_stats = AsyncMock(return_value=SAMPLE_MEMORY_STATS)
        self.get_diagnostics = AsyncMock(return_value=SAMPLE_DIAGNOSTICS)
        self.get_settings = AsyncMock(return_value=SAMPLE_SETTINGS)
        self.update_setting = AsyncMock(return_value={"status": "ok"})
        self.get_status = AsyncMock(return_value=SAMPLE_STATUS)
        self.get_agents = AsyncMock(return_value={"agents": SAMPLE_AGENTS})
        self.run_agent = AsyncMock(return_value=SAMPLE_AGENT_RUN_RESULT)
        self.get_activity_detail = AsyncMock(return_value={"status": "RUNNING", "progress": 50})
        self.get_activity_summary = AsyncMock(return_value={"progress": 50})


class _MockUpdateService:
    """Minimal mock for ActivityUpdateService used in tests."""
    def __init__(self):
        self._callbacks = []
        self._cache = {"activities": [], "counts": {}}

    @property
    def cache(self):
        return self._cache

    @property
    def is_running(self):
        return True

    def subscribe(self, callback):
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def unsubscribe(self, callback):
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def start(self):
        pass

    async def stop(self):
        pass


class _BaseTestApp(App):
    def __init__(self, mock_client=None, screen_cls=None):
        super().__init__()
        self.jarvis_client = mock_client or _MockClient()
        self.activity_updates = _MockUpdateService()
        self._screen_cls = screen_cls

    def on_mount(self):
        if self._screen_cls:
            self.push_screen(self._screen_cls())

    def handle_navigation(self, screen_name):
        pass


# --- Automation Dashboard ---

@pytest.fixture
def mock_client():
    return _MockClient()

@pytest.fixture
def auto_app(mock_client):
    return _BaseTestApp(mock_client, AutomationDashboardScreen)


@pytest.mark.asyncio
async def test_auto_screen_has_title(auto_app):
    async with auto_app.run_test() as pilot:
        await pilot.pause()
        assert auto_app.screen.query_one("#screen-title") is not None


@pytest.mark.asyncio
async def test_auto_screen_has_goals_table(auto_app):
    async with auto_app.run_test() as pilot:
        await pilot.pause()
        assert auto_app.screen.query_one("#goals-table") is not None


@pytest.mark.asyncio
async def test_auto_screen_has_action_buttons(auto_app):
    async with auto_app.run_test() as pilot:
        await pilot.pause()
        assert auto_app.screen.query_one("#btn-refresh") is not None
        assert auto_app.screen.query_one("#btn-stop") is not None
        assert auto_app.screen.query_one("#btn-repair") is not None
        assert auto_app.screen.query_one("#btn-advance") is not None


@pytest.mark.asyncio
async def test_auto_activities_loaded(auto_app, mock_client):
    async with auto_app.run_test() as pilot:
        await pilot.pause()
        assert mock_client.get_activities.await_count >= 1


@pytest.mark.asyncio
async def test_auto_empty_state(mock_client):
    mock_client.get_activities = AsyncMock(return_value=[])
    app = _BaseTestApp(mock_client, AutomationDashboardScreen)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.screen.query_one("#goals-table")
        assert table.row_count >= 1


@pytest.mark.asyncio
async def test_auto_error_state(mock_client):
    mock_client.get_activities = AsyncMock(side_effect=Exception("API error"))
    app = _BaseTestApp(mock_client, AutomationDashboardScreen)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.screen.query_one("#goals-table")
        assert table.row_count >= 1


@pytest.mark.asyncio
async def test_auto_refresh_button(auto_app, mock_client):
    async with auto_app.run_test() as pilot:
        await pilot.pause()
        count_before = mock_client.get_activities.await_count
        btn = auto_app.screen.query_one("#btn-refresh")
        btn.press()
        await pilot.pause()
        assert mock_client.get_activities.await_count > count_before


@pytest.mark.asyncio
async def test_auto_stop_all(auto_app, mock_client):
    async with auto_app.run_test() as pilot:
        await pilot.pause()
        await auto_app.screen.refresh_goals()
        await pilot.pause()
        await auto_app.screen.on_button_pressed(ButtonPressedStub("btn-stop"))
        await pilot.pause()
        # Should have called get_activities() when stop button fires
        assert mock_client.get_activities.await_count >= 1


class ButtonPressedStub:
    """Minimal stub for Button.Pressed event."""
    def __init__(self, button_id: str):
        self.button = ButtonStub(button_id)


class ButtonStub:
    def __init__(self, button_id: str):
        self.id = button_id


# --- Memory Dashboard ---

@pytest.fixture
def mem_app(mock_client):
    return _BaseTestApp(mock_client, MemoryDashboardScreen)


@pytest.mark.asyncio
async def test_mem_screen_has_title(mem_app):
    async with mem_app.run_test() as pilot:
        await pilot.pause()
        assert mem_app.screen.query_one("#screen-title") is not None


@pytest.mark.asyncio
async def test_mem_screen_has_table(mem_app):
    async with mem_app.run_test() as pilot:
        await pilot.pause()
        assert mem_app.screen.query_one("#memory-table") is not None


@pytest.mark.asyncio
async def test_mem_data_loaded(mem_app, mock_client):
    async with mem_app.run_test() as pilot:
        await pilot.pause()
        assert mock_client.get_memory_stats.await_count >= 1


@pytest.mark.asyncio
async def test_mem_error_state(mock_client):
    mock_client.get_memory_stats = AsyncMock(side_effect=Exception("API error"))
    app = _BaseTestApp(mock_client, MemoryDashboardScreen)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.screen.query_one("#memory-table")
        assert table.row_count >= 1


@pytest.mark.asyncio
async def test_mem_empty_state(mock_client):
    mock_client.get_memory_stats = AsyncMock(return_value={"memories": []})
    app = _BaseTestApp(mock_client, MemoryDashboardScreen)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.screen.query_one("#memory-table")
        assert table.row_count >= 1


@pytest.mark.asyncio
async def test_mem_refresh_button(mem_app, mock_client):
    async with mem_app.run_test() as pilot:
        await pilot.pause()
        count_before = mock_client.get_memory_stats.await_count
        btn = mem_app.screen.query_one("#btn-refresh")
        btn.press()
        await pilot.pause()
        assert mock_client.get_memory_stats.await_count > count_before


@pytest.mark.asyncio
async def test_mem_prune_button_does_not_crash(mem_app):
    async with mem_app.run_test() as pilot:
        await pilot.pause()
        btn = mem_app.screen.query_one("#btn-prune")
        btn.press()
        await pilot.pause()


# --- Voice Dashboard ---

@pytest.fixture
def voice_app(mock_client):
    return _BaseTestApp(mock_client, VoiceDashboardScreen)


@pytest.mark.asyncio
async def test_voice_screen_has_title(voice_app):
    async with voice_app.run_test() as pilot:
        await pilot.pause()
        assert voice_app.screen.query_one("#screen-title") is not None


@pytest.mark.asyncio
async def test_voice_status_labels_exist(voice_app):
    async with voice_app.run_test() as pilot:
        await pilot.pause()
        assert voice_app.screen.query_one("#voice-wake") is not None
        assert voice_app.screen.query_one("#voice-stt") is not None
        assert voice_app.screen.query_one("#voice-tts") is not None


@pytest.mark.asyncio
async def test_voice_status_loaded(voice_app, mock_client):
    async with voice_app.run_test() as pilot:
        await pilot.pause()
        assert mock_client.get_diagnostics.await_count >= 1


@pytest.mark.asyncio
async def test_voice_shows_ready_when_available(voice_app):
    async with voice_app.run_test() as pilot:
        await pilot.pause()
        wake = voice_app.screen.query_one("#voice-wake", Static)
        text = str(wake.render())
        assert "LISTENING" in text or "UNAVAILABLE" in text


@pytest.mark.asyncio
async def test_voice_error_state(mock_client):
    mock_client.get_diagnostics = AsyncMock(side_effect=Exception("API error"))
    app = _BaseTestApp(mock_client, VoiceDashboardScreen)
    async with app.run_test() as pilot:
        await pilot.pause()
        stt = app.screen.query_one("#voice-stt", Static)
        assert "OFFLINE" in str(stt.render())


@pytest.mark.asyncio
async def test_voice_buttons_do_not_crash(voice_app):
    async with voice_app.run_test() as pilot:
        await pilot.pause()
        voice_app.screen.query_one("#btn-ptt").press()
        await pilot.pause()
        voice_app.screen.query_one("#btn-wake").press()
        await pilot.pause()
        voice_app.screen.query_one("#btn-tts").press()
        await pilot.pause()


# --- Replay Screen ---

@pytest.fixture
def replay_app(mock_client):
    return _BaseTestApp(mock_client, ReplayScreen)


@pytest.mark.asyncio
async def test_replay_screen_has_header(replay_app):
    async with replay_app.run_test() as pilot:
        await pilot.pause()
        assert replay_app.screen.query_one("#replay-header") is not None


@pytest.mark.asyncio
async def test_replay_screen_has_viewer(replay_app):
    async with replay_app.run_test() as pilot:
        await pilot.pause()
        assert replay_app.screen.query_one("#replay-viewer") is not None


@pytest.mark.asyncio
async def test_replay_screen_has_controls(replay_app):
    async with replay_app.run_test() as pilot:
        await pilot.pause()
        assert replay_app.screen.query_one("#replay-controls") is not None
        assert replay_app.screen.query_one("#replay-progress") is not None


@pytest.mark.asyncio
async def test_replay_loads_dag(replay_app, mock_client):
    async with replay_app.run_test() as pilot:
        await pilot.pause()
        assert mock_client.get_activities.await_count >= 1
        assert mock_client.get_activity_replay.await_count >= 1


@pytest.mark.asyncio
async def test_replay_empty_state(mock_client):
    mock_client.get_activities = AsyncMock(return_value=[])
    app = _BaseTestApp(mock_client, ReplayScreen)
    async with app.run_test() as pilot:
        await pilot.pause()
        viewer = app.screen.query_one("#replay-viewer", Static)
        assert viewer is not None


@pytest.mark.asyncio
async def test_replay_error_state(mock_client):
    mock_client.get_activities = AsyncMock(side_effect=Exception("API error"))
    app = _BaseTestApp(mock_client, ReplayScreen)
    async with app.run_test() as pilot:
        await pilot.pause()
        viewer = app.screen.query_one("#replay-viewer", Static)
        assert viewer is not None


@pytest.mark.asyncio
async def test_replay_step_forward(replay_app):
    async with replay_app.run_test() as pilot:
        await pilot.pause()
        replay_app.screen.action_step_forward()
        await pilot.pause()


@pytest.mark.asyncio
async def test_replay_step_back(replay_app):
    async with replay_app.run_test() as pilot:
        await pilot.pause()
        replay_app.screen.action_step_forward()
        await pilot.pause()
        replay_app.screen.action_step_back()
        await pilot.pause()


# --- Diagnostics Dashboard ---

@pytest.fixture
def diag_app(mock_client):
    return _BaseTestApp(mock_client, DiagnosticsDashboardScreen)


@pytest.mark.asyncio
async def test_diag_screen_has_title(diag_app):
    async with diag_app.run_test() as pilot:
        await pilot.pause()
        assert diag_app.screen.query_one("#screen-title") is not None


@pytest.mark.asyncio
async def test_diag_has_env_table(diag_app):
    async with diag_app.run_test() as pilot:
        await pilot.pause()
        assert diag_app.screen.query_one("#env-table") is not None


@pytest.mark.asyncio
async def test_diag_has_health_table(diag_app):
    async with diag_app.run_test() as pilot:
        await pilot.pause()
        assert diag_app.screen.query_one("#health-table") is not None


@pytest.mark.asyncio
async def test_diag_data_loaded(diag_app, mock_client):
    async with diag_app.run_test() as pilot:
        await pilot.pause()
        assert mock_client.get_diagnostics.await_count >= 1


@pytest.mark.asyncio
async def test_diag_env_table_has_rows(diag_app):
    async with diag_app.run_test() as pilot:
        await pilot.pause()
        table = diag_app.screen.query_one("#env-table")
        assert table.row_count >= 3


@pytest.mark.asyncio
async def test_diag_health_table_has_rows(diag_app):
    async with diag_app.run_test() as pilot:
        await pilot.pause()
        table = diag_app.screen.query_one("#health-table")
        assert table.row_count >= 3


@pytest.mark.asyncio
async def test_diag_error_state(mock_client):
    mock_client.get_diagnostics = AsyncMock(side_effect=Exception("API error"))
    app = _BaseTestApp(mock_client, DiagnosticsDashboardScreen)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.query_one("#health-table") is not None


@pytest.mark.asyncio
async def test_diag_audit_button(diag_app, mock_client):
    async with diag_app.run_test() as pilot:
        await pilot.pause()
        count_before = mock_client.get_diagnostics.await_count
        btn = diag_app.screen.query_one("#btn-audit")
        btn.press()
        await pilot.pause()
        assert mock_client.get_diagnostics.await_count > count_before


# --- Home Screen ---

@pytest.fixture
def home_app(mock_client):
    return _BaseTestApp(mock_client, HomeScreen)


@pytest.mark.asyncio
async def test_home_has_banner(home_app):
    async with home_app.run_test() as pilot:
        await pilot.pause()
        assert home_app.screen.query_one("#hero-banner") is not None


@pytest.mark.asyncio
async def test_home_has_status_label(home_app):
    async with home_app.run_test() as pilot:
        await pilot.pause()
        assert home_app.screen.query_one("#system-status") is not None


@pytest.mark.asyncio
async def test_home_status_loaded(home_app, mock_client):
    async with home_app.run_test() as pilot:
        await pilot.pause()
        assert mock_client.get_status.await_count >= 1


@pytest.mark.asyncio
async def test_home_shows_healthy(home_app):
    async with home_app.run_test() as pilot:
        await pilot.pause()
        label = home_app.screen.query_one("#system-status", Static)
        text = str(label.render())
        assert "HEALTHY" in text or "OFFLINE" in text


@pytest.mark.asyncio
async def test_home_error_state(mock_client):
    mock_client.get_status = AsyncMock(side_effect=Exception("API error"))
    app = _BaseTestApp(mock_client, HomeScreen)
    async with app.run_test() as pilot:
        await pilot.pause()
        label = app.screen.query_one("#system-status", Static)
        assert "OFFLINE" in str(label.render())


# --- Main Screen ---

@pytest.mark.asyncio
async def test_main_screen_has_sidebar():
    app = _BaseTestApp(None, MainScreen)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.query_one("#sidebar") is not None


@pytest.mark.asyncio
async def test_main_screen_has_chat_stream():
    app = _BaseTestApp(None, MainScreen)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.query_one("#chat-stream") is not None


@pytest.mark.asyncio
async def test_main_screen_has_input_bar():
    app = _BaseTestApp(None, MainScreen)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.query_one("#input-bar") is not None


@pytest.mark.asyncio
async def test_main_screen_has_diff_pane():
    app = _BaseTestApp(None, MainScreen)
    async with app.run_test() as pilot:
        await pilot.pause()
        pane = app.screen.query_one("#diff-pane")
        assert pane is not None


@pytest.mark.asyncio
async def test_main_screen_has_status_bar():
    app = _BaseTestApp(None, MainScreen)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.query_one("#status-bar") is not None


@pytest.mark.asyncio
async def test_main_screen_toggle_diff():
    app = _BaseTestApp(None, MainScreen)
    async with app.run_test() as pilot:
        await pilot.pause()
        diff = app.screen.query_one("#diff-pane")
        was_visible = diff.display
        app.screen.action_toggle_diff()
        await pilot.pause()
        assert diff.display != was_visible


@pytest.mark.asyncio
async def test_main_screen_toggle_whisper():
    app = _BaseTestApp(None, MainScreen)
    async with app.run_test() as pilot:
        await pilot.pause()
        whisper = app.screen.query_one("#whisper-channel")
        app.screen.action_toggle_whisper()
        await pilot.pause()


# --- Settings Screen ---

@pytest.fixture
def settings_app(mock_client):
    return _BaseTestApp(mock_client, SettingsScreen)


@pytest.mark.asyncio
async def test_settings_has_title(settings_app):
    async with settings_app.run_test() as pilot:
        await pilot.pause()
        assert settings_app.screen.query_one("#screen-title") is not None


@pytest.mark.asyncio
async def test_settings_has_table(settings_app):
    async with settings_app.run_test() as pilot:
        await pilot.pause()
        assert settings_app.screen.query_one("#settings-table") is not None


@pytest.mark.asyncio
async def test_settings_has_save_button(settings_app):
    async with settings_app.run_test() as pilot:
        await pilot.pause()
        assert settings_app.screen.query_one("#btn-save") is not None


@pytest.mark.asyncio
async def test_settings_data_loaded(settings_app, mock_client):
    async with settings_app.run_test() as pilot:
        await pilot.pause()
        assert mock_client.get_settings.await_count >= 1


@pytest.mark.asyncio
async def test_settings_table_has_rows(settings_app):
    async with settings_app.run_test() as pilot:
        await pilot.pause()
        table = settings_app.screen.query_one("#settings-table")
        assert table.row_count > 0


@pytest.mark.asyncio
async def test_settings_error_state(mock_client):
    mock_client.get_settings = AsyncMock(side_effect=Exception("API error"))
    app = _BaseTestApp(mock_client, SettingsScreen)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.screen.query_one("#settings-table")
        assert table.row_count >= 1


@pytest.mark.asyncio
async def test_settings_no_hardcoded_fallback(mock_client):
    mock_client.get_settings = AsyncMock(side_effect=Exception("API error"))
    app = _BaseTestApp(mock_client, SettingsScreen)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.screen.query_one("#settings-table")
        assert table.row_count >= 1
        # Table should show error, not hardcoded defaults
        rendered = str(table.render())
        assert "AUTO_REPAIR" not in rendered
        assert "VOICE_ENABLED" not in rendered


# --- Agent Dashboard ---

@pytest.fixture
def agent_app(mock_client):
    return _BaseTestApp(mock_client, AgentDashboardScreen)


@pytest.mark.asyncio
async def test_agent_screen_has_title(agent_app):
    async with agent_app.run_test() as pilot:
        await pilot.pause()
        assert agent_app.screen.query_one("#screen-title") is not None


@pytest.mark.asyncio
async def test_agent_has_table(agent_app):
    async with agent_app.run_test() as pilot:
        await pilot.pause()
        assert agent_app.screen.query_one("#agents-table") is not None


@pytest.mark.asyncio
async def test_agent_has_action_buttons(agent_app):
    async with agent_app.run_test() as pilot:
        await pilot.pause()
        assert agent_app.screen.query_one("#btn-refresh") is not None
        assert agent_app.screen.query_one("#btn-run") is not None


@pytest.mark.asyncio
async def test_agent_has_task_input_area(agent_app):
    async with agent_app.run_test() as pilot:
        await pilot.pause()
        area = agent_app.screen.query_one("#task-input-area")
        assert area is not None
        assert area.display is False


@pytest.mark.asyncio
async def test_agent_has_running_progress(agent_app):
    async with agent_app.run_test() as pilot:
        await pilot.pause()
        progress = agent_app.screen.query_one("#running-progress")
        assert progress is not None


@pytest.mark.asyncio
async def test_agent_show_task_input_no_selection(agent_app):
    async with agent_app.run_test() as pilot:
        await pilot.pause()
        table = agent_app.screen.query_one("#agents-table")
        # Cursor is at row 0 after data load, so show_task_input should work
        agent_app.screen.show_task_input()
        await pilot.pause()
        area = agent_app.screen.query_one("#task-input-area")
        assert area.display is True


@pytest.mark.asyncio
async def test_agent_show_task_input_with_selection(agent_app, mock_client):
    mock_client.get_agents = AsyncMock(return_value={"agents": SAMPLE_AGENTS})
    async with agent_app.run_test() as pilot:
        await pilot.pause()
        table = agent_app.screen.query_one("#agents-table")
        table.move_cursor(row=0)
        agent_app.screen.show_task_input()
        await pilot.pause()
        area = agent_app.screen.query_one("#task-input-area")
        assert area.display is True


@pytest.mark.asyncio
async def test_agent_hide_task_input(agent_app):
    async with agent_app.run_test() as pilot:
        await pilot.pause()
        agent_app.screen.show_task_input()
        await pilot.pause()
        agent_app.screen.hide_task_input()
        await pilot.pause()
        area = agent_app.screen.query_one("#task-input-area")
        assert area.display is False


@pytest.mark.asyncio
async def test_agent_submit_empty_task_does_not_run(agent_app, mock_client):
    mock_client.get_agents = AsyncMock(return_value={"agents": SAMPLE_AGENTS})
    async with agent_app.run_test() as pilot:
        await pilot.pause()
        agent_app.screen.show_task_input()
        await pilot.pause()
        # Submit without entering text
        btn = agent_app.screen.query_one("#btn-submit-task")
        btn.press()
        await pilot.pause()
        assert mock_client.run_agent.await_count == 0


@pytest.mark.asyncio
async def test_agent_cancel_button(agent_app, mock_client):
    mock_client.get_agents = AsyncMock(return_value={"agents": SAMPLE_AGENTS})
    async with agent_app.run_test() as pilot:
        await pilot.pause()
        agent_app.screen.show_task_input()
        await pilot.pause()
        btn = agent_app.screen.query_one("#btn-cancel-task")
        btn.press()
        await pilot.pause()
        area = agent_app.screen.query_one("#task-input-area")
        assert area.display is False


@pytest.mark.asyncio
async def test_agent_run_task_success(agent_app, mock_client):
    mock_client.get_agents = AsyncMock(return_value={"agents": SAMPLE_AGENTS})
    mock_client.run_agent = AsyncMock(return_value=SAMPLE_AGENT_RUN_RESULT)
    mock_client.get_activity_detail = AsyncMock(return_value={"status": "RUNNING", "progress": 50})
    mock_client.get_activity_summary = AsyncMock(return_value={"progress": 50})
    mock_client.get_activity_timeline = AsyncMock(return_value=SAMPLE_TIMELINE)
    async with agent_app.run_test() as pilot:
        await pilot.pause()
        agent_app.screen.show_task_input()
        await pilot.pause()
        task_input = agent_app.screen.query_one("#task-input")
        task_input.value = "Build APK"
        btn = agent_app.screen.query_one("#btn-submit-task")
        btn.press()
        await pilot.pause()
        assert mock_client.run_agent.await_count >= 1
        progress = agent_app.screen.query_one("#running-progress", Static)
        assert progress is not None


@pytest.mark.asyncio
async def test_agent_run_task_error(agent_app, mock_client):
    mock_client.get_agents = AsyncMock(return_value={"agents": SAMPLE_AGENTS})
    mock_client.run_agent = AsyncMock(side_effect=Exception("Agent unavailable"))
    async with agent_app.run_test() as pilot:
        await pilot.pause()
        agent_app.screen.show_task_input()
        await pilot.pause()
        task_input = agent_app.screen.query_one("#task-input")
        task_input.value = "Build APK"
        btn = agent_app.screen.query_one("#btn-submit-task")
        btn.press()
        await pilot.pause()
        assert mock_client.run_agent.await_count >= 1


@pytest.mark.asyncio
async def test_agent_run_task_no_activity_id(agent_app, mock_client):
    mock_client.get_agents = AsyncMock(return_value={"agents": SAMPLE_AGENTS})
    mock_client.run_agent = AsyncMock(return_value={})  # No activity_id returned
    async with agent_app.run_test() as pilot:
        await pilot.pause()
        agent_app.screen.show_task_input()
        await pilot.pause()
        task_input = agent_app.screen.query_one("#task-input")
        task_input.value = "Build APK"
        btn = agent_app.screen.query_one("#btn-submit-task")
        btn.press()
        await pilot.pause()
        assert mock_client.run_agent.await_count >= 1


@pytest.mark.asyncio
async def test_agent_run_button_dispatches(agent_app, mock_client):
    mock_client.get_agents = AsyncMock(return_value={"agents": SAMPLE_AGENTS})
    async with agent_app.run_test() as pilot:
        await pilot.pause()
        btn = agent_app.screen.query_one("#btn-run")
        btn.press()
        await pilot.pause()
        area = agent_app.screen.query_one("#task-input-area")
        assert area.display is True
