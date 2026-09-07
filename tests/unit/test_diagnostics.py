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

from core.diagnostics import build_diagnostic_report


def test_diagnostic_report_has_operational_fields():
    report = build_diagnostic_report()

    assert report.status in {"ok", "warning", "degraded", "critical"}
    assert report.counts["python_files"] > 0
    assert "fastapi" in report.optional_dependencies
    assert "python_3_11_plus" in report.runtime_flags
    assert report.capability_gaps


def test_diagnostic_report_serializes_to_dict():
    data = build_diagnostic_report().to_dict()

    assert isinstance(data["issues"], list)
    assert isinstance(data["optional_dependencies"], dict)
    assert isinstance(data["capability_gaps"], list)
