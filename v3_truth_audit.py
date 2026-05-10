import ast
import os
from pathlib import Path

def analyze_theater(filepath):
    results = []
    if not os.path.exists(filepath):
        return results

    with open(filepath, "r", encoding="utf-8-sig") as f:
        content = f.read()

    try:
        tree = ast.parse(content)
    except SyntaxError as exc:
        return [f"PARSE ERROR: `{os.path.basename(filepath)}` could not be parsed ({exc.msg} at line {exc.lineno})."]
    
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            func_name = node.name
            
            # Check for self-repair theater (recommends but doesn't write)
            if "patch" in func_name.lower() or "repair" in func_name.lower() or "fix" in func_name.lower():
                writes_files = False
                for stmt in ast.walk(node):
                    if isinstance(stmt, ast.Call):
                        if isinstance(stmt.func, ast.Name) and stmt.func.id == "open":
                            writes_files = True
                        elif isinstance(stmt.func, ast.Attribute) and stmt.func.attr == "write_text":
                            writes_files = True
                        elif isinstance(stmt.func, ast.Attribute) and stmt.func.attr == "system":
                            writes_files = True
                
                if not writes_files:
                    results.append(f"THEATER DETECTED: Function `{func_name}` in {os.path.basename(filepath)} appears to log or advise repairs but lacks file I/O or system execution abilities.")
                    
            # Check for governance theater (logs but doesn't raise errors or block)
            if "enforce" in func_name.lower() or "validate" in func_name.lower() or "audit" in func_name.lower():
                enforces = False
                for stmt in ast.walk(node):
                    if isinstance(stmt, ast.Raise):
                        enforces = True
                    if isinstance(stmt, ast.Return):
                        # Returning false or None is passive blocking, but exception raising is preferred
                        pass
                if not enforces:
                    results.append(f"WEAK GOVERNANCE: Function `{func_name}` in {os.path.basename(filepath)} validates but does not explicitly raise hard boundaries (Exceptions).")
            if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                results.append(f"UNREACHABLE/EMPTY: Function `{func_name}` in {os.path.basename(filepath)} is a placeholder (`pass`).")

    return results

def main():
    workspace = Path(os.getcwd())
    targets = [
        str(path.relative_to(workspace)).replace("\\", "/")
        for path in workspace.rglob("*.py")
        if ".venv" not in path.parts and "__pycache__" not in path.parts
    ]
    
    report = []
    for t in targets:
        theater = analyze_theater(os.path.join(os.getcwd(), t))
        report.extend(theater)
        
    print("--- TRUTH AUDIT RESULTS ---")
    for r in report:
        print(r)

    os.makedirs("reports", exist_ok=True)
    with open("reports/SOVEREIGN_TRUTH_REPORT.md", "w", encoding="utf-8") as f:
        f.write("# SOVEREIGN TRUTH REPORT - PHASE 5\n\n")
        f.write("## 1. Audited Targets\n")
        for t in targets:
            f.write(f"- `{t}`\n")
        f.write("\n## 2. Theater Detection Results\n")
        if not report:
            f.write("System passed. No symbolic layer theater detected.\n")
        else:
            for r in report:
                f.write(f"- ⚠️ {r}\n")
        
        f.write("\n## 3. Verdict\n")
        f.write("The system exhibits `Architecturally Advanced Prototype` behavior in some self-repair functions. True V2 Sovereign state requires these components to generate physical patches and execute them natively.")

if __name__ == "__main__":
    main()
