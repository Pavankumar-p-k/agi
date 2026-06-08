import ast
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]


def _get_imports(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        try:
            tree = ast.parse(f.read())
        except Exception:
            return []
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                imports.append(n.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


def test_core_layer_boundaries():
    core_dir = BASE_DIR / "core"
    for py_file in core_dir.glob("**/*.py"):
        if py_file.name in ("__init__.py", "main.py"):
            continue
        imports = _get_imports(py_file)
        for imp in imports:
            assert not imp.startswith("api"), (
                f"Core file {py_file.relative_to(BASE_DIR)} imports api: {imp}"
            )
            assert not imp.startswith("apps"), (
                f"Core file {py_file.relative_to(BASE_DIR)} imports apps: {imp}"
            )


def test_brain_layer_boundaries():
    brain_dir = BASE_DIR / "brain"
    if not brain_dir.exists():
        return
    for py_file in brain_dir.glob("**/*.py"):
        imports = _get_imports(py_file)
        for imp in imports:
            assert not imp.startswith("api"), (
                f"Brain file {py_file.relative_to(BASE_DIR)} imports api: {imp}"
            )
            assert not imp.startswith("apps"), (
                f"Brain file {py_file.relative_to(BASE_DIR)} imports apps: {imp}"
            )


def test_memory_layer_boundaries():
    memory_dir = BASE_DIR / "memory"
    if not memory_dir.exists():
        return
    for py_file in memory_dir.glob("**/*.py"):
        imports = _get_imports(py_file)
        for imp in imports:
            assert not imp.startswith("api"), (
                f"Memory file {py_file.relative_to(BASE_DIR)} imports api: {imp}"
            )
            assert not imp.startswith("brain"), (
                f"Memory file {py_file.relative_to(BASE_DIR)} imports brain: {imp}"
            )
