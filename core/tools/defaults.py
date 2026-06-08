from core.tools.policy import policy_engine, ToolPolicy

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
