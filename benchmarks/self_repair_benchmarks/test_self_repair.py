import shutil
import pytest
from pathlib import Path
from brain.AdaptiveSelfRepair import AutonomousSelfRepairV3

@pytest.mark.asyncio
async def test_self_repair_patch_cycle():
    workspace = Path.cwd() / ".tmp_self_repair_benchmark"
    workspace.mkdir(parents=True, exist_ok=True)

    target = workspace / "dummy_broken.py"
    target.write_text("def broken_func():\n    return 1 / 0\n", encoding="utf-8")
    test_target = workspace / "test_dummy_broken.py"
    test_target.write_text(
        "from dummy_broken import broken_func\n\n"
        "def test_broken_func():\n"
        "    assert broken_func() == 0\n",
        encoding="utf-8",
    )

    try:
        repair_engine = AutonomousSelfRepairV3(str(workspace))
        patch = await repair_engine.autonomous_patch_generation(
            target_file="dummy_broken.py",
            failing_test="test_dummy_broken.py",
            error_trace="ZeroDivisionError",
        )

        assert patch is not None
        assert patch.status.name == "SUCCESS"
        assert patch.confidence >= 0.8
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
