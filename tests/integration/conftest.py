# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import pytest
from unittest.mock import MagicMock


@pytest.fixture(autouse=True)
def mock_external_calls(monkeypatch):
    """Override root conftest: patch subprocess but NOT httpx (TestClient needs real httpx)."""
    monkeypatch.setattr("subprocess.Popen", MagicMock())
    monkeypatch.setattr("subprocess.run", MagicMock(return_value=MagicMock(returncode=0, stdout=b"", stderr=b"")))
    monkeypatch.setattr("subprocess.check_output", MagicMock(return_value=b""))
    monkeypatch.setattr("subprocess.check_call", MagicMock(return_value=0))
