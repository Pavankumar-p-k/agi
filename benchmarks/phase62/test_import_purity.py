from pathlib import Path


def test_runtime_module_is_pure_reexport():
    text = Path("runtime/ModelRuntimeManager.py").read_text(encoding="utf-8")
    assert "from jarvis_os.model_runtime_manager import ModelRuntimeManager" in text
    assert "__all__" in text


def test_governance_wrapper_points_to_canonical():
    text = Path("governance/RuntimeGovernanceLayer.py").read_text(encoding="utf-8")
    assert "from jarvis_os.RuntimeGovernanceLayer import RuntimeGovernanceLayer" in text
