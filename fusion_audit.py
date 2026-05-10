import os

def build_manifest(dirpath):
    manifest = []
    for root, _, files in os.walk(dirpath):
        if ".venv" in root or ".git" in root or "tests" in root or "data" in root:
            continue
        for f in files:
            if f.endswith(".py"):
                manifest.append(os.path.relpath(os.path.join(root, f), dirpath))
    return set(manifest)

local_files = build_manifest(".")
v9_files = build_manifest(os.path.join("jarvis_v9_final", "jarvis_v9"))
mythos_files = build_manifest(os.path.join("mythos_v19_final", "mythos_v19"))

def filename_map(file_set):
    res = {}
    for f in file_set:
        basename = os.path.basename(f)
        if basename not in res:
            res[basename] = []
        res[basename].append(f)
    return res

local_map = filename_map(local_files)
v9_map = filename_map(v9_files)
mythos_map = filename_map(mythos_files)

all_basenames = set(local_map.keys()) | set(v9_map.keys()) | set(mythos_map.keys())

artifact_path = r"C:\Users\peter\.gemini\antigravity\brain\45fbd691-6024-446b-b5a4-1457dda8e256\SOVEREIGN_AUDIT.md"

with open(artifact_path, "w") as f:
    f.write("# SOVEREIGN FUSION PROTOCOL: STRUCTURAL AUDIT\n\n")
    f.write("## 1. DUPLICATE MATRIX (COLLISIONS DETECTED)\n")
    for b in sorted(all_basenames):
        if b == "__init__.py": continue
        locs = []
        if b in local_map: locs.append(f"Local: {local_map[b]}")
        if b in v9_map: locs.append(f"V9: {v9_map[b]}")
        if b in mythos_map: locs.append(f"Mythos: {mythos_map[b]}")
        
        if len(locs) > 1:
            f.write(f"### File: `{b}`\n")
            for l in locs:
               f.write(f"- {l}\n")
            f.write("\n")

    f.write("## 2. ORPHANS / UNIQUE SUB-SYSTEMS IN IMPORTED REPOS\n")
    for b in sorted(v9_map.keys()):
        if b not in local_map and b not in mythos_map and b != "__init__.py":
            f.write(f"- [V9 Only] `{v9_map[b][0]}`\n")
    for b in sorted(mythos_map.keys()):
        if b not in local_map and b not in v9_map and b != "__init__.py":
            f.write(f"- [Mythos Only] `{mythos_map[b][0]}`\n")

print("Audit script executed. See SOVEREIGN_AUDIT.md")
