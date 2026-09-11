from core.desktop.task_packs import TaskPack, TaskPackResult, TaskPackRunner, TaskPackStep


def test_task_pack_requires_verified_evidence():
    pack = TaskPack("explorer-safe", "explorer", (
        TaskPackStep("discover", "discover_window", expected_evidence=("found",)),
    ))
    runner = TaskPackRunner(lambda step: {"found": True}, lambda step, evidence: evidence.get("found") is True)
    result = runner.run(pack)
    assert result.status == "completed"
    assert result.completed_steps == ["discover"]


def test_task_pack_blocks_destructive_steps_by_default():
    pack = TaskPack("delete-check", "explorer", (
        TaskPackStep("delete", "delete_path", destructive=True),
    ))
    result = TaskPackRunner(lambda step: {}, lambda step, evidence: True).run(pack)
    assert result.status == "blocked"
    assert result.completed_steps == []


def test_task_pack_stops_on_failed_verification():
    pack = TaskPack("verify-check", "notepad", (
        TaskPackStep("read", "read_file"),
        TaskPackStep("write", "write_file"),
    ))
    calls = []
    runner = TaskPackRunner(lambda step: calls.append(step.name) or {}, lambda step, evidence: False)
    result = runner.run(pack)
    assert result.status == "failed"
    assert calls == ["read"]
