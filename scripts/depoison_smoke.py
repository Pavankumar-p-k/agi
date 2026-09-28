"""Import smoke for de-poisoning.

Imports a representative sample of poisoned modules (including the
importlib-corrupting one) and probes:
  1. import success
  2. attribute behavior on a missing name (DynamicStub returns a callable
     poison object; honest module raises AttributeError)
  3. submodule import behavior (poison breaks ``import x.y`` with
     ``TypeError: 'DynamicStub' object is not iterable``; honest module
     raises ModuleNotFoundError)

Usage:
    python scripts/depoison_smoke.py            # summary verdict
    python scripts/depoison_smoke.py --verbose  # per-module detail
"""
from __future__ import annotations

import argparse
import importlib
import sys

sys.path.insert(0, ".")

SAMPLES = [
    # The importlib-corruption reproducer
    "core.privacy_classifier",
    # Package inits that poison-pure
    "core.activity",
    "core.belief",
    "core.benchmark",
    "core.plugins",
    "core.workflow",
    "core.collaboration",
    "core.negotiation",
    "core.opportunity",
    "core.generalization",
    "core.long_term_memory",
    "core.self_modification",
    "core.improvement",
    "core.scheduler",
    "core.strategy",
    "core.observation",
    "core.evidence",
    "core.inbox",
    "core.spawning",
    "core.settings",
    # Submodule poison (non-init files)
    "core.activity.recorder",
    "core.belief.store",
    "core.audit_log",
    "core.api_key_vault",
    "core.chroma_client",
    "core.email_monitor",
    # Healthy boundary must stay untouched
    "core.providers",
    "core.providers.orchestration",
    "core.capability",
    "core.tools",
    "core.permission",
]


def probe(modname: str) -> dict:
    out = {"module": modname}
    try:
        mod = importlib.import_module(modname)
        out["import"] = "ok"
    except Exception as exc:
        out["import"] = f"FAIL: {type(exc).__name__}: {exc}"
        return out

    # Missing-attribute behavior
    try:
        _ = getattr(mod, "__definitely_not_a_real_attr_xyz__")
        out["missing_attr"] = "POISON (returned value instead of raising)"
    except AttributeError:
        out["missing_attr"] = "honest"
    except Exception as exc:
        out["missing_attr"] = f"odd ({type(exc).__name__})"

    # Submodule import machinery behavior
    sub = f"{modname}.definitely_not_a_submodule_xyz"
    try:
        importlib.import_module(sub)
        out["submodule_import"] = "POISON (no error)"
    except ModuleNotFoundError:
        out["submodule_import"] = "honest"
    except TypeError as exc:
        out["submodule_import"] = f"CORRUPT ({type(exc).__name__})"
    except Exception as exc:
        out["submodule_import"] = f"odd ({type(exc).__name__}: {exc})"
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    results = [probe(m) for m in SAMPLES]
    ok = sum(1 for r in results if r.get("import") == "ok")
    honest_attr = sum(1 for r in results if r.get("missing_attr") == "honest")
    honest_sub = sum(1 for r in results if r.get("submodule_import") == "honest")

    for r in results:
        flag = ""
        if "POISON" in str(r.get("missing_attr", "")) or "CORRUPT" in str(r.get("submodule_import", "")):
            flag = "  <<< POISON"
        elif r.get("import") != "ok":
            flag = "  <<< IMPORT FAIL"
        if args.verbose or flag or r.get("import") != "ok":
            print(f"{r['module']:40s} import={r.get('import')!s:30s} "
                  f"attr={r.get('missing_attr', '-')!s:45s} sub={r.get('submodule_import', '-')}{flag}")

    print(f"\nimports ok: {ok}/{len(results)}; honest attr: {honest_attr}; honest subimport: {honest_sub}")
    # Non-poison verdict: every import ok AND every probe honest.
    poison = sum(
        1 for r in results
        if "POISON" in str(r.get("missing_attr", "")) or "CORRUPT" in str(r.get("submodule_import", ""))
    )
    print("VERDICT:", "POISON DETECTED" if poison else "HONEST")
    return 0


if __name__ == "__main__":
    main()
