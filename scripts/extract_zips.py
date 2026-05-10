import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
out = root / "extracted_zips"
out.mkdir(exist_ok=True)

for zipf in root.glob("jarvis_*.zip"):
    dest = out / zipf.stem
    dest.mkdir(exist_ok=True)
    print(f"Extracting {zipf.name} -> {dest}")
    with zipfile.ZipFile(zipf, "r") as z:
        z.extractall(dest)
print("Done.")
