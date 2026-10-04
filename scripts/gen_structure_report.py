"""Generate a whole-project structure + link report.

For every project file it records: name, size, status (REAL/STUB/HOLLOW),
one-line purpose, outbound project-internal imports (links), inbound referencers,
and a heuristic reason for each link family. Output:

  CODE_STRUCTURE.md   human-readable report
  file_links.tsv      every import edge (src -> dst, line, reason)

Run:  python scripts/gen_structure_report.py
"""
from __future__ import annotations

import ast
import os
import sys
from collections import defaultdict

STUB_MARKER = "Auto-reconstructed backend component"
SKIP_DIRS = {".git", "__pycache__", "node_modules", "venv", ".venv", "dist",
             "build", ".hypothesis", ".pytest_cache", "jarvis.egg-info",
             "jarvis-export", "DATA_DIR", "logs", "media", "data"}

# Top-level directory purpose (why it exists in this project)
DIR_PURPOSE = {
    "core": "Backend: pipeline, desktop/browser control, providers, tools, memory, API routes",
    "tests": "pytest suites (unit / architecture gates / integration / acceptance / e2e)",
    "tools": "Standalone tool integrations (search, crawl, image gen, website gen, registry)",
    "skills": "User-installable skill packages (each a folder with main.py)",
    "memory": "Long-term memory: vector store, SQLite stores, adapters",
    "learning": "Learning subsystem (habit tracker, student_agi experiments)",
    "integrations": "External services: Gmail, Google Calendar, WhatsApp, weather/news",
    "plugins": "Runtime plugins loaded by the plugin system",
    "jarvis_mcp": "MCP servers (memory, rag, image gen) for tool hosts",
    "jarvis_tui": "Textual TUI application (screens, widgets, services)",
    "jarvis_plugin_sdk": "Public SDK for writing JARVIS plugins",
    "provider_sdk": "SDK + adapters for plugging new LLM providers",
    "channels": "Messaging channel plugins (Telegram, Discord, ...)",
    "governance": "Top-level governance rules/reporting (distinct from core/governance)",
    "monitors": "Background monitors (voice, services, system)",
    "vision": "Face recognition / image utilities",
    "media": "Media playback and file helpers",
    "network": "Network utilities",
    "notifications": "Notification dispatch",
    "reminders": "Reminder scheduling",
    "services": "Shared service helpers (memory service)",
    "daemon": "OS service / daemon wrapper",
    "data": "Scratch data + one-off probe/benchmark scripts",
    "demo": "Demo entry scripts",
    "docs": "Documentation",
    "scripts": "Repo tooling: audits, stub counter/cleanup, smoke, verification",
    "src": "Small auxiliary search package",
    "web": "Web UI assets (built frontend)",
    "brain": "Experimental reasoning transforms",
    "models": "Shared pydantic/dataclass models",
    "providers": "Legacy provider package (see core/providers)",
    "personal": "Personal-area config/data",
    "reports": "Generated reports",
    "notes": "Scratch notes",
    "config": "Configuration loaders",
    "packages": "Vendored/helper packages",
    "governance_pkg": "",
}

# Link family reasons (why one module imports another)
def edge_reason(importer: str, target: str) -> str:
    leaf = target.rsplit(".", 1)[-1]
    pkg = target.split(".")[0]
    if importer.startswith("tests/"):
        return "verification: test exercises the target"
    if leaf in ("config", "constants", "settings", "config_init") or "/configuration/" in target.replace(".", "/"):
        return "reads configuration/constants"
    if leaf in ("models", "schemas", "types", "messages") or leaf.endswith("_models"):
        return "data contract: shared types"
    if pkg in ("providers", "model_providers") or "provider" in target:
        return "LLM provider access (routing/models/keys)"
    if "/routes/" in target or target.startswith("core.routes"):
        return "HTTP API wiring (FastAPI router)"
    if "/desktop/" in target or "desktop" in target:
        return "OS/desktop control capability"
    if "browser" in target:
        return "browser automation capability"
    if "/memory" in target or target.startswith("memory") or "/belief/" in target:
        return "memory / knowledge recall"
    if "/pipeline/" in target or target.startswith("core.pipeline"):
        return "canonical request pipeline"
    if "/tools/" in target or target.startswith("tools") or "tool" in leaf:
        return "tool invocation layer"
    if "/governance/" in target or "security" in leaf or "permission" in target or "authz" in target:
        return "safety / permissions / audit"
    if leaf.startswith("test_"):
        return "verification"
    return "runtime dependency"


def project_dirs() -> set[str]:
    return {d for d in os.listdir(".") if os.path.isdir(d) and d not in SKIP_DIRS} | \
           {f[:-3] for f in os.listdir(".") if f.endswith(".py")}


ROOT_MODULES: set[str] = set()


def build_module_index(root: str) -> tuple[dict[str, str], dict[str, str]]:
    mod2path, path2mod = {}, {}
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        for f in fn:
            if not f.endswith(".py"):
                continue
            p = os.path.join(dp, f).replace("\\", "/")
            rel = p[2:] if p.startswith("./") else p
            if f == "__init__.py":
                pkg = rel[: -len("/__init__.py")].replace("/", ".") if "/" in rel else ""
            else:
                pkg = rel[:-3].replace("/", ".")
            if pkg:
                mod2path[pkg] = rel
                path2mod[rel] = pkg
    return mod2path, path2mod


def resolve(level: int, mod: str, owner_pkg: str) -> list[str]:
    """Return candidate absolute dotted targets for an import."""
    out = []
    if level == 0:
        if mod:
            out.append(mod)
        return out
    parts = owner_pkg.split(".") if owner_pkg else []
    # owner_pkg is the *module* dotted path; package = drop last element for files
    up = level - 1
    base = parts[: len(parts) - up] if up else parts
    if mod:
        out.append(".".join([*base, mod]))
    else:
        out.append(".".join(base))
    return out


def collect_links(rel: str, owner_pkg: str, tree: ast.AST, mod2path: dict[str, str]):
    links: set[str] = set()
    broken: set[str] = set()
    proj_roots = ROOT_MODULES
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                _register(a.name, 0, "", links, broken, mod2path, proj_roots, rel, node.lineno)
        elif isinstance(node, ast.ImportFrom):
            for cand in resolve(node.level or 0, node.module or "", owner_pkg):
                _register(cand, node.level or 0, node.module or "", links, broken,
                          mod2path, proj_roots, rel, node.lineno)
                # also: from pkg import submodule
                for a in node.names:
                    sub = f"{cand}.{a.name}"
                    if sub in mod2path:
                        links.add(sub)
    return links, broken


def _register(name, level, mod, links, broken, mod2path, proj_roots, rel, lineno):
    if not name:
        return
    root = name.split(".")[0]
    # exact match or a package prefix of an existing module
    if name in mod2path:
        links.add(name)
        return
    if any(m.startswith(name + ".") for m in mod2path):
        links.add(name)
        return
    if root in proj_roots or root in mod2path:
        broken.add(name)


def status_of(rel: str) -> str:
    try:
        src = open(rel, encoding="utf-8", errors="ignore").read()
    except OSError:
        return "ERR"
    if STUB_MARKER in src:
        return "STUB"
    code = [l for l in src.splitlines() if l.strip() and not l.strip().startswith("#")]
    if len(code) <= 8:
        return "TINY"
    return "REAL"


def purpose_of(rel: str) -> str:
    try:
        with open(rel, encoding="utf-8", errors="ignore") as fh:
            for _ in range(15):
                line = fh.readline()
                if not line:
                    break
                s = line.strip()
                if s.startswith('"""') or s.startswith("'''"):
                    s = s[3:]
                    if s.endswith('"""') or s.endswith("'''"):
                        s = s[:-3]
                    if s:
                        return s.replace("\n", " ")[:110]
                    # multi-line docstring: grab next non-empty
                    for _ in range(10):
                        line = fh.readline()
                        if not line:
                            break
                        t = line.strip().rstrip('"""').strip()
                        if t:
                            return t[:110]
                    return ""
                if s.startswith("#") and not s.startswith("#!") and len(s) > 5:
                    return s.lstrip("# ").replace("\n", " ")[:110]
                if s and not s.startswith(("from __future__", "import", "from ")):
                    return ""
    except OSError:
        pass
    return ""


def main() -> int:
    root = "."
    mod2path, path2mod = build_module_index(root)
    ROOT_MODULES.update({m.split(".")[0] for m in mod2path})
    # known project-owned roots that no longer resolve (missing packages)
    ROOT_MODULES.update({"assistant", "resource_monitor", "jarvis", "cli_commands",
                         "jarvis_provider", "desktop_bridge", "jarvis_tui", "jarvis_cli"})

    out_edges: dict[str, list[tuple[str, int, str]]] = defaultdict(list)
    in_edges: dict[str, list[str]] = defaultdict(list)
    broken: dict[str, set[str]] = defaultdict(set)
    parse_fail: list[str] = []

    files = sorted(mod2path.values())
    for rel in files:
        pkg = path2mod[rel]
        # relative imports resolve against the *package*, i.e. the dirname for a
        # module file and the module path itself for an __init__.py
        owner = pkg if rel.endswith("__init__.py") else pkg.rsplit(".", 1)[0]
        try:
            tree = ast.parse(open(rel, encoding="utf-8", errors="ignore").read())
        except SyntaxError as e:
            parse_fail.append(f"{rel}: {e.msg}")
            continue
        links, brk = collect_links(rel, owner, tree, mod2path)
        for b in brk:
            if b not in mod2path:
                broken[rel].add(b)
        for t in sorted(links):
            reason = edge_reason(rel, t)
            out_edges[rel].append((t, 0, reason))
            in_edges[t].append(rel)

    # ---------- file_links.tsv ----------
    with open("file_links.tsv", "w", encoding="utf-8") as fh:
        fh.write("src\tdst\treason\n")
        for src in sorted(out_edges):
            for dst, _ln, reason in out_edges[src]:
                fh.write(f"{src}\t{dst}\t{reason}\n")

    # ---------- CODE_STRUCTURE.md ----------
    L: list[str] = []
    L.append("# JARVIS — Full Code Structure & Link Report\n")
    L.append(f"Generated by `scripts/gen_structure_report.py` · {len(files)} Python files · "
             f"{sum(len(v) for v in out_edges.values())} internal import edges\n")
    L.append("Legend: **REAL** = implemented · **STUB** = `Auto-reconstructed backend component` "
             "DynamicStub · **TINY** = <=8 code lines (shim/empty)\n")

    # top-level overview
    top_stats: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])  # files, stub, tiny, edges
    for rel in files:
        top = rel.split("/")[0] if "/" in rel else "(root)"
        st = status_of(rel)
        top_stats[top][0] += 1
        if st == "STUB":
            top_stats[top][1] += 1
        if st == "TINY":
            top_stats[top][2] += 1
        top_stats[top][3] += len(out_edges.get(rel, []))
    L.append("## 1. Top-level layout\n")
    L.append("| dir | purpose | files | stubs | tiny | out-links |")
    L.append("|---|---|---:|---:|---:|---:|")
    for top in sorted(top_stats, key=lambda t: -top_stats[t][0]):
        f, s, t, e = top_stats[top]
        purpose = DIR_PURPOSE.get(top, "project files")
        L.append(f"| `{top}/` | {purpose} | {f} | {s} | {t} | {e} |")
    L.append("")

    # hubs
    hubs = sorted(((len(v), k) for k, v in in_edges.items()), reverse=True)[:30]
    L.append("## 2. Most-linked modules (hubs everyone depends on)\n")
    L.append("| module | referenced by | status | role |")
    L.append("|---|---:|---|---|")
    for n, mod in hubs:
        rel = mod2path.get(mod, "?")
        L.append(f"| `{mod}` | {n} | {status_of(rel) if rel != '?' else '-'} | {purpose_of(rel) if rel != '?' else ''} |")
    L.append("")

    # broken links
    all_broken: dict[str, set[str]] = defaultdict(set)
    for src, sset in broken.items():
        for b in sset:
            all_broken[b].add(src)
    L.append("## 3. BROKEN links (import target does not exist in the project)\n")
    if all_broken:
        L.append("| missing module | imported by (count) | example importers |")
        L.append("|---|---:|---|")
        for b in sorted(all_broken, key=lambda x: -len(all_broken[x])):
            imps = sorted(all_broken[b])
            shown = ", ".join(f"`{i}`" for i in imps[:4])
            L.append(f"| `{b}` | {len(imps)} | {shown} |")
    else:
        L.append("_none_")
    L.append("")

    # orphans
    entrypoints = {rel for rel in files if rel.count("/") == 0}
    orphans = [rel for rel in files
               if not in_edges.get(path2mod[rel]) and rel not in entrypoints
               and not rel.startswith("tests/") and status_of(rel) == "REAL"]
    L.append("## 4. Orphan REAL files (nothing in the project imports them)\n")
    L.append("These are dead code or only reachable dynamically (CLI flags, importlib, scripts):\n")
    for rel in sorted(orphans):
        L.append(f"- `{rel}` — {purpose_of(rel) or '(no docstring)'}")
    L.append("")

    # ---------- per-package detail ----------
    L.append("## 5. Per-package file detail (links + why)\n")
    L.append("Every entry: file · status · LOC · purpose · `→` outbound project links · "
             "`←` inbound referencer count.\n")

    by_pkg: dict[str, list[str]] = defaultdict(list)
    for rel in files:
        if rel.startswith("tests/"):
            continue
        parts = rel.split("/")
        pkg = "/".join(parts[:-1]) if len(parts) > 1 else "(root)"
        by_pkg[pkg].append(rel)

    for pkg in sorted(by_pkg):
        L.append(f"### `{pkg}/`")
        if pkg in DIR_PURPOSE or pkg.split("/")[0] in DIR_PURPOSE:
            why = DIR_PURPOSE.get(pkg, "")
            if why:
                L.append(f"*Why it exists:* {why}")
        for rel in sorted(by_pkg[pkg]):
            mod = path2mod[rel]
            st = status_of(rel)
            try:
                loc = len([l for l in open(rel, encoding="utf-8", errors="ignore").read().splitlines()
                           if l.strip()])
            except OSError:
                loc = 0
            purpose = purpose_of(rel)
            outs = out_edges.get(rel, [])
            out_str = ", ".join(f"`{d}`" for d, _, _ in outs[:10]) if outs else "—"
            if len(outs) > 10:
                out_str += f" (+{len(outs)-10} more)"
            inn = len(in_edges.get(mod, []))
            line = f"- **{os.path.basename(rel)}** [{st}, {loc} LOC] — {purpose or '(no purpose line)'}  \n" \
                   f"  → {out_str}  \n" \
                   f"  ← {inn} referencer(s)"
            if rel in broken and broken[rel]:
                line += f" · ⚠ missing: {', '.join(sorted(broken[rel])[:3])}"
            L.append(line)
        L.append("")

    # tests summary
    t_files = [rel for rel in files if rel.startswith("tests/")]
    L.append("## 6. Tests (`tests/`) — grouped\n")
    t_groups: dict[str, list[str]] = defaultdict(list)
    for rel in t_files:
        t_groups["/".join(rel.split("/")[:2])].append(rel)
    for g in sorted(t_groups):
        L.append(f"- `{g}/` — {len(t_groups[g])} files")
    L.append(f"\nFull edge list for every file: `file_links.tsv` ({sum(len(v) for v in out_edges.values())} rows).")
    if parse_fail:
        L.append("\n## Parse failures\n")
        L += [f"- {p}" for p in parse_fail]

    with open("CODE_STRUCTURE.md", "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")

    print(f"files: {len(files)}  edges: {sum(len(v) for v in out_edges.values())}  "
          f"broken-modules: {len(all_broken)}  orphans: {len(orphans)}  parse-fails: {len(parse_fail)}")
    print("wrote CODE_STRUCTURE.md and file_links.tsv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
