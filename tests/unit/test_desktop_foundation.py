from __future__ import annotations

import json
import subprocess

import pytest

import jarvis_desktop_agent as agent
from core.desktop.task_graph import TaskGraph
from core.desktop.user_actions import UserActions


def test_recursive_list_files_reports_bounds(tmp_path, monkeypatch):
    root = tmp_path / "root"
    (root / "one" / "two").mkdir(parents=True)
    (root / "one" / "two" / "deep.txt").write_text("x", encoding="utf-8")
    (root / "a.txt").write_text("a", encoding="utf-8")
    (root / "b.txt").write_text("b", encoding="utf-8")

    monkeypatch.setattr(UserActions, "MAX_RECURSION_DEPTH", 1)
    monkeypatch.setattr(UserActions, "MAX_ENTRIES", 3)
    result = UserActions.list_files(str(root), recursive=True)

    assert result["success"] is True
    assert result["status"] == "limited"
    assert result["truncated"] is True
    assert result["limits"]["entry_limit"] or result["limits"]["depth_limit"]
    assert len(result["entries"]) <= 3


def test_recursive_list_files_does_not_follow_symlink(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "file.txt").write_text("x", encoding="utf-8")
    link = root / "loop"
    try:
        link.symlink_to(root, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is unavailable")

    result = UserActions.list_files(str(root), recursive=True)

    assert result["success"] is True
    assert result["limits"]["symlink_skipped"] >= 1
    assert not any(str(item["path"]).endswith("loop\\loop") for item in result["entries"])


def test_autocomplete_selection_is_semantic_and_read_back(monkeypatch):
    monkeypatch.setattr(UserActions, "_app_pids", staticmethod(lambda _app: [123]))
    monkeypatch.setattr(
        UserActions,
        "list_ui_controls",
        staticmethod(lambda _app: {
            "controls": [{"name": "Paris", "type": "ControlType.ListItem", "id": "city"}]
        }),
    )

    class Result:
        stdout = json.dumps({"name": "Paris", "value": "Paris", "selected": True})
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: Result())
    result = UserActions.select_autocomplete_suggestion("browser", "paris")

    assert result["success"] is True
    assert result["verified"] is True
    assert result["actual_value"] == "Paris"


def test_autocomplete_selection_rejects_false_value(monkeypatch):
    monkeypatch.setattr(UserActions, "_app_pids", staticmethod(lambda _app: [123]))
    monkeypatch.setattr(
        UserActions,
        "list_ui_controls",
        staticmethod(lambda _app: {
            "controls": [{"name": "Paris", "type": "ControlType.ListItem", "id": "city"}]
        }),
    )

    class Result:
        stdout = json.dumps({"name": "Paris", "value": "Pari", "selected": True})
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: Result())
    result = UserActions.select_autocomplete_suggestion("browser", "Paris")

    assert result["success"] is False
    assert result["verified"] is False


def test_structured_plan_routes_to_graph():
    actions = agent.parse_actions(json.dumps({
        "id": "plan",
        "goal": "two steps",
        "steps": [{"id": "one", "tool": "list_windows", "args": {}}],
    }))
    assert actions == [{
        "tool": "run_graph",
        "args": {"graph": {
            "id": "plan",
            "goal": "two steps",
            "steps": [{"id": "one", "tool": "list_windows", "args": {}}],
        }},
    }]


def test_done_request_is_not_success_without_observation(monkeypatch):
    agent._reset_action_limits()
    result, done = agent.execute_action({"tool": "done", "args": {}})
    assert result == "DONE_REQUESTED"
    assert done is False
    assert agent._completion_is_verified([
        {"tool": "type_text", "result": "Tool 'type_text' result: True"}
    ]) is False
    assert agent._completion_is_verified([
        {"tool": "list_windows", "result": "Tool 'list_windows' result: {\"count\": 1}"}
    ]) is True


def test_identical_action_retries_are_bounded(monkeypatch):
    agent._reset_action_limits()
    monkeypatch.setitem(agent.TOOLS, "probe", lambda: True)
    results = [agent.execute_action({"tool": "probe", "args": {}})[0] for _ in range(4)]
    assert "blocked" not in results[0].lower()
    assert "blocked" in results[-1].lower()
    agent._reset_action_limits()


def test_task_graph_rolls_back_after_consent_block(tmp_path):
    target = tmp_path / "state.txt"
    target.write_text("before", encoding="utf-8")
    calls = []

    def execute(action):
        calls.append(action)
        if action["tool"] == "write_file":
            target.write_text("after", encoding="utf-8")
            return "Tool 'write_file' result: {\"success\": true}", False
        return "Tool 'delete_path' BLOCKED: consent denied", False

    graph = TaskGraph({
        "id": "consent-rollback",
        "steps": [
            {
                "id": "write",
                "tool": "write_file",
                "args": {"path": str(target), "content": "after"},
                "rollback_capture": {"kind": "file", "path": str(target)},
            },
            {
                "id": "cleanup",
                "tool": "delete_path",
                "args": {"path": str(target)},
                "depends_on": ["write"],
            },
        ],
    })
    report = graph.run(execute)

    assert report["status"] == "rolled_back"
    assert report["success"] is False
    assert target.read_text(encoding="utf-8") == "before"
    assert report["rollback"][0]["status"] == "restored"


def test_task_graph_does_not_treat_unstructured_text_as_success():
    graph = TaskGraph({"steps": [{"id": "one", "tool": "probe", "args": {}}]})
    report = graph.run(lambda _action: ("Tool 'probe' completed", False))
    assert report["status"] == "rolled_back"
    assert report["success"] is False
