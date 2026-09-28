"""De-poisoning inventory + transformer for DynamicStub-polluted modules.

Commands:
    inventory            classify every matched file and list actionable ones
    transform [--apply]  rewrite poison-pure modules (dry-run without --apply)
    verify               re-run inventory (post-transform check)

Classification (per file):
    poison_pure          module-level __getattr__ that only returns `name` or
                         a DynamicStub()/DynamicMeta() call — mechanical fix.
    poison_lazy_fallback getattr mixes real import machinery WITH name
                         swallowing — MANUAL (worst kind; may be deliberate).
    poison_mixed         getattr with other real logic — MANUAL.
    lazy_import          PEP 562 lazy submodule import only — healthy.
    honest               getattr already raises — healthy.
    class_stub           defines DynamicStub/DynamicMeta but no module-level
                         getattr (stub used inside methods) — MANUAL.
    clean                text match only (comments/docstrings).
    excluded             under the planner/pipeline/agents/specialist boundary.

Never modifies: core/planner, core/pipeline, core/agents, core/browser,
core/coding, core/desktop.  Never deletes files, never touches tests.
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXCLUDED_PREFIXES = (
    "core/planner/",
    "core/pipeline/",
    "core/agents/",
    "core/browser/",
    "core/coding/",
    "core/desktop/",
)

SEARCH_ROOTS = ("core", "tools", "memory", "learning", "jarvis_mcp", "provider_sdk", "routes", "scripts", "cli")

HEALTHY = {"honest", "lazy_import", "clean", "no_match", "excluded"}
MANUAL = {"poison_mixed", "poison_lazy_fallback", "class_stub", "unreadable", "syntax_error"}


def is_excluded(rel: str) -> bool:
    return rel.startswith(EXCLUDED_PREFIXES)


def iter_candidate_files():
    for root in SEARCH_ROOTS:
        base = ROOT / root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            yield path
    for path in sorted(ROOT.glob("*.py")):
        yield path


def _has_stub_class(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name in ("DynamicStub", "DynamicMeta"):
            return True
    return False


def _module_getattr(tree: ast.Module):
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "__getattr__":
            return node
    return None


def _called_name(node: ast.AST) -> str:
    func = getattr(node, "func", None)
    if func is None:
        return ""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def classify(tree: ast.Module) -> str:
    fn = _module_getattr(tree)
    has_stub = _has_stub_class(tree)
    if fn is None:
        return "class_stub" if has_stub else "clean"

    returns_name = False
    returns_stub = False
    has_import = False
    has_raise = False
    for sub in ast.walk(fn):
        if isinstance(sub, ast.Return):
            value = sub.value
            if isinstance(value, ast.Name) and value.id == "name":
                returns_name = True
            if isinstance(value, ast.Call) and _called_name(value) in ("DynamicStub", "DynamicMeta"):
                returns_stub = True
        elif isinstance(sub, (ast.Import, ast.ImportFrom)):
            has_import = True
        elif isinstance(sub, ast.Raise):
            has_raise = True

    # Entanglement: any real module-level class or function means the stub
    # machinery shares the file with genuine code — manual handling only.
    real_defs = [
        n for n in tree.body
        if (isinstance(n, ast.ClassDef) and n.name not in ("DynamicStub", "DynamicMeta"))
        or (isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name != "__getattr__")
    ]

    if has_raise:
        return "honest"
    if has_import and (returns_name or returns_stub):
        return "poison_lazy_fallback"
    if has_import:
        return "lazy_import"
    if returns_name or returns_stub:
        return "poison_mixed" if real_defs else "poison_pure"
    return "poison_mixed"


def analyze(path: Path) -> dict:
    rel = path.relative_to(ROOT).as_posix().replace("\\", "/")
    if is_excluded(rel):
        return {"path": rel, "category": "excluded"}
    try:
        src = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as exc:
        return {"path": rel, "category": "unreadable", "detail": str(exc)}
    if "DynamicStub" not in src and "DynamicMeta" not in src and "__getattr__" not in src:
        return {"path": rel, "category": "no_match"}
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        return {"path": rel, "category": "syntax_error", "detail": str(exc)}
    return {"path": rel, "category": classify(tree)}


HONEST_REPLACEMENT = (
    "\n\ndef __getattr__(name: str):\n"
    '    raise AttributeError(\n'
    '        f"module {__name__!r} has no attribute {name!r}"\n'
    "    )\n"
)


def transform_file(path: Path) -> tuple[bool, str]:
    """Splice out ALL poison machinery and splice in the honest __getattr__.

    Removes, at module level: DynamicMeta class, DynamicStub class, and the
    poison __getattr__ (which may itself define stub classes internally).
    Line-based splice with post-splice semantic gates (all must pass before
    write): parses, zero DynamicStub/DynamicMeta definitions AND zero
    surviving references, __getattr__ raises, classify() == 'honest'.
    """
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    if classify(tree) != "poison_pure":
        return False, "not poison_pure at transform time"
    fn = _module_getattr(tree)
    if fn is None:
        return False, "no module getattr"

    # Collect 1-based line spans to remove: stub classes + the getattr.
    spans: list[tuple[int, int]] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name in ("DynamicStub", "DynamicMeta"):
            spans.append((node.lineno, node.end_lineno))
    start_line = fn.lineno - 1
    if fn.decorator_list:
        start_line = min(d.lineno for d in fn.decorator_list) - 1
    spans.append((start_line + 1, fn.end_lineno))

    # Comment lines directly above each removed def/class belong to it.
    lines = src.splitlines(keepends=True)
    drop = set()
    for lo, hi in spans:
        drop.update(range(lo - 1, hi))  # to 0-based half-open
        k = lo - 2
        while k >= 0 and lines[k].strip().startswith("#"):
            drop.add(k)
            k -= 1

    kept = [line for i, line in enumerate(lines) if i not in drop]

    # Insert the honest __getattr__ before any trailing code, else at end.
    new_src = "".join(kept).rstrip("\n") + "\n" + HONEST_REPLACEMENT
    # (spans removed the getattr; trailing module code after it is preserved
    #  by `kept` — the replacement is appended at the end of the kept block,
    #  which for these generated files is exactly where the getattr was.
    #  If trailing code existed after the getattr it would now sit ABOVE the
    #  honest __getattr__, which is still valid and honest.)

    # ── Post-splice semantic gates (all must pass before write) ──
    try:
        new_tree = ast.parse(new_src)
    except SyntaxError as exc:
        return False, f"compile check failed: {exc}"
    if _has_stub_class(new_tree):
        return False, "DynamicStub still present after splice"
    for node in ast.walk(new_tree):
        if isinstance(node, ast.Name) and node.id in ("DynamicStub", "DynamicMeta"):
            return False, f"surviving reference to {node.id}"
    new_fn = _module_getattr(new_tree)
    if new_fn is None:
        return False, "__getattr__ lost in splice"
    if not any(isinstance(n, ast.Raise) for n in ast.walk(new_fn)):
        return False, "new __getattr__ does not raise"
    if classify(new_tree) != "honest":
        return False, f"post-splice classification is {classify(new_tree)!r}, expected 'honest'"

    path.write_text(new_src, encoding="utf-8")
    return True, "rewritten"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["inventory", "transform", "verify"])
    parser.add_argument("--apply", action="store_true", help="write changes (transform)")
    args = parser.parse_args()

    results = [analyze(p) for p in iter_candidate_files()]

    if args.command in ("inventory", "verify"):
        counts: dict[str, int] = {}
        for r in results:
            counts[r["category"]] = counts.get(r["category"], 0) + 1
        print("== category counts ==")
        for cat, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            print(f"{n:5d}  {cat}")
        for cat in ("poison_pure", "poison_lazy_fallback", "poison_mixed",
                    "class_stub", "lazy_import", "honest", "unreadable", "syntax_error"):
            items = [r["path"] for r in results if r["category"] == cat]
            if not items:
                continue
            print(f"\n-- {cat} ({len(items)}) --")
            for item in items:
                print(f"   {item}")
        return 0

    # transform
    targets = [r for r in results if r["category"] == "poison_pure"]
    print(f"{len(targets)} poison_pure targets")
    changed = failed = 0
    for r in targets:
        path = ROOT / r["path"]
        if not args.apply:
            changed += 1
            continue
        ok, note = transform_file(path)
        if ok:
            changed += 1
        else:
            failed += 1
            print(f"[FAIL] {r['path']}: {note}")
    verb = "would rewrite" if not args.apply else "rewritten"
    print(f"{verb}: {changed}; failures: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
