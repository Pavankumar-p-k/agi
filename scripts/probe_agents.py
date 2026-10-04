"""Import-health probe for every agent module (STEP 3)."""
import importlib, json, os, sys, traceback
sys.path.insert(0, os.getcwd())

MODULES = []
for f in sorted(os.listdir("core/agents")):
    if f.endswith(".py") and f != "__init__.py":
        MODULES.append("core.agents." + f[:-3])
for extra in ["core.agents.registry", "core.agents.base", "core.agents.capabilities"]:
    if extra not in MODULES:
        MODULES.append(extra)

out = {}
for m in MODULES:
    try:
        importlib.import_module(m)
        out[m] = "OK"
    except BaseException as e:
        out[m] = f"{type(e).__name__}: {e}"

ok = [m for m, r in out.items() if r == "OK"]
bad = {m: r for m, r in out.items() if r != "OK"}
print(f"IMPORT OK: {len(ok)} / {len(out)}")
for m, r in bad.items():
    print(f"  FAIL {m}\n        {r[:200]}")
json.dump(out, open("agent_import_health.json", "w"), indent=1)
