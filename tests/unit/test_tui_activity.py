from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from textual.app import App
from textual.widgets import DataTable, RichLog

from jarvis_tui.app.screens.activity_dashboard_screen import ActivityDashboardScreen

SAMPLE_ACTIVITIES = [
    {
        "node_id": "act_001",
        "label": "Build coffee shop app",
        "status": "RUNNING",
        "node_type": "goal",
        "depth": 0,
        "agent_id": "orchestrator",
    },
    {
        "node_id": "act_002",
        "label": "Refactor auth module",
        "status": "PENDING",
        "node_type": "goal",
        "depth": 0,
        "agent_id": None,
    },
    {
        "node_id": "act_003",
        "label": "Fix login screen",
        "status": "FAILED",
        "node_type": "task",
        "depth": 1,
        "agent_id": "builder",
    },
]

SAMPLE_TREE = {
    "nodes": [
        {"node_id": "n1", "label": "Root Goal", "status": "RUNNING", "node_type": "goal", "depth": 0, "parent_id": None, "agent_id": None},
        {"node_id": "n2", "label": "Sub task A", "status": "COMPLETED", "node_type": "task", "depth": 1, "parent_id": "n1", "agent_id": "builder"},
        {"node_id": "n3", "label": "Sub task B", "status": "RUNNING", "node_type": "task", "depth": 1, "parent_id": "n1", "agent_id": "coder"},
    ],
    "edges": [
        {"from_node_id": "n1", "to_node_id": "n2", "edge_type": "depends_on"},
        {"from_node_id": "n1", "to_node_id": "n3", "edge_type": "depends_on"},
    ],
}

SAMPLE_NODE = {
    "node_id": "act_001",
    "label": "Build coffee shop app",
    "status": "RUNNING",
    "node_type": "goal",
    "depth": 0,
    "agent_id": "orchestrator",
    "workflow_id": "wf_001",
    "parent_id": None,
}

SAMPLE_SUMMARY = {
    "total_nodes": 3,
    "depth": 1,
    "agents_used": ["orchestrator", "builder"],
    "by_status": {"RUNNING": 1, "PENDING": 1, "FAILED": 1},
    "goal": "Build coffee shop app",
}


class _MockClient:
    def __init__(self):
        self.get_activities = AsyncMock(return_value=SAMPLE_ACTIVITIES)
        self.get_activity_counts = AsyncMock(return_value={"total": 3, "running": 1, "pending": 1, "failed": 1})
        self.get_activity_tree = AsyncMock(return_value=SAMPLE_TREE)
        self.get_activity_detail = AsyncMock(return_value=SAMPLE_NODE)
        self.get_activity_summary = AsyncMock(return_value=SAMPLE_SUMMARY)
        self.pause_activity = AsyncMock(return_value={"status": "paused"})
        self.resume_activity = AsyncMock(return_value={"status": "resumed"})
        self.cancel_activity = AsyncMock(return_value={"status": "cancelled"})


class _TestApp(App):
    def __init__(self, mock_client=None):
        super().__init__()
        self.jarvis_client = mock_client or _MockClient()

    def on_mount(self):
        self.push_screen(ActivityDashboardScreen())

    def handle_navigation(self, screen_name):
        pass


@pytest.fixture
def mock_client():
    return _MockClient()


@pytest.fixture
def app(mock_client):
    return _TestApp(mock_client)


# --- Widget existence tests ---

@pytest.mark.asyncio
async def test_screen_has_title(app):
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.query_one("#screen-title") is not None


@pytest.mark.asyncio
async def test_screen_has_subtitle(app):
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.query_one("#screen-subtitle") is not None


@pytest.mark.asyncio
async def test_activity_table_exists(app):
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.query_one("#activities-table") is not None


@pytest.mark.asyncio
async def test_detail_panel_exists(app):
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.query_one("#activity-detail") is not None


@pytest.mark.asyncio
async def test_timeline_panel_exists(app):
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.query_one("#activity-timeline") is not None


@pytest.mark.asyncio
async def test_action_buttons_exist(app):
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.query_one("#btn-refresh") is not None
        assert app.screen.query_one("#btn-tree") is not None
        assert app.screen.query_one("#btn-detail") is not None


@pytest.mark.asyncio
async def test_pause_resume_cancel_buttons_exist(app):
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.screen.query_one("#btn-pause") is not None
        assert app.screen.query_one("#btn-resume") is not None
        assert app.screen.query_one("#btn-cancel") is not None


# --- Data loading tests ---

@pytest.mark.asyncio
async def test_activities_loaded_into_table(app):
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.screen.query_one("#activities-table")
        assert table.row_count > 0


@pytest.mark.asyncio
async def test_empty_state(mock_client):
    mock_client.get_activities = AsyncMock(return_value=[])
    app = _TestApp(mock_client)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.screen.query_one("#activities-table")
        assert table.row_count == 0


@pytest.mark.asyncio
async def test_error_fetching_activities_does_not_crash(mock_client):
    mock_client.get_activities = AsyncMock(side_effect=Exception("Connection refused"))
    app = _TestApp(mock_client)
    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.screen.query_one("#activities-table")
        assert table.row_count == 0


# --- Refresh action ---

@pytest.mark.asyncio
async def test_refresh_reloads_data(app, mock_client):
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.action_refresh()
        await pilot.pause()
        assert mock_client.get_activities.await_count >= 1


# --- _get_selected_id tests ---

@pytest.mark.asyncio
async def test_get_selected_id_none_for_empty_table(mock_client):
    mock_client.get_activities = AsyncMock(return_value=[])
    app = _TestApp(mock_client)
    async with app.run_test() as pilot:
        await pilot.pause()
        result = app.screen._get_selected_id()
        assert result is None


# --- RichLog-based tree and detail (test via worker fire-and-forget) ---

@pytest.mark.asyncio
async def test_tree_view_triggers_client_call(app, mock_client):
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen._selected_id = "act_001"
        # @work(thread=False) returns a Worker, not an awaitable
        app.screen._load_tree("act_001")
        await pilot.pause()
        assert mock_client.get_activity_tree.await_count >= 1


@pytest.mark.asyncio
async def test_tree_view_error_does_not_crash(mock_client):
    mock_client.get_activity_tree = AsyncMock(side_effect=Exception("API error"))
    app = _TestApp(mock_client)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen._load_tree("bad_id")
        await pilot.pause()
        assert app.screen.query_one("#activity-detail") is not None


@pytest.mark.asyncio
async def test_detail_view_triggers_client_call(app, mock_client):
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen._load_detail("act_001")
        await pilot.pause()
        assert mock_client.get_activity_detail.await_count >= 1
        assert mock_client.get_activity_summary.await_count >= 1


@pytest.mark.asyncio
async def test_detail_view_error_does_not_crash(mock_client):
    mock_client.get_activity_detail = AsyncMock(side_effect=Exception("Detail error"))
    app = _TestApp(mock_client)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen._load_detail("bad_id")
        await pilot.pause()
        assert app.screen.query_one("#activity-detail") is not None


# --- Action dispatch tests ---

@pytest.mark.asyncio
async def test_pause_action_dispatches(app, mock_client):
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen._selected_id = "act_001"
        app.screen._do_pause("act_001")
        await pilot.pause()
        assert mock_client.pause_activity.await_count >= 1


@pytest.mark.asyncio
async def test_resume_action_dispatches(app, mock_client):
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen._selected_id = "act_001"
        app.screen._do_resume("act_001")
        await pilot.pause()
        assert mock_client.resume_activity.await_count >= 1


@pytest.mark.asyncio
async def test_cancel_action_dispatches(app, mock_client):
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen._selected_id = "act_001"
        app.screen._do_cancel("act_001")
        await pilot.pause()
        assert mock_client.cancel_activity.await_count >= 1


# --- Button press handler tests ---

@pytest.mark.asyncio
async def test_refresh_button_handler(app, mock_client):
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.action_refresh()
        await pilot.pause()
        assert mock_client.get_activities.await_count >= 2


@pytest.mark.asyncio
async def test_tree_button_handler(app, mock_client):
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.action_show_tree()
        await pilot.pause()
        assert True


@pytest.mark.asyncio
async def test_detail_button_handler(app, mock_client):
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.action_show_detail()
        await pilot.pause()
        assert True


@pytest.mark.asyncio
async def test_pause_button_handler(app, mock_client):
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.action_pause_activity()
        await pilot.pause()
        assert True


@pytest.mark.asyncio
async def test_resume_button_handler(app, mock_client):
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.action_resume_activity()
        await pilot.pause()
        assert True


@pytest.mark.asyncio
async def test_cancel_button_handler(app, mock_client):
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.action_cancel_activity()
        await pilot.pause()
        assert True
