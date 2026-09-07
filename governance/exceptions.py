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
class GovernanceViolation(Exception):
    """Raised when a governance policy is violated."""
    def __init__(self, policy: str, reason: str = "Unspecified violation", severity: str = "warning"):
        self.policy = policy
        self.reason = reason
        self.severity = severity
        super().__init__(f"[{severity.upper()}] {policy}: {reason}")

class SecurityViolation(Exception):
    """Raised when a security boundary is crossed or bypassed."""

class RuntimeBoundaryViolation(Exception):
    """Raised when runtime enters an unsafe or undefined operating boundary."""
