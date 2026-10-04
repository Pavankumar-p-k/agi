"""STEP 2 — delete every file tagged STUB or FAKE-SUCCESS.

Deleting beats stubbing: a missing import fails immediately (ImportError),
a stub fails three layers deep as a mystery NoneType.

Safety model:
  1. every target is copied to rebuild_backlog/files/<path> first
  2. rebuild_backlog/BACKLOG.json records tag + evidence + test status
  3. tracked files are recoverable from git anyway; untracked ones only from here
  4. directories left with nothing but __pycache__ are removed too, so
     `import pkg` fails loudly instead of silently becoming a namespace package

Usage:  python scripts/step2_delete_nonreal.py [--apply]
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

BACKLOG = "rebuild_backlog"
PYTEST_LOGS = ["audit_pytest_unit.txt", "audit_pytest_arch.txt",
               "audit_pytest_int.txt", "audit_pytest_acc.txt"]
SKIP_DIRS = {".git", "__pycache__"}


def main() -> int:
    apply = "--apply" in sys.argv
    inv = json.load(open("inventory.json", encoding="utf-8"))
    targets = [e for e in inv["files"]
               if e["tag"] in ("STUB", "FAKE-SUCCESS")
               and not e["file"].endswith("(absent)")]
    exists = [t for t in targets if os.path.exists(t["file"])]
    missing = [t for t in targets if not os.path.exists(t["file"])]
    untracked = [t for t in exists if not t.get("tracked")]

    print(f"targets: {len(targets)}  (STUB "
          f"{sum(1 for t in targets if t['tag'] == 'STUB')}, FAKE-SUCCESS "
          f"{sum(1 for t in targets if t['tag'] == 'FAKE-SUCCESS')})")
    print(f"  on disk: {len(exists)}   already gone: {len(missing)}")
    print(f"  git-tracked (recoverable via git): {len(exists) - len(untracked)}")
    print(f"  UNTRACKED/gitignored (recoverable ONLY from backlog): "
          f"{[t['file'] for t in untracked]}")
    if not apply:
        print("\n(dry run — pass --apply to delete)")
        return 0

    # 1. backlog: copy + record
    for t in exists:
        dst = os.path.join(BACKLOG, "files", t["file"])
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if not os.path.exists(dst):
            shutil.copy2(t["file"], dst)
    backlog = [{"file": t["file"], "tag": t["tag"], "loc": t.get("loc"),
                "tracked": t.get("tracked"), "tests": t.get("tests"),
                "evidence": t.get("evidence"), "test_files": t.get("test_files"),
                "restore": f"cp rebuild_backlog/files/{t['file']} {t['file']}"}
               for t in targets]
    os.makedirs(BACKLOG, exist_ok=True)
    with open(os.path.join(BACKLOG, "BACKLOG.json"), "w", encoding="utf-8") as fh:
        json.dump({"count": len(backlog),
                   "STUB": sum(1 for b in backlog if b["tag"] == "STUB"),
                   "FAKE-SUCCESS": sum(1 for b in backlog
                                       if b["tag"] == "FAKE-SUCCESS"),
                   "files": backlog}, fh, indent=1)

    # 2. delete
    deleted = 0
    for t in exists:
        try:
            os.remove(t["file"])
            deleted += 1
        except OSError as e:
            print(f"FAILED {t['file']}: {e}")

    # 3. prune directories that now hold nothing but __pycache__ (so imports
    #    fail loudly instead of resolving as silent namespace packages)
    pruned = []
    for dp, dn, fn in os.walk(".", topdown=False):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        rel = os.path.relpath(dp, ".").replace(os.sep, "/")
        if rel in (".", "") or rel.startswith(("./", "venv", ".git")):
            continue
        entries = [e for e in os.listdir(dp) if e != "__pycache__"]
        if not entries:
            shutil.rmtree(dp, ignore_errors=True)
            pruned.append(rel)

    with open(os.path.join(BACKLOG, "DELETED.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(sorted(t["file"] for t in exists)) + "\n")

    print(f"\nbacked up {len(exists)} files -> {BACKLOG}/files/")
    print(f"BACKLOG.json written ({len(backlog)} entries)")
    print(f"deleted {deleted} files")
    print(f"pruned {len(pruned)} now-empty dirs: {pruned[:20]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
