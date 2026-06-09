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
from core.tools.policy import ToolPolicy, policy_engine


def register_default_policies():
    """Register default policies for high-risk tools."""

    # Bash: Requires confirmation if not in YOLO mode
    policy_engine.register(ToolPolicy(
        id="bash",
        name="Bash Shell",
        description="Execute arbitrary shell commands. High risk.",
        risk_level="high",
        needs_confirmation=True,
        required_scope="tools:execute:high"
    ))

    # Write File: Requires confirmation
    policy_engine.register(ToolPolicy(
        id="write_file",
        name="Write File",
        description="Write or overwrite files on disk.",
        risk_level="medium",
        needs_confirmation=True,
        required_scope="tools:execute:medium"
    ))

    # Python: Requires confirmation
    policy_engine.register(ToolPolicy(
        id="python",
        name="Python Interpreter",
        description="Execute Python code. High risk.",
        risk_level="high",
        needs_confirmation=True,
        required_scope="tools:execute:high"
    ))

    # Computer: High risk
    policy_engine.register(ToolPolicy(
        id="computer",
        name="Computer Control",
        description="Execute natural language commands on the PC.",
        risk_level="high",
        needs_confirmation=True,
        required_scope="tools:execute:high"
    ))

    # Browser Navigate: Medium risk
    policy_engine.register(ToolPolicy(
        id="browser_navigate",
        name="Browser Navigate",
        description="Navigate the browser to a specific URL.",
        risk_level="medium",
        needs_confirmation=True,
        required_scope="tools:execute:medium"
    ))

    # Delete Email: Requires confirmation
    policy_engine.register(ToolPolicy(
        id="delete_email",
        name="Delete Email",
        description="Move email to trash or delete permanently.",
        risk_level="medium",
        needs_confirmation=True,
        required_scope="tools:execute:high"
    ))

    # --- Management Tools ---
    policy_engine.register(ToolPolicy(
        id="manage_memory",
        name="Manage Memory",
        required_scope="memory:write"
    ))

    policy_engine.register(ToolPolicy(
        id="manage_skills",
        name="Manage Skills",
        required_scope="tools:execute:medium"
    ))

register_default_policies()
