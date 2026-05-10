from jarvis_os.ProviderDecisionMatrix import ProviderDecisionMatrix
from jarvis_os.ProviderStrategicMemory import ProviderStrategicMemory
from jarvis_os.ProviderTrustRegistry import ProviderTrustRegistry
from jarvis_os.runtime.config import JarvisConfig


def test_patch_generation_task_profile():
    config = JarvisConfig.from_env()
    trust = ProviderTrustRegistry({"ollama": object(), "fallback": object()})
    strategic = ProviderStrategicMemory(config)
    matrix = ProviderDecisionMatrix(config, trust, strategic)
    profile = matrix.evaluate_task("Generate code patch for failing unit test", {})
    assert profile["task_type"] == "coding"
    assert profile["coding_strength"] >= 0.9


def test_bug_fix_task_profile():
    config = JarvisConfig.from_env()
    trust = ProviderTrustRegistry({"ollama": object(), "fallback": object()})
    strategic = ProviderStrategicMemory(config)
    matrix = ProviderDecisionMatrix(config, trust, strategic)
    profile = matrix.evaluate_task("Fix runtime import error and refactor code", {})
    assert profile["task_type"] == "coding"

