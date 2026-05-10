import shutil
from pathlib import Path

root = Path(__file__).resolve().parents[1]
ex_root = root / "extracted_zips"

if not ex_root.exists():
    raise SystemExit("No extracted_zips folder found")

for zip_dir in sorted(ex_root.iterdir()):
    if not zip_dir.is_dir():
        continue

    # If extracted folder contains a single directory, use that as the source.
    children = [p for p in zip_dir.iterdir() if p.name not in ("__MACOSX",)]
    if len(children) == 1 and children[0].is_dir():
        src = children[0]
    else:
        src = zip_dir

    dest_name = src.name
    dest = root / dest_name

    # If destination exists, find a new name
    if dest.exists():
        i = 1
        while True:
            candidate = root / f"{dest_name}_fromzip{i}"
            if not candidate.exists():
                dest = candidate
                break
            i += 1

    print(f"Merging {src} -> {dest}")
    shutil.copytree(src, dest)

print("Integration complete. Please review and resolve any conflicts.")
