"""Review pass: list marker files vs git, and print FAKE-SUCCESS candidates."""
import json
import os
import subprocess

STUB = "Auto-reconstructed backend component"
SKIP = {".git", "__pycache__", "venv", ".venv", "node_modules",
        ".hypothesis", ".pytest_cache"}

tracked = set(subprocess.run(["git", "ls-files"], capture_output=True, text=True,
                             encoding="utf-8").stdout.split())
disk = set()
for dp, dn, fn in os.walk("."):
    dn[:] = [d for d in dn if d not in SKIP]
    for f in fn:
        if f.endswith(".py"):
            p = os.path.join(dp, f)
            p = p[2:] if p.startswith("./") or p.startswith(".\\") else p
            p = p.replace(os.sep, "/")
            try:
                if STUB in open(p, encoding="utf-8", errors="ignore").read():
                    disk.add(p)
            except OSError:
                pass

print("marker files on disk (venv excluded):", len(disk))
venv_stubs = subprocess.run(
    ["python", "scripts/count_stubs.py", "venv"], capture_output=True, text=True,
    encoding="utf-8").stdout.strip()
print("count_stubs inside venv:", venv_stubs)
print("marker files tracked:", len([d for d in disk if d in tracked]))
print("marker files UNTRACKED:", sorted(d for d in disk if d not in tracked))

inv = json.load(open("inventory.json", encoding="utf-8"))
print("\n=== FAKE-SUCCESS candidates (function bodies) ===")
for c in inv["fake_success_candidates_reviewed"]:
    print("\n" + c["file"])
    for fn in c["funcs"]:
        name, ln, ret = (fn if isinstance(fn, list) else [fn, "", ""])
        print(f"    {name} (line {ln}) -> {ret}")
