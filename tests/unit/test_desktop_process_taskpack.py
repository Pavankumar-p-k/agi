from core.desktop.adapters import ProcessInspectionAdapter
from core.desktop.task_packs import TaskPack, TaskPackRunner, TaskPackStep


def test_process_task_pack_requires_structured_evidence():
    class Monitor:
        def list_processes(self, limit):
            return []

    pack = TaskPack("process-list", "process_inspection", (
        TaskPackStep("list", "list", expected_evidence=("processes",)),
    ))
    result = TaskPackRunner(
        lambda step: ProcessInspectionAdapter().list(Monitor(), 10),
        lambda step, evidence: evidence.get("success") is True and isinstance(evidence.get("processes"), list),
    ).run(pack)
    assert result.status == "completed"
