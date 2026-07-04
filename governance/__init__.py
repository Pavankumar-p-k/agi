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
"""Jarvis Governance Layer — policies, circuit breaking, runtime enforcement.

Architecture layers:
  1. Input:    GovernanceValidator — keyword blocklist + LLM semantic classification
  2. Runtime:  RuntimeGovernanceLayer — request budget, concurrency limits, circuit breaker
  3. Rate:     core/rate_limiter.py — per-IP/scope sliding window
  4. Auth:     core/auth.py — loopback bypass (dev mode)
  5. Desktop:  core/desktop/safety.py — emergency stop, mouse/keyboard rate limits
  6. Execution: core/sandbox/ — Docker isolation
  7. Loop:     MetaGovernor — continuous observe→analyze→decide→act→learn (EXPERIMENTAL)
"""
from governance.exceptions import GovernanceViolation
from governance.RuntimeGovernanceLayer import RuntimeGovernanceLayer, runtime_governance
from governance.GovernanceValidator import GovernanceValidator
from governance.MetaGovernor import MetaGovernor

__all__ = [
    "GovernanceViolation",
    "RuntimeGovernanceLayer", 
    "runtime_governance",
    "GovernanceValidator",
    "MetaGovernor",
]
