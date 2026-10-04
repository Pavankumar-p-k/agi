"""Build inventory.json — every repo file tagged REAL / FAKE-SUCCESS / STUB / MISSING.

Labels are earned, not read off a docstring:
  STUB         DynamicStub marker/body (the 269 known auto-reconstructed files).
  FAKE-SUCCESS AST body-read + manual review: an action/endpoint whose entire body
               is pass/.../return <canned success>, with zero calls/awaits/writes.
               Test files are excluded (their doubles are legitimate).
  REAL         everything else; `tests` = pass|fail|none from the 4 executed runs.
  MISSING      module names imported by repo code that do not exist on disk.
  ASSET        non-Python tracked file (docs/config/data).

Universe = every .py file on disk (venv/.git/caches excluded), not just git-tracked,
so gitignored-but-live files like core/build/service.py are counted.

Run:  python scripts/build_inventory.py
"""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
from collections import defaultdict

STUB_MARKER = "Auto-reconstructed backend component"
AUDIT_TOOLS = {  # my own audit scripts contain the marker as a literal constant
    "scripts/audit_stub_scan.py", "scripts/gen_structure_report.py",
    "scripts/build_inventory.py", "scripts/_review_fake.py",
}
ACTION_VERBS = (
    "build", "run", "execute", "start", "stop", "setup", "install", "send",
    "save", "create", "update", "delete", "process", "handle", "init", "resume",
    "launch", "connect", "sync", "apply", "submit", "verify", "check", "perform",
    "do_", "open", "write", "load", "ensure", "register", "initiate", "complete",
    "finish", "commit", "persist", "record", "read", "chat", "admin",
)
SKIP_TOP = {"venv", "dist", "build", "node_modules", ".git", ".venv", ".tox",
            "rebuild_backlog"}
SKIP_ANY = {"__pycache__", ".hypothesis", ".pytest_cache", "jarvis.egg-info"}
SUCCESS_KEYS = {"status", "success", "ok"}

# ---- manually reviewed decisions (body reads, 2026-10-02) -------------------
# extra functions the heuristics missed but review confirmed as fake-success
MANUAL_FAKE = {
    "core/agent_loop.py": ["run_agent_loop -> f-string canned echo",
                           "stream_agent_loop -> yields 'Processing/Done' only"],
    "core/build/service.py": ["build -> {'status': 'success'} always",
                              "resume_pending -> [] always"],
    "core/main.py": ["list_sessions -> {'sessions': []} canned",
                     "get_setting -> {'key': key, 'value': None} canned",
                     "admin_endpoint -> {'admin': True} canned"],
    "utils/telemetry.py": ["compute_global_health -> returns MockHealth with "
                           "mocked values (comment: 'Mocking values that "
                           "MetaGovernor expects')"],
    "core/dev_mode.py": ["is_enabled -> always True (flag file "
                         "~/.jarvis_dev_mode is written by enable()/disable() "
                         "but never read)"],
}
# functions the heuristics flagged but review cleared as legitimate
MANUAL_REAL = {
    "core/result.py": ["is_ok/is_err are value semantics of the Ok/Err type"],
}
PYTEST_LOGS = ["audit_pytest_unit.txt", "audit_pytest_arch.txt",
               "audit_pytest_int.txt", "audit_pytest_acc.txt"]


def walk_py() -> list[str]:
    out = []
    for dp, dn, fn in os.walk("."):
        rel_dir = os.path.relpath(dp, ".").replace(os.sep, "/")
        top = rel_dir.split("/")[0]
        dn[:] = [d for d in dn if d not in SKIP_ANY and
                 not (rel_dir == "." and d in SKIP_TOP)]
        for f in fn:
            if f.endswith(".py"):
                p = (os.path.join(rel_dir, f) if rel_dir != "." else f)
                out.append(p.replace(os.sep, "/"))
    return sorted(out)


def is_success_constant(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return len(node.elts) == 0
    if isinstance(node, ast.JoinedStr):
        return True                       # f"Echo: {message}" etc.
    if isinstance(node, ast.Dict):
        for k, v in zip(node.keys, node.values):
            if k is None or not isinstance(k, ast.Constant):
                return False
            kk = k.value
            if isinstance(v, ast.Constant) or isinstance(v, ast.JoinedStr):
                if kk in SUCCESS_KEYS or v is True or isinstance(v, ast.JoinedStr):
                    continue
                continue
            if isinstance(v, (ast.List, ast.Dict)) and not v.elts if isinstance(v, (ast.List,)) else False:
                continue
            return False
        return True
    if isinstance(node, (ast.List, ast.Dict)):
        return False
    if isinstance(node, ast.Name):
        return node.id in {"None", "True", "False"}
    if isinstance(node, ast.UnaryOp):
        return True
    return False


def is_endpoint(dec: ast.AST) -> bool:
    name = ast.unparse(dec)
    return (name.startswith(("app.", "router.", "api.", "web.")) or
            ".get(" in name or ".post(" in name or ".put(" in name or
            ".delete(" in name or "route" in name)


def fake_functions(tree: ast.AST) -> list[str]:
    """Action/endpoint functions that do nothing yet report success."""
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        name = node.name
        if name.startswith("_"):
            continue
        decorators = node.decorator_list
        body = [s for s in node.body if not (isinstance(s, ast.Expr)
                and isinstance(s.value, ast.Constant)
                and isinstance(s.value.value, str))]
        if not body:
            continue
        single_return = len(body) == 1 and isinstance(body[0], ast.Return)
        endpoint = any(is_endpoint(d) for d in decorators)
        # --- endpoint returning a canned payload ---
        if endpoint and single_return and body[0].value is not None:
            val = body[0].value
            calls = [n for n in ast.walk(val) if isinstance(n, (ast.Call, ast.Await))]
            if not calls and isinstance(val, (ast.Dict, ast.List, ast.Constant,
                                              ast.Set, ast.Name)):
                found.append(f"{name}:@{node.lineno} canned endpoint -> "
                             f"{ast.unparse(val)[:70]}")
                continue
        # --- body must be only pass / return <success constant> ---
        ret_repr, ok = None, True
        has_ellipsis = False
        for s in body:
            if isinstance(s, ast.Pass):
                ret_repr = ret_repr or "pass"
                continue
            if (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant)
                    and s.value.value is ...):
                has_ellipsis = True
                continue
            if isinstance(s, ast.Return) and (s.value is None
                                              or is_success_constant(s.value)):
                ret_repr = "return " + (ast.unparse(s.value) if s.value else "None")
                continue
            ok = False
            break
        if not ok:
            continue
        if has_ellipsis and ret_repr is None:
            continue                        # Protocol/ABC stub — abstract, not fake
        if ret_repr is None:
            continue
        # --- no side effects ---
        for s in body:
            for sub in ast.walk(s):
                if isinstance(sub, (ast.Call, ast.Await, ast.Delete)):
                    ok = False
                if isinstance(sub, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                    targets = sub.targets if isinstance(sub, ast.Assign) else [sub.target]
                    if any(isinstance(t, (ast.Attribute, ast.Subscript)) for t in targets):
                        ok = False
                if isinstance(sub, (ast.With, ast.For, ast.While, ast.If, ast.Try)):
                    ok = False
        if not ok:
            continue
        claims = ("status" in ret_repr or ret_repr.startswith("return True")
                  or ret_repr in {"pass", "return None", "return []", "return {}",
                                  "return ''", 'return ""'})
        is_action = name.startswith(ACTION_VERBS)
        if claims and (is_action or endpoint or ret_repr.startswith("return {'status'")):
            found.append(f"{name}:@{node.lineno} {ret_repr[:70]}")
    return found


def main() -> int:
    py = walk_py()
    tracked = set(subprocess.run(["git", "ls-files"], capture_output=True, text=True,
                                 encoding="utf-8", errors="replace").stdout.split())
    assets = [f for f in tracked if not f.endswith(".py")]

    # --- test outcomes from the 4 executed runs ---
    test_fail: set[str] = set()
    for log in PYTEST_LOGS:
        if not os.path.exists(log):
            continue
        for line in open(log, encoding="utf-8", errors="ignore"):
            m = re.match(r"^(FAILED|ERROR) ([^\s:]+)", line)
            if m:
                test_fail.add(m.group(2).replace("\\", "/"))
    ran_test_files = set()
    for log in PYTEST_LOGS:
        if not os.path.exists(log):
            continue
        txt = open(log, encoding="utf-8", errors="ignore").read()
        ran_test_files.update(re.findall(r"(tests/[\w/]+\.py)", txt.replace("\\", "/")))

    # --- module index (on disk) ---
    mod2path = {}
    for f in py:
        if f.endswith("/__init__.py"):
            mod = f[: -len("/__init__.py")].replace("/", ".")
        else:
            mod = f[:-3].replace("/", ".")
        if mod and mod != "__init__":
            mod2path[mod] = f
    project_roots = {f.split("/")[0] for f in py} | {"assistant", "resource_monitor"}

    # --- test -> source links (from the structure report) ---
    test_links: dict[str, set[str]] = defaultdict(set)
    if os.path.exists("file_links.tsv"):
        for i, line in enumerate(open("file_links.tsv", encoding="utf-8")):
            if i == 0:
                continue
            src, dst, _ = line.rstrip("\n").split("\t")
            if src.startswith("tests/"):
                test_links[src].add(dst)
    src2tests: dict[str, set[str]] = defaultdict(set)
    for tf, mods in test_links.items():
        for m in mods:
            if m in mod2path:
                src2tests[mod2path[m]].add(tf)
            else:
                for k, v in mod2path.items():
                    if k.startswith(m + "."):
                        src2tests[v].add(tf)
    all_tests = [f for f in py if f.startswith("tests/") and f.endswith(".py")]

    entries = []
    for f in py:
        try:
            src = open(f, encoding="utf-8", errors="ignore").read()
        except OSError:
            entries.append({"file": f, "tag": "MISSING", "why": "unreadable"})
            continue
        loc = len([l for l in src.splitlines() if l.strip()])
        base = {"file": f, "loc": loc, "tracked": f in tracked}
        if f in AUDIT_TOOLS:
            entries.append({**base, "tag": "REAL", "note": "audit tooling "
                            "(contains marker literal)", "tests": "none"})
            continue
        if STUB_MARKER in src or ("class DynamicStub" in src
                                  and "def __getattr__" in src):
            entries.append({**base, "tag": "STUB",
                            "evidence": "DynamicStub marker/body"})
            continue
        # fake-success
        cands: list[str] = []
        parse_err = None
        try:
            cands = fake_functions(ast.parse(src))
        except SyntaxError as e:
            parse_err = e.msg
        if f in MANUAL_REAL:
            cands = []
        if f in MANUAL_FAKE:
            cands = list(dict.fromkeys(cands + MANUAL_FAKE[f]))
        if f.startswith("tests/"):
            cands = []                      # test doubles are legitimate
        # coupled-evidence rule: bare `is_* -> True` only counts with another fake
        if len(cands) == 1 and "return True" in cands[0] and \
                cands[0].startswith("is_"):
            cands = []
        # tests
        tests = set(src2tests.get(f, set()))
        if not tests and f.startswith("tests/"):
            tests = {f}
        if not tests:
            leaf = os.path.basename(f)[:-3]
            tests = {t for t in all_tests
                     if os.path.basename(t) in (f"test_{leaf}.py",
                                                f"test_{leaf}_test.py")}
        if f.startswith("tests/"):
            tstat = "fail" if f in test_fail else (
                "pass" if f in ran_test_files else "none")
        elif not tests:
            tstat = "none"
        elif any(t in test_fail for t in tests):
            tstat = "fail"
        else:
            tstat = "pass"
        tag = "FAKE-SUCCESS" if cands else "REAL"
        e = {**base, "tag": tag, "tests": tstat}
        if cands:
            e["evidence"] = cands[:10]
        if tests:
            e["test_files"] = sorted(tests)[:6]
        if parse_err:
            e["parse_error"] = parse_err
        entries.append(e)

    # --- MISSING: imported-but-absent project modules ---
    missing: dict[str, set[str]] = defaultdict(set)
    for f in py:
        if f.startswith("tests/"):
            continue
        try:
            tree = ast.parse(open(f, encoding="utf-8", errors="ignore").read())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            for n in names:
                root = n.split(".")[0]
                if root in project_roots and n not in mod2path and \
                        not any(k.startswith(n + ".") for k in mod2path):
                    missing[n].add(f)
    for m, imps in sorted(missing.items()):
        entries.append({"file": m + " (absent)", "tag": "MISSING",
                        "imported_by": sorted(imps)[:8]})
    for f in assets:
        entries.append({"file": f, "tag": "ASSET",
                        "kind": f.rsplit(".", 1)[-1] if "." in f else "no-ext"})

    summary = defaultdict(int)
    for e in entries:
        summary[e["tag"]] += 1
    real_tests = defaultdict(int)
    for e in entries:
        if e["tag"] == "REAL" and not e["file"].endswith("(absent)"):
            real_tests[e.get("tests", "none")] += 1
    fake_by_test = defaultdict(int)
    for e in entries:
        if e["tag"] == "FAKE-SUCCESS":
            fake_by_test[e.get("tests", "none")] += 1

    inv = {
        "generated": "scripts/build_inventory.py",
        "universe": f"{len(py)} .py files on disk (venv/.git/caches excluded) "
                    f"+ {len(assets)} tracked non-Python assets + absent modules",
        "test_runs_executed": {
            "tests/unit": "1574 failed, 2353 passed, 3 skipped, 213 errors",
            "tests/architecture": "20100 passed, 916 skipped",
            "tests/{integration,contract,cli,distribution}":
                "76 failed, 266 passed, 21 errors",
            "tests/{acceptance,e2e}": "32 failed, 97 passed, 18 errors",
        },
        "summary_counts": {k: summary.get(k, 0)
                           for k in ("REAL", "FAKE-SUCCESS", "STUB", "MISSING",
                                     "ASSET")},
        "real_by_test_status": dict(real_tests),
        "fake_success_by_test_status": dict(fake_by_test),
        "files": entries,
    }
    with open("inventory.json", "w", encoding="utf-8") as fh:
        json.dump(inv, fh, indent=1)

    print("=== inventory.json summary counts ===")
    for k, v in inv["summary_counts"].items():
        print(f"  {k:14s} {v}")
    print(f"  {'TOTAL':14s} {sum(inv['summary_counts'].values())}")
    print("REAL by test status:      ", dict(real_tests))
    print("FAKE-SUCCESS by test status:", dict(fake_by_test))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
