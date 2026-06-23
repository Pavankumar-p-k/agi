FUNCTION_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "build_project",
            "description": "Build a project from source, auto-repairing on failure. Creates a build plan, generates files, runs static verification, builds with targeted repair, tests, and validates the runtime.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "Build task description (e.g. 'Build Android app', 'Build Python package')"},
                    "project_dir": {"type": "string", "description": "Absolute path to the project directory"}
                },
                "required": ["task", "project_dir"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "repair_project",
            "description": "Repair a project based on build errors or analysis results. Uses the compiler repair engine with failure memory to fix build issues.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_dir": {"type": "string", "description": "Absolute path to the project directory"},
                    "build_output": {"type": "string", "description": "Build output or error log to analyze for repair", "default": ""}
                },
                "required": ["project_dir"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_tests",
            "description": "Run the project's test suite and report results. Uses the automation pipeline's phase_test to execute tests consistently.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_dir": {"type": "string", "description": "Absolute path to the project directory"},
                    "test_command": {"type": "string", "description": "Optional custom test command override", "default": ""}
                },
                "required": ["project_dir"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "runtime_validate",
            "description": "Run runtime validation checks on a built project. Verifies the project starts, responds, and behaves correctly after build.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_dir": {"type": "string", "description": "Absolute path to the project directory"}
                },
                "required": ["project_dir"]
            }
        }
    },
]
