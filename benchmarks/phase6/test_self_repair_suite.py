import shutil
from pathlib import Path

import pytest

from brain.AdaptiveSelfRepair import AutonomousSelfRepairV3
from brain.MetaCognitionEngine import ExecutiveMetaCognitionV3


@pytest.mark.asyncio
async def test_syntax_failure_patch_and_validate():
    workspace = Path.cwd() / ".tmp_phase6_selfrepair"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "broken.py").write_text("def broken():\n    return 1 / 0\n", encoding="utf-8")
    (workspace / "test_broken.py").write_text(
        "from broken import broken\n\ndef test_broken():\n    assert broken() == 0\n",
        encoding="utf-8",
    )
    try:
        repair = AutonomousSelfRepairV3(str(workspace))
        patch = await repair.autonomous_patch_generation("broken.py", "test_broken.py", "ZeroDivisionError")
        assert patch is not None
        assert patch.status.name == "SUCCESS"
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_meta_patch_loop_rejects_missing_fields():
    meta = ExecutiveMetaCognitionV3()
    result = meta.trigger_detect_and_patch_loop({"error_trace": "ImportError"})
    assert result["patched"] is False

