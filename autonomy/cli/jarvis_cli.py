#!/usr/bin/env python3
"""
cli/jarvis_cli.py — JARVIS Autonomous CLI
==========================================
Usage:
  jarvis think  "what should I focus on today?"
  jarvis plan   "build a Flutter login screen"
  jarvis run    "write a Python script to backup my files"
  jarvis exec   "open chrome"
  jarvis exec   "terminal: ls -la"
  jarvis memory "project deadline"
  jarvis status
  jarvis logs   [n]
  jarvis chat
"""
import sys, os, json, re, textwrap, urllib.request, urllib.error, urllib.parse

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SERVER = os.environ.get("JARVIS_SERVER", "http://localhost:8000")
AUTONOMY_PREFIX = os.environ.get("JARVIS_AUTONOMY_PREFIX", "/autonomy")

# ── ANSI ─────────────────────────────────────────────────────────
C = {"c":"\033[96m","y":"\033[93m","g":"\033[92m","r":"\033[91m",
     "d":"\033[2m","b":"\033[1m","o":"\033[33m","R":"\033[0m","bl":"\033[94m"}

def c(text, *s):
    return "".join(C.get(x,"") for x in s) + str(text) + C["R"]

def hdr(t): print(f"\n{c('+- '+t,'c','b')}")
def div():  print(c("-" * 64,"d"))
def ok(t):  print(c("  [OK] ","g") + t)
def err(t): print(c("  [FAIL] ","r") + t)

def api(endpoint, data=None, method=None):
    url     = SERVER + endpoint
    payload = json.dumps(data or {}).encode() if data is not None else None
    m       = method or ("POST" if payload else "GET")
    req     = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type":"application/json"},
        method=m,
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        err(f"HTTP {e.code}")
        return None
    except urllib.error.URLError:
        err(f"Cannot reach JARVIS at {SERVER}")
        print(c("  Start: jarvis server","d"))
        print(c("  Or:    jarvis up","d"))
        sys.exit(1)


# ── Commands ──────────────────────────────────────────────────────

def cmd_think(args):
    text = " ".join(args)
    if not text: print(c("Usage: jarvis think \"text\"","y")); return
    hdr(f"THINK: {text[:55]}")
    div()
    print(c("Routing through layers...","d"), end="\r", flush=True)
    r = api(f"{AUTONOMY_PREFIX}/think", {"text": text, "platform": "cli"})
    if not r: return
    print(" "*40, end="\r")

    route_c = {"brain":"c","assistant":"bl","executor":"o","controller":"y"}
    route   = str(r.get("route","")).split(".")[-1]
    print(f"  {c('Route:','d')} {c(route, route_c.get(route,'c'), 'b')}  "
          f"{c('Intent:','d')} {c(r.get('intent','?'),'c')}  "
          f"{c('Emotion:','d')} {r.get('emotion','?')}  "
          f"{c('Model:','d')} {c(r.get('model','?'),'d')}")
    print()
    _fmt(r.get("reply",""))

    plan = r.get("plan",[])
    if plan:
        print(c("\n  Plan:","y"))
        for i, s in enumerate(plan, 1):
            print(f"    {c(str(i)+'.','d')} {s}")

    out = r.get("exec_output","")
    if out and out.strip():
        print(c("\n  Execution output:","g"))
        for line in out.splitlines()[:20]:
            print(f"    {line}")

    print(c(f"\n  {r.get('latency_ms',0)}ms · {r.get('source','?')}","d"))


def cmd_plan(args):
    goal = " ".join(args)
    if not goal: print(c("Usage: jarvis plan \"goal\"","y")); return
    hdr(f"PLAN: {goal[:55]}")
    div()
    print(c("Planning...","d"), end="\r", flush=True)
    r = api(f"{AUTONOMY_PREFIX}/plan", {"goal": goal, "dry_run": True})
    if not r: return
    print(" "*20, end="\r")

    risk   = r.get("risk", 0)
    rc     = "g" if risk < 0.3 else "y" if risk < 0.7 else "r"
    print(f"  {c('Risk:','d')} {c(f'{risk:.2f}',rc)}\n")

    for s in r.get("steps",[]):
        icon = "[CODE]" if s.get("has_code") else ">"
        tool = f" [{s['tool']}]" if s.get("tool") else ""
        print(f"  {c(icon,'c')} {c(str(s['index'])+'.','d')} "
              f"{s['description']}{c(tool,'d')}")

    print(c(f"\n  {len(r.get('steps',[]))} steps planned","d"))
    ans = input(c("\n  Execute this plan? [y/N]: ","c"))
    if ans.strip().lower() == "y":
        cmd_run(args)


def cmd_run(args):
    goal = " ".join(args)
    if not goal: print(c("Usage: jarvis run \"goal\"","y")); return
    hdr(f"RUN: {goal[:55]}")
    div()
    print(c("Planning → Executing → Verifying...","d"), end="\r", flush=True)
    r = api(f"{AUTONOMY_PREFIX}/execute", {"goal": goal, "dry_run": False})
    if not r: return
    print(" "*40, end="\r")

    status = r.get("status","?")
    sc = {"success":"g","partial":"y","failed":"r","blocked":"r"}.get(status,"d")
    done, total = r.get("steps_done",0), r.get("steps_total",0)
    print(f"  {c('Status:','d')} {c(status.upper(),sc,'b')}  "
          f"{c(f'{done}/{total} steps','d')}\n")

    out = r.get("output","")
    if out:
        print(c("  Output:","c"))
        for line in out.splitlines()[:30]:
            print(f"    {line}")

    if r.get("error"):
        print(c(f"\n  Error: {r['error'][:200]}","r"))
    if r.get("audit_id"):
        print(c(f"\n  Audit ID: {r['audit_id']}","d"))
    print(c(f"  {r.get('latency_ms',0)}ms","d"))


def cmd_status(_args):
    hdr("SYSTEM STATUS")
    div()
    r = api("/layers/status", method="GET")
    if not r: return

    icons = {
        "L1_brain":      "[BRAIN]      (L1) - JarvisBrain 8-agent pipeline",
        "L2_assistant":  "[ASSISTANT]  (L2) - Codebase indexer + Codex",
        "L3_executor":   "[EXECUTOR]   (L3) - TaskPlanner + sandbox loop",
        "L4_controller": "[CONTROLLER] (L4) - Terminal + ADB + Safety",
        "orchestrator":  "[ORCHESTRATOR]      - 4-layer router",
    }
    for key, label in icons.items():
        active = r["layers"].get(key, False)
        print(f"  {c('(*)' if active else '( )', 'g' if active else 'r')} {label}")

    mem = r.get("memory",{})
    if mem.get("online"):
        stats = mem.get("stats",{})
        print(f"\n  {c('Memory:','c')} {stats.get('total',0)} entries")

    blocks = r.get("safety",{}).get("recent_blocks",[])
    if blocks:
        print(c(f"\n  [WARN] {len(blocks)} recent safety blocks","y"))

    # Also show existing /health
    h = api("/health", method="GET")
    if h:
        print(c("\n  Core modules:","d"))
        for mod, active in h.get("modules",{}).items():
            print(f"    {c('(*) ' if active else '( ) ','g' if active else 'd')} {mod}")


def cmd_memory(args):
    q = " ".join(args)
    if not q: print(c("Usage: jarvis memory \"query\"","y")); return
    hdr(f"MEMORY: {q[:50]}")
    div()
    r = api(f"{AUTONOMY_PREFIX}/memory/search?q={urllib.parse.quote(q)}&top_k=5", method="GET")
    if not r: return
    results = r.get("results",[])
    if not results:
        print(c("  No memories found","d")); return
    for i, m in enumerate(results,1):
        score = m.get("score", m.get("similarity",0))
        cat   = m.get("category","?")
        text  = m.get("text", m.get("content",""))
        print(f"  {c(str(i)+'.','d')} {c(f'[{cat}]','c')} {c(f'{score:.2f}','d')}")
        print(f"     {text[:120]}")
    print()


def cmd_exec(args):
    text = " ".join(args)
    if not text: print(c("Usage: jarvis exec \"action\"","y")); return
    hdr(f"SYSTEM: {text[:50]}")
    div()

    tl = text.lower()
    if tl.startswith("open "):
        r = api(f"{AUTONOMY_PREFIX}/system/action", {"action":"app_open",
                                    "params":{"app":text[5:]}})
    elif tl.startswith("http"):
        r = api(f"{AUTONOMY_PREFIX}/system/action", {"action":"browser",
                                    "params":{"url":text}})
    elif tl.startswith("ls ") or tl.startswith("dir"):
        r = api(f"{AUTONOMY_PREFIX}/system/action", {"action":"file_list",
                                    "params":{"path":text[3:].strip() or "."}})
    elif tl.startswith("read "):
        r = api(f"{AUTONOMY_PREFIX}/system/action", {"action":"file_read",
                                    "params":{"path":text[5:].strip()}})
    elif tl.startswith("terminal:") or tl.startswith("terminal "):
        cmd = re.sub(r"^terminal:?\s*","",text,flags=re.I)
        r = api(f"{AUTONOMY_PREFIX}/system/action", {"action":"terminal",
                                    "params":{"cmd":cmd}})
    else:
        r = api(f"{AUTONOMY_PREFIX}/think", {"text": text, "platform": "cli"})
        if r:
            _fmt(r.get("reply",""))
        return

    if not r: return
    if r.get("success"):
        ok(r.get("output","Done")[:500])
    else:
        err(r.get("error","Failed"))
    print(c(f"  {r.get('duration_ms',0)}ms","d"))


def cmd_logs(args):
    n = int(args[0]) if args and args[0].isdigit() else 10
    hdr(f"EXECUTION LOG (last {n})")
    div()
    r = api(f"/executions/recent?n={n}", method="GET")
    if not r: return
    import datetime
    for ex in r.get("executions",[]):
        status = ex.get("status","?")
        sc  = {"success":"g","partial":"y","failed":"r","blocked":"r"}.get(status,"d")
        ts  = ex.get("ts",0)
        dt  = datetime.datetime.fromtimestamp(ts).strftime("%H:%M") if ts else "?"
        print(f"  {c(dt,'d')} {c(status,sc,'b'):20} {ex.get('goal','')[:55]}")
    print()


def cmd_chat(_args):
    print(c("\n+----------------------------------------------+","c"))
    print(c("|  JARVIS AUTONOMOUS - Interactive Chat          |","c"))
    print(c("|  /plan  /run  /exec  /memory  /status  /logs  |","c"))
    print(c("|  Type 'exit' to quit                           |","c"))
    print(c("+----------------------------------------------+\n","c"))

    while True:
        try:
            text = input(c("You > ","c")).strip()
        except (KeyboardInterrupt, EOFError):
            print(c("\nGoodbye.","d")); break
        if not text: continue
        if text.lower() in ("exit","quit","bye"): break

        # Slash commands
        if   text.startswith("/plan "):    cmd_plan(text[6:].split())
        elif text.startswith("/run "):     cmd_run(text[5:].split())
        elif text.startswith("/exec "):    cmd_exec(text[6:].split())
        elif text.startswith("/memory "): cmd_memory(text[8:].split())
        elif text.startswith("/status"):  cmd_status([])
        elif text.startswith("/logs"):    cmd_logs(text[6:].split())
        else:
            print(c("JARVIS > ","c"), end="", flush=True)
            r = api("/think", {"text":text,"platform":"cli"})
            if r:
                _fmt(r.get("reply",""))
                route = str(r.get("route","")).split(".")[-1]
                print(c(f"  ({r.get('latency_ms',0)}ms · {route})","d"))
            print()


def _fmt(text: str):
    """Print with code block highlighting."""
    def sub(m):
        lang = m.group(1) or ""
        code = m.group(2)
        return (c("\n  ```"+lang,"d") + "\n"
                + "\n".join(c("  "+l,"g") for l in code.splitlines())
                + "\n" + c("  ```","d"))
    text = re.sub(r"```(\w*)\n?([\s\S]*?)```", sub, text)
    for line in text.splitlines():
        print("  " + line)


COMMANDS = {
    "think":  cmd_think, "plan":   cmd_plan,
    "run":    cmd_run,   "exec":   cmd_exec,
    "status": cmd_status,"memory": cmd_memory,
    "logs":   cmd_logs,  "chat":   cmd_chat,
}

HELP = f"""
{c('JARVIS AUTONOMOUS CLI','c','b')} — 4-layer intelligence

{c('Commands:','y')}
  think   "text"          Route through all 4 layers
  plan    "goal"          Show plan without executing
  run     "goal"          Execute via L3 loop
  exec    "action"        Direct L4 system control
  memory  "query"         Search semantic memory
  status                  Status of all 4 layers + core
  logs    [n]             Recent execution audit log
  chat                    Interactive mode

{c('Examples:','y')}
  jarvis think "what should I focus on today?"
  jarvis plan  "build a REST API"
  jarvis run   "create backup of my Python files"
  jarvis exec  "open chrome"
  jarvis exec  "terminal: git status"
  jarvis memory "deadline"
  jarvis chat

{c('Server:','d')} {SERVER}
"""

def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h","--help","help"):
        print(HELP); return
    cmd = args[0].lower()
    if cmd in COMMANDS:
        COMMANDS[cmd](args[1:])
    else:
        cmd_think(args)   # treat whole input as think

if __name__ == "__main__":
    main()
