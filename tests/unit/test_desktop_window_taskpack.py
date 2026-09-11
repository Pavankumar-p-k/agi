from core.desktop.adapters import WindowManagementAdapter
from core.desktop.task_packs import TaskPack, TaskPackRunner, TaskPackStep


def test_window_list_task_pack_is_verified():
    class Controller:
        def list_windows(self):
            return [{"title": "Editor"}]

    pack = TaskPack("window-list", "windows", (
        TaskPackStep("list", "list", expected_evidence=("windows",)),
    ))
    result = TaskPackRunner(
        lambda step: WindowManagementAdapter().list(Controller()),
        lambda step, evidence: evidence.get("success") is True and evidence.get("count") == 1,
    ).run(pack)
    assert result.status == "completed"
