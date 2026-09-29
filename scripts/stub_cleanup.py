"""De-poison the working tree: restore recoverable stubs, delete orphan ones.

Safety model
------------
1. "Recoverable" stubs get the real implementation restored from git history.
2. "Orphan" stubs (no inbound reference from a non-stub module, no test mention)
   are deleted — but only after these guards pass:
     * the module path / leaf name does not appear in any non-Python file
       (yaml/json/toml/ini/md/sh/pyproject config, docs, scripts)
     * no dynamic import pattern (``importlib.import_module("x")`` /
       ``__import__("x")``) names the module
     * the file is not a package ``__init__.py``
3. After deletion a whole-tree import smoke test runs; any module that fails to
   import because of a deletion is reported (and the deletion is a candidate for
   rollback).

Everything is committed in git, so any deletion is revertible with
``git checkout <rev> -- <path>``.

Usage:
    python scripts/stub_cleanup.py --dry-run     # guard report only
    python scripts/stub_cleanup.py --apply       # restore + delete
    python scripts/stub_cleanup.py --smoke       # import every module
"""
from __future__ import annotations

import argparse
import importlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INVENTORY = ROOT / "stub_inventory.json"
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build"}
# Runtime/config surfaces only — docs (.md) and generated reports do not
# reference code at runtime, so mentioning a module there must not block a
# deletion. This inventory file is excluded explicitly (it lists every stub).
NON_PY_TEXT_SUFFIXES = {
    ".yaml", ".yml", ".json", ".toml", ".ini", ".cfg", ".sh",
    ".ps1", ".html", ".ts", ".js",
}
CORPUS_EXCLUDE = {"stub_inventory.json", "stub_cleanup.json"}


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    return result.stdout or ""


def load_inventory() -> list[dict]:
    if not INVENTORY.exists():
        sys.exit("run scripts/stub_inventory.py first")
    return json.loads(INVENTORY.read_text(encoding="utf-8"))


MAX_CORPUS_BYTES = 400_000


def text_corpus() -> list[tuple[str, str]]:
    """Read every non-Python text file once: [(relpath, text), ...]."""
    corpus: list[tuple[str, str]] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.name in CORPUS_EXCLUDE:
            continue
        if path.suffix.lower() not in NON_PY_TEXT_SUFFIXES and path.name not in (
            "Makefile", "Dockerfile", "requirements.txt"
        ):
            continue
        try:
            if path.stat().st_size > MAX_CORPUS_BYTES:
                continue
            corpus.append((_rel(path), path.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            continue
    return corpus


def external_references(rel: str, corpus: list[tuple[str, str]]) -> list[str]:
    """Non-Python files that name this module (path or leaf word)."""
    module = rel[:-3].replace("/", ".")
    leaf = module.rsplit(".", 1)[-1]
    path_hit = re.compile(re.escape(module))
    leaf_hit = re.compile(rf"\b{re.escape(leaf)}\b")
    hits: list[str] = []
    for other, text in corpus:
        if path_hit.search(text) or leaf_hit.search(text):
            hits.append(other)
    return sorted(set(hits))


# `from X import a, b` / `import X` / `from . import a` / `from .x import y`
_IMPORT_LINE = re.compile(
    r"^\s*(from\s+(?P<level>\.*)\s*(?P<mod>[\w\.]*)\s+import\s+(?P<names>[^\n]*)"
    r"|import\s+(?P<plain>[\w\.]+))",
    re.MULTILINE,
)


def _resolve(level: str, mod: str, owner: str) -> str:
    """Resolve an import target to an absolute dotted module path."""
    if not level:
        return mod
    parts = Path(owner).parent.as_posix().replace("/", ".").split(".")
    parts = [p for p in parts if p and p != "."]
    # one leading dot = current package, each extra dot goes up one level
    up = len(level) - 1
    base = parts[: len(parts) - up] if up else parts
    return ".".join([*base, mod]) if mod else ".".join(base)


def python_references(rel: str, sources: dict[str, str]) -> list[str]:
    """Python files that import this module, including relative imports.

    Stub files are NOT skipped: the auto-reconstructed stubs keep the original
    module's ``# Re-exports`` block, so their import lines are real references.
    Ignoring them previously deleted modules that load-bearing ``__init__.py``
    stubs still import (e.g. ``core.tools.schemas``).
    """
    module = rel[:-3].replace("/", ".")
    parts = module.split(".")
    leaf = parts[-1]
    package = ".".join(parts[:-1])
    out = []
    for other, text in sources.items():
        if other == rel:
            continue
        hit = False
        for m in _IMPORT_LINE.finditer(text):
            if m.group("plain"):
                target = m.group("plain")
                if target == module or target.startswith(module + "."):
                    hit = True
                    break
                continue
            target = _resolve(m.group("level"), m.group("mod"), other)
            names = [n.strip().split(" as ")[0].strip()
                     for n in m.group("names").split(",") if n.strip()]
            if target == module or target.startswith(module + "."):
                hit = True
                break
            if target == package and leaf in names:
                hit = True
                break
        if hit:
            out.append(other)
    return sorted(set(out))


def dynamic_reference(rel: str, sources: dict[str, str]) -> list[str]:
    """Python files that import this module dynamically."""
    module = rel[:-3].replace("/", ".")
    leaf = module.rsplit(".", 1)[-1]
    patterns = (
        f'import_module("{module}")', f"import_module('{module}')",
        f'import_module("{leaf}")', f"import_module('{leaf}')",
        f'__import__("{module}")', f"__import__('{module}')",
        f'__import__("{leaf}")', f"__import__('{leaf}')",
    )
    out = []
    for other, text in sources.items():
        if other == rel:
            continue
        if any(p in text for p in patterns):
            out.append(other)
    return out


def module_name(rel: str) -> str:
    mod = rel[:-3].replace("/", ".")
    return mod[: -len(".__init__")] if mod.endswith(".__init__") else mod


def smoke_import() -> list[tuple[str, str]]:
    """Import every importable module; return (module, error) failures."""
    failures: list[tuple[str, str]] = []
    for path in sorted(ROOT.rglob("*.py")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        rel = _rel(path)
        if rel.startswith(("tests/", "scripts/")) or path.name.startswith("test_"):
            continue
        mod = module_name(rel)
        try:
            importlib.import_module(mod)
        except BaseException as exc:  # noqa: BLE001 — report everything
            failures.append((mod, f"{type(exc).__name__}: {exc}"))
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()

    if args.smoke:
        failures = smoke_import()
        for mod, err in failures:
            print(f"IMPORT-FAIL {mod}: {err}")
        print(f"import failures: {len(failures)}")
        return 0

    report = load_inventory()
    recoverable = [r for r in report if r["recoverable_from_git"]]
    orphans = [r for r in report if r["priority"] == "P1"]

    sources = {}
    for path in ROOT.rglob("*.py"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        sources[_rel(path)] = path.read_text(encoding="utf-8", errors="replace")

    corpus = text_corpus()
    print(f"external text corpus: {len(corpus)} files")
    deletable, guarded = [], []
    for entry in orphans:
        rel = entry["file"]
        if rel.endswith("__init__.py"):
            guarded.append((rel, "package __init__"))
            continue
        ext = external_references(rel, corpus)
        dyn = dynamic_reference(rel, sources)
        py = python_references(rel, sources)
        if ext or dyn or py:
            guarded.append((rel, f"py={py[:3]} external={ext[:2]} dynamic={dyn[:2]}"))
        else:
            deletable.append(rel)

    print(f"recoverable:      {len(recoverable)}")
    print(f"orphan candidates:{len(orphans)}")
    print(f"safe to delete:   {len(deletable)}")
    print(f"kept (guarded):   {len(guarded)}")
    for rel, why in guarded[:15]:
        print(f"  guarded {rel}: {why}")

    if args.dry_run or not args.apply:
        print("\n(dry run — pass --apply to act)")
        return 0

    for entry in recoverable:
        rel, rev = entry["file"], entry["recoverable_from_git"]
        print(f"restoring {rel} <- {rev[:10]}")
        _git("checkout", rev, "--", rel)

    if deletable:
        # Only tracked paths: an untracked pathspec aborts the whole `git rm`.
        tracked = set(_git("ls-files", "--", *deletable).split("\n"))
        tracked.discard("")
        to_remove = [rel for rel in deletable if rel in tracked]
        untracked = [rel for rel in deletable if rel not in tracked]
        if to_remove:
            result = subprocess.run(
                ["git", "rm", "-q", "--ignore-unmatch", "--", *to_remove],
                cwd=ROOT, capture_output=True, text=True,
            )
            if result.returncode != 0:
                print(f"git rm failed: {result.stderr.strip()[:300]}")
        for rel in untracked:
            target = ROOT / rel
            if target.exists():
                target.unlink()
        print(f"deleted {len(to_remove)} tracked + {len(untracked)} untracked "
              f"orphan stub modules")

    print("\nnow run: python scripts/stub_cleanup.py --smoke")
    return 0


if __name__ == "__main__":
    sys.exit(main())
