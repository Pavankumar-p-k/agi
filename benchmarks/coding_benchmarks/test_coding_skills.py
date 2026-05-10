import shutil
import pytest
from pathlib import Path

from brain.AdaptiveSelfRepair import AutonomousSelfRepairV3, RepairStatus
from jarvis_os.ProviderDecisionMatrix import ProviderDecisionMatrix
from jarvis_os.ProviderStrategicMemory import ProviderStrategicMemory
from jarvis_os.ProviderTrustRegistry import ProviderTrustRegistry
from jarvis_os.runtime.config import JarvisConfig


@pytest.mark.asyncio
async def test_bug_fix_and_dependency_recovery():
    workspace = Path.cwd() / ".tmp_coding_benchmark"
    workspace.mkdir(parents=True, exist_ok=True)
    target = workspace / "broken_module.py"
    target.write_text("def broken_func():\n    return 1 / 0\n", encoding="utf-8")

    test_file = workspace / "test_broken_module.py"
    test_file.write_text(
        "from broken_module import broken_func\n\n"
        "def test_broken_func_returns_zero_after_patch():\n"
        "    assert broken_func() == 0\n",
        encoding="utf-8",
    )

    try:
        repair = AutonomousSelfRepairV3(str(workspace))
        patch = await repair.autonomous_patch_generation(
            target_file="broken_module.py",
            failing_test="test_broken_module.py",
            error_trace="ZeroDivisionError: division by zero",
        )
        assert patch is not None
        assert patch.status == RepairStatus.SUCCESS
        assert patch.confidence >= 0.8
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_code_generation_and_refactor_routing():
    config = JarvisConfig.from_env()
    trust = ProviderTrustRegistry({"ollama": object(), "rest": object(), "fallback": object()})
    strategic = ProviderStrategicMemory(config)
    matrix = ProviderDecisionMatrix(config, trust, strategic)

    profile = matrix.evaluate_task("Refactor this Python code and generate tests", {})
    assert profile["task_type"] == "coding"
    assert profile["coding_strength"] >= 0.9
