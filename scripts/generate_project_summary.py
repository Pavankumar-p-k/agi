"""Generate a summary of the JARVIS project structure.

Run this script from the repo root to print an overview of directories, key modules, and file counts.
"""

import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(ROOT, "backend")

print("PROJECT ROOT:", ROOT)
print("\nTOP-LEVEL DIRECTORIES:")
for name in sorted(os.listdir(ROOT)):
    path = os.path.join(ROOT, name)
    if os.path.isdir(path):
        print(" -", name)

print("\nBACKEND DIRECTORIES (top-level):")
for name in sorted(os.listdir(BACKEND)):
    path = os.path.join(BACKEND, name)
    if os.path.isdir(path):
        print(" -", name)

# Count python files
py_files = []
for dirpath, dirnames, filenames in os.walk(BACKEND):
    for f in filenames:
        if f.endswith(".py"):
            py_files.append(os.path.join(dirpath, f))

print(f"\nTotal Python files in backend: {len(py_files)}")

# Count key features
print("\nKey modules (sample):")
print(" - core")
print(" - assistant")
print(" - autonomy")
print(" - automation")
print(" - learning")
print(" - api")
print(" - data")
print(" - services")

# Show some key entry points
print("\nKey entry points:")
print(" - jarvis_main.py (starts FastAPI server)")
print(" - backend/core/main.py (FastAPI app and route mounts)")
print(" - backend/autonomy/api/autonomous_routes.py (autonomous endpoints)")
print(" - backend/learning/student_agi/student_agi_main.py (student AGI service)")
