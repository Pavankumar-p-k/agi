from core.desktop.adapters import FileExplorerAdapter
from core.desktop.task_packs import TaskPack, TaskPackRunner, TaskPackStep


def test_explorer_task_pack_uses_adapter_and_evidence():
    adapter = FileExplorerAdapter()
    actions = type("Actions", (), {
        "reveal_in_explorer": lambda self, path: {"success": True, "path": path},
    })()
    pack = TaskPack("explorer-reveal", "explorer", (
        TaskPackStep("reveal", "reveal", expected_evidence=("path",)),
    ))
    result = TaskPackRunner(
        lambda step: adapter.reveal("C:\\safe", actions),
        lambda step, evidence: evidence.get("success") is True and bool(evidence.get("path")),
    ).run(pack)
    assert result.status == "completed"
