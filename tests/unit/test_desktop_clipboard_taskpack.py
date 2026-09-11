from core.desktop.adapters import ClipboardAdapter
from core.desktop.task_packs import TaskPack, TaskPackRunner, TaskPackStep


def test_clipboard_read_task_pack_is_verified():
    class Clipboard:
        def get_text(self):
            return "desktop"

    pack = TaskPack("clipboard-read", "clipboard", (
        TaskPackStep("read", "read", expected_evidence=("content",)),
    ))
    result = TaskPackRunner(
        lambda step: ClipboardAdapter().read(Clipboard()),
        lambda step, evidence: evidence.get("success") is True and evidence.get("content") == "desktop",
    ).run(pack)
    assert result.status == "completed"
