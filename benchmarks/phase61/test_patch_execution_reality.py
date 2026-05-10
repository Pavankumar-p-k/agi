from pathlib import Path

from brain.AdaptiveSelfRepair import AutonomousSelfRepairV3


def test_patch_path_points_to_real_filesystem():
    root = Path(".").resolve()
    repair = AutonomousSelfRepairV3(str(root))
    assert Path(repair.workspace_root).exists()
