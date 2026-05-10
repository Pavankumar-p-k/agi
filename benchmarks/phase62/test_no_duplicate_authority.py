import ast
from pathlib import Path


CLASS_OWNER = {
    "PlanningEngine": "jarvis_os/core/planner.py",
    "RuntimeGovernanceLayer": "jarvis_os/RuntimeGovernanceLayer.py",
    "ModelRuntimeManager": "jarvis_os/model_runtime_manager.py",
    "MemoryManager": "jarvis_os/memory/memory_manager.py",
    "ExecutionEngine": "jarvis_os/core/executor.py",
    "AgentLoop": "jarvis_os/core/loop.py",
}


def test_no_duplicate_authority_owners():
    root = Path(".")
    flagged = []
    for path in root.rglob("*.py"):
        rel = path.as_posix()
        if any(part in rel for part in ("benchmarks/", "archive/", "__pycache__", ".venv")):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            owner = CLASS_OWNER.get(node.name)
            if owner and owner != rel:
                flagged.append(f"{rel}:{node.name}")
    assert flagged == []
