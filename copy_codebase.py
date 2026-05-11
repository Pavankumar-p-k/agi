"""Copy entire codebase into 20 files in copy/ dir."""
import os
import sys

ROOT = r"C:\Users\peter\Desktop\jarvis"
OUT_DIR = os.path.join(ROOT, "copy")
TOTAL_FILES = 20

EXCLUDE_DIRS = {
    "__pycache__", ".git", "node_modules", ".venv", "venv",
    ".aider", ".github", ".pytest_cache",
}
EXCLUDE_PARTS = {
    "__pycache__", ".git", "node_modules", ".venv", "tmp", "tmp_pytest",
    ".aider", ".github", ".pytest_cache", ".dart_tool", "build", ".gradle",
    "Pods", ".symlinks", "flutter_export_environment", ".packages"
}
EXCLUDE_EXTS = {
    ".pyc", ".pyo", ".pyd", ".so", ".dll", ".dylib",
    ".exe", ".bin", ".zip", ".tar", ".gz", ".7z", ".rar",
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".ico", ".webp", ".svg",
    ".mp3", ".mp4", ".wav", ".flac", ".ogg", ".mov", ".avi",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".ttf", ".otf", ".woff", ".woff2", ".eot",
    ".o", ".a", ".lib", ".obj",
    ".db", ".db-shm", ".db-wal", ".db-journal",
    ".jsonl",
    ".class", ".jar", ".kotlin_module",
    ".iml", ".idea",
    ".lock", ".cache",
    ".gradle", ".kts",
    ".hprof", ".snap",
    ".pdb",
}

def should_exclude(path):
    parts = path.replace("\\", "/").split("/")
    for p in parts:
        if p in EXCLUDE_PARTS or p.startswith("tmp"):
            return True
    ext = os.path.splitext(path)[1].lower()
    if ext in EXCLUDE_EXTS:
        return True
    name = os.path.basename(path)
    if name.startswith("tmp") and os.path.isdir(path):
        return True
    return False

# Collect all text files
all_files = []
for dirpath, dirnames, filenames in os.walk(ROOT):
    skip_dirs = {"__pycache__", "tmp", "tmp_pytest", "archive", "jarvis_fixed_files",
                 "data", "build", ".dart_tool", ".gradle", "Pods", ".symlinks",
                 ".idea", "node_modules", ".venv", ".git",
                 ".pub-cache", "flutter_export_environment", ".packages",
                 "copy", "ephemeral", "flutter"}
    dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.startswith("tmp")]
    for f in filenames:
        full = os.path.join(dirpath, f)
        ext = os.path.splitext(f)[1].lower()
        if ext in EXCLUDE_EXTS:
            continue
        if should_exclude(full):
            continue
        rel = os.path.relpath(full, ROOT)
        all_files.append((rel, full))

all_files.sort()
print(f"Found {len(all_files)} text files")

# Build mega-content
all_content = []
for rel, full in all_files:
    try:
        with open(full, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        header = f"\n{'='*80}\nFILE: {rel}\n{'='*80}\n"
        all_content.append(header + text)
    except Exception as e:
        all_content.append(f"\n{'='*80}\nFILE: {rel}\n{'='*80}\n[ERROR READING: {e}]\n")

# Calculate total lines
total_lines = sum(c.count("\n") for c in all_content)
lines_per_chunk = max(total_lines // TOTAL_FILES, 1)

print(f"Total lines: {total_lines}")
print(f"Lines per chunk: {lines_per_chunk}")

# Create output directory
os.makedirs(OUT_DIR, exist_ok=True)

# Split into chunks
chunk_lines = [[]]
current_lines = 0

for item in all_content:
    item_lines = item.count("\n")
    overflow = current_lines + item_lines > lines_per_chunk
    if overflow and current_lines > 0 and len(chunk_lines) < TOTAL_FILES:
        chunk_lines.append([])
        current_lines = 0
    chunk_lines[-1].append(item)
    current_lines += item_lines

# Write chunks
for i, items in enumerate(chunk_lines):
    out_path = os.path.join(OUT_DIR, f"part_{i+1:02d}_of_{TOTAL_FILES:02d}.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"JARVIS CODEBASE - PART {i+1}/{TOTAL_FILES}\n")
        f.write(f"{'='*80}\n\n")
        for item in items:
            f.write(item)
            f.write("\n")
    print(f"Written: {out_path} ({len(items)} files)")

print(f"\nDone! {len(chunk_lines)} files written to {OUT_DIR}")
