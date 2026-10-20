"""Built-in capability implementations — the things MJ can actually do.

Each capability has: a validated manifest, a run function, an independent
verify function, and (where sensible) an undo plan. Verifiers do their own
IO — they never trust the run function's claims (plan failure mode 3).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from mj.core import registry
from mj.core.registry import Manifest
from mj.core.store import Store
from mj.world import model
from mj.world import probes as world_probes


# -- capability implementations ---------------------------------------------


def _category_for(suffix: str) -> str:
    """Extension → pack category. Deterministic, no model in the loop."""
    images = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"}
    docs = {".pdf", ".doc", ".docx", ".txt", ".md", ".rtf", ".odt"}
    code = {".py", ".js", ".ts", ".tsx", ".rs", ".go", ".java", ".c", ".cpp", ".h", ".sh"}
    data = {".json", ".csv", ".xml", ".yaml", ".yml", ".toml", ".ini"}
    archives = {".zip", ".rar", ".7z", ".tar", ".gz"}
    if suffix in images:
        return "images"
    if suffix in docs:
        return "documents"
    if suffix in code:
        return "code"
    if suffix in data:
        return "data"
    if suffix in archives:
        return "archives"
    if suffix:
        return "other"
    return "other"


def run_facts(store: Store, inputs: dict[str, Any]) -> dict[str, Any]:
    scopes = sorted(inputs.get("probes") or list(world_probes.PROBES))
    facts = world_probes.run_probes(store, scopes)
    return {
        "facts": [
            {
                "scope": f.scope,
                "key": f.key,
                "value": f.value,
                "source": f.source,
                "observed_at": f.observed_at,
                "label": f.label,
            }
            for f in facts
        ]
    }


def verify_facts(store: Store, inputs: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    """Independent check: the requested scopes now exist in the fact store."""
    scopes = sorted(inputs.get("probes") or list(world_probes.PROBES))
    present = {f.scope for f in model.list_all(store)}
    missing = [s for s in scopes if s not in present]
    return {
        "verified": not missing,
        "detail": {"requested": scopes, "present": sorted(present), "missing": missing},
    }


def _listing(path: Path) -> list[dict[str, Any]]:
    out = []
    for entry in sorted(path.iterdir(), key=lambda p: p.name.lower()):
        if entry.is_file():
            stat = entry.stat()
            out.append(
                {
                    "name": entry.name,
                    "size": stat.st_size,
                    "ext": entry.suffix.lower(),
                    "is_dir": False,
                }
            )
        else:
            out.append(
                {"name": entry.name, "size": None, "ext": "", "is_dir": True}
            )
    return out


def run_list(store: Store, inputs: dict[str, Any]) -> dict[str, Any]:
    path = Path(inputs["path"])
    if not path.exists():
        raise OSError(f"no such directory: {path}")
    if not path.is_dir():
        raise OSError(f"not a directory: {path}")
    listing = _listing(path)
    return {
        "path": str(path),
        "count": len(listing),
        "files": [e for e in listing if not e["is_dir"]],
        "dirs": [e["name"] for e in listing if e["is_dir"]],
    }


def verify_list(store: Store, inputs: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    path = Path(inputs["path"])
    if not (path.exists() and path.is_dir()):
        return {"verified": False, "detail": {"reason": "directory missing at verify time"}}
    now_count = sum(1 for e in path.iterdir() if e.is_file())
    return {
        "verified": now_count == output["count"],
        "detail": {"files_now": now_count, "files_observed": output["count"]},
    }


def _plan_moves(files: list[str], base: Path) -> list[dict[str, str]]:
    moves = []
    for name in files:
        src = base / name
        target_dir = _category_for(src.suffix.lower())
        moves.append({"src": name, "dst": f"{target_dir}/"})
    return moves


def run_organize_plan(store: Store, inputs: dict[str, Any]) -> dict[str, Any]:
    """Dry run: propose the moves, change nothing."""
    path = Path(inputs["path"])
    if not (path.exists() and path.is_dir()):
        raise OSError(f"not a directory: {path}")
    files = [e.name for e in sorted(path.iterdir()) if e.is_file()]
    before_count = len(files)
    proposals = _plan_moves(files, path)
    return {
        "path": str(path),
        "before_count": before_count,
        "proposals": proposals,
        "moved": 0,
    }


def verify_organize_plan(store: Store, inputs: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    path = Path(inputs["path"])
    now_count = sum(1 for e in path.iterdir() if e.is_file())
    unchanged = now_count == output["before_count"]
    return {
        "verified": unchanged,
        "detail": {
            "files_before": output["before_count"],
            "files_after": now_count,
            "note": "dry run guarantees nothing moved" if unchanged else "UNEXPECTED CHANGE during dry run",
        },
    }


def _escapes_base(base: Path, relative: str) -> bool:
    """True if a worker-reported relative path resolves outside the base dir.

    Defense against a compromised worker reporting (or performing) a move to a
    path outside the directory the user approved: path traversal / confused
    deputy on the filesystem (adversarial suite class 6).
    """
    resolved = (base / relative).resolve()
    try:
        resolved.relative_to(base.resolve())
    except ValueError:
        return True
    return False


def _unique_dst(dst: Path, base: Path) -> Path:
    """Collisions get `name (2).ext`, never a silent overwrite."""
    candidate = dst
    n = 2
    while candidate.exists():
        candidate = dst.with_name(f"{dst.stem} ({n}){dst.suffix}")
        n += 1
    return candidate


def run_organize(store: Store, inputs: dict[str, Any]) -> dict[str, Any]:
    """Real moves, fully recorded so undo can reverse each one."""
    path = Path(inputs["path"])
    if not (path.exists() and path.is_dir()):
        raise OSError(f"not a directory: {path}")
    files = [e.name for e in sorted(path.iterdir()) if e.is_file()]
    before_count = len(files)
    done: list[dict[str, Any]] = []
    for name in files:
        src = path / name
        target_dir = path / _category_for(src.suffix.lower())
        target_dir.mkdir(exist_ok=True)
        dst = _unique_dst(target_dir / name, path)
        src_size = src.stat().st_size
        os.replace(src, dst)
        done.append({"src": name, "dst": str(dst.relative_to(path)), "src_size": src_size})
    return {
        "path": str(path),
        "before_count": before_count,
        "after_count": sum(1 for e in path.iterdir() if e.is_file()),
        "moves": done,
        "moved": len(done),
    }


def verify_organize(store: Store, inputs: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    """Every recorded move is checked by real stat calls, not by memory."""
    path = Path(inputs["path"])
    problems: list[str] = []
    for mv in output["moves"]:
        if _escapes_base(path, mv["dst"]) or _escapes_base(path, mv["src"]):
            problems.append(f"move escapes the base directory: {mv['src']} -> {mv['dst']}")
            continue
        dst = path / mv["dst"]
        if not dst.is_file():
            problems.append(f"missing destination {mv['dst']}")
        elif dst.stat().st_size != mv["src_size"]:
            problems.append(f"size mismatch at {mv['dst']}")
        src = path / mv["src"]
        if src.is_file():
            problems.append(f"source still present: {mv['src']}")
    return {
        "verified": not problems,
        "detail": {"moves_checked": len(output["moves"]), "problems": problems},
    }


def undo_organize(store: Store, inputs: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    """Restore every recorded move back to its original location,
    and remove category folders the organize step created."""
    path = Path(inputs["path"])
    undone = []
    refused: list[str] = []
    touched_dirs: set[str] = set()
    for mv in output["moves"]:
        if _escapes_base(path, mv["dst"]) or _escapes_base(path, mv["src"]):
            # never pull a file in from (or push one out to) beyond the base
            refused.append(f"{mv['src']} -> {mv['dst']}")
            continue
        dst = path / mv["dst"]
        src = path / mv["src"]
        touched_dirs.add(dst.parent.name)
        if dst.is_file():
            target = _unique_dst(src, path)
            os.replace(dst, target)
            undone.append(mv["src"])
    for name in touched_dirs:
        d = path / name
        try:
            d.rmdir()  # only succeeds if empty (rollback left nothing behind)
        except OSError:
            pass
    return {"undone": undone, "refused": refused}


@dataclass
class Impl:
    manifest: Manifest
    run: Callable[[Store, dict[str, Any]], dict[str, Any]]
    verify: Callable[[Store, dict[str, Any], dict[str, Any]], dict[str, Any]]


BUILTINS: dict[str, Impl] = {}


def _builtin(m: Manifest, run_fn, verify_fn) -> None:
    BUILTINS[m.id] = Impl(m, run_fn, verify_fn)
    registry.validate_manifest(m)


def ensure_registered(store: Store, actor: str = "bootstrap") -> None:
    """Idempotently register the builtin manifests as healthy.

    'healthy' is honest here: their manifest semantics and verifiers were
    tested by the repo's test suite before this registration (plan invariant:
    no capability trusted until it passed its tests).
    """
    for capability_id, impl in sorted(BUILTINS.items()):
        registry.register(store, impl.manifest, status="healthy", actor=actor)


_builtin(
    Manifest(
        id="os.facts",
        type="os",
        version="1.0.0",
        source="builtin",
        # R1 (was R0): the probes spawn short-lived read-only processes, so
        # the effect floor for `process` applies — an honest declaration.
        risk_class="R1",
        description="Refresh machine facts (disk, processes, apps, tools). Read-only toward user data; runs short-lived probe commands.",
        has_verifier=True,
        provenance={"implementations": ["mj.world.probes"]},
        effects=["filesystem.read", "process"],
    ),
    run_facts,
    verify_facts,
)
_builtin(
    Manifest(
        id="files.list",
        type="os",
        version="1.0.0",
        source="builtin",
        risk_class="R0",
        description="List a directory's files and subfolders. Read-only.",
        has_verifier=True,
        provenance={"implementations": ["mj.executor.capabilities:run_list"]},
        effects=["filesystem.read"],
    ),
    run_list,
    verify_list,
)
_builtin(
    Manifest(
        id="files.organize.plan",
        type="os",
        version="1.0.0",
        source="builtin",
        risk_class="R1",
        description="Dry run of file organization: proposes moves, changes nothing.",
        has_verifier=True,
        provenance={"implementations": ["mj.executor.capabilities:run_organize_plan"]},
        effects=["filesystem.read"],
    ),
    run_organize_plan,
    verify_organize_plan,
)
_builtin(
    Manifest(
        id="files.organize",
        type="os",
        version="1.0.0",
        source="builtin",
        risk_class="R2",
        description="Move files into category subfolders; records moves for undo; corrupts nothing on collision.",
        has_verifier=True,
        has_undo=True,
        provenance={"implementations": ["mj.executor.capabilities:run_organize"]},
        effects=["filesystem.read", "filesystem.write"],
    ),
    run_organize,
    verify_organize,
)
