import pytest

from jarvis_os.model_runtime_manager import ModelRuntimeManager
from jarvis_os.runtime.exceptions import RuntimeBoundaryViolation


def test_runtime_manager_blocks_when_no_providers_available():
    with pytest.raises(RuntimeBoundaryViolation):
        ModelRuntimeManager(providers={})
