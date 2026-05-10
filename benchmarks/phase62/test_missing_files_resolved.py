from pathlib import Path


REQUIRED = [
    "autonomy/l3_executor/executor_engine.py",
    "autonomy/l3_executor/executor_layer.py",
    "brain/ContinuousCognitionLoop.py",
    "brain/CounterfactualSimulator.py",
    "brain/adapters.py",
    "jarvis_os/ProviderSimulationEngine.py",
]


def test_all_phase62_required_files_exist():
    missing = [path for path in REQUIRED if not Path(path).exists()]
    assert missing == []
