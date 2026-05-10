import os
import ast

def analyze_and_purge(root_dir):
    deleted = []
    fake_modules = []
    
    for dirpath, _, filenames in os.walk(root_dir):
        if ".venv" in dirpath or ".git" in dirpath or "data" in dirpath or "tests" in dirpath:
            continue
        for file in filenames:
            if not file.endswith(".py"):
                continue
            filepath = os.path.join(dirpath, file)
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue
            
            class FunctionVisitor(ast.NodeVisitor):
                def __init__(self):
                    self.total_funcs = 0
                    self.empty_funcs = 0
                    
                def visit_FunctionDef(self, node):
                    self.total_funcs += 1
                    # check if the body only contains pass, docstring, or NotImplementedError
                    is_empty = True
                    for stmt in node.body:
                        if isinstance(stmt, ast.Pass):
                            continue
                        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
                            continue
                        if isinstance(stmt, ast.Raise):
                            if isinstance(stmt.exc, ast.Call) and getattr(stmt.exc.func, "id", "") in ("NotImplementedError", "Exception"):
                                continue
                            if getattr(stmt.exc, "id", "") in ("NotImplementedError", "Exception"):
                                continue
                        is_empty = False
                    if is_empty:
                        self.empty_funcs += 1
                    self.generic_visit(node)
                    
                def visit_AsyncFunctionDef(self, node):
                    self.visit_FunctionDef(node)

            visitor = FunctionVisitor()
            visitor.visit(tree)
            
            # Identify fake architecture: if the file has functions, and ALL of them are empty/NotImplemented. Or zero functions and just classes with pass.
            if visitor.total_funcs > 0 and visitor.total_funcs == visitor.empty_funcs:
                fake_modules.append(filepath)
                os.remove(filepath)
                deleted.append(filepath)
            elif visitor.total_funcs == 0 and sum(1 for node in ast.walk(tree) if isinstance(node, ast.ClassDef)) > 0:
                 # Check if all classes just have 'pass' or docstrings
                 all_empty_classes = True
                 for node in ast.walk(tree):
                     if isinstance(node, ast.ClassDef):
                         for stmt in node.body:
                             if not (isinstance(stmt, ast.Pass) or (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant))):
                                 all_empty_classes = False
                 if all_empty_classes:
                     fake_modules.append(filepath)
                     os.remove(filepath)
                     deleted.append(filepath)

    return deleted, fake_modules

if __name__ == "__main__":
    d, f = analyze_and_purge(".")
    print("DELETED FAKE MODULES:")
    for m in d:
        print(f" - {m}")
