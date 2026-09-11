from core.desktop.adapters import TextEditorAdapter
from core.desktop.task_packs import TaskPack, TaskPackRunner, TaskPackStep


def test_text_editor_read_task_pack_is_verified():
    adapter = TextEditorAdapter()
    actions = type("Actions", (), {
        "read_file": lambda self, path: {"success": True, "content": "hello"},
    })()
    pack = TaskPack("text-read", "text_editor", (
        TaskPackStep("read", "read", expected_evidence=("content",)),
    ))
    result = TaskPackRunner(
        lambda step: adapter.read("C:\\safe\\note.txt", actions),
        lambda step, evidence: evidence.get("success") is True and "content" in evidence,
    ).run(pack)
    assert result.status == "completed"
