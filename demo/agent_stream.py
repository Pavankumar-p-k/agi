# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
agent_stream.py — CLI demo that consumes /api/agent/stream SSE events.

Usage:
    python -m demo.agent_stream "write a python script that prints hello world"
    python -m demo.agent_stream "what is the capital of france?" --no-color
    python -m demo.agent_stream "search for AI news" --server http://localhost:8000
"""

import json
import os
import sys
import time
import urllib.request


def _c(code: str) -> str:
    """Return ANSI color escape if stdout is a TTY."""
    if not sys.stdout.isatty():
        return ""
    return code


CYAN = _c("\x1b[36m")
GREEN = _c("\x1b[32m")
YELLOW = _c("\x1b[33m")
RED = _c("\x1b[31m")
MAGENTA = _c("\x1b[35m")
BOLD = _c("\x1b[1m")
DIM = _c("\x1b[2m")
RESET = _c("\x1b[0m")


def _fmt_tool_event(payload: dict) -> str:
    t = payload.get("tool", "?")
    cmd = (payload.get("command") or payload.get("description") or "")[:120]
    return f"{BOLD}{CYAN}[{t}]{RESET} {DIM}{cmd}{RESET}"


def _print_event(payload: dict):
    etype = payload.get("type", "")

    if etype == "tool_start":
        print(f"\n  {_fmt_tool_event(payload)}")
    elif etype == "tool_output":
        out = (payload.get("output") or "")[:200]
        if out:
            print(f"  {DIM}{out}{RESET}")
    elif etype == "tool_progress":
        step = payload.get("step", "")
        data = payload.get("data", "")
        print(f"  {DIM}  [{step}] {data}{RESET}")
    elif etype == "web_sources":
        sources = payload.get("data", [])
        if sources:
            print(f"  {MAGENTA}Sources:{RESET}")
            for s in sources[:3]:
                title = s.get("title", "?")
                url = s.get("url", "")
                print(f"    {DIM}* {title} ({url}){RESET}")
    elif etype == "reasoning_trace":
        traces = payload.get("traces", [])
        for t in traces:
            tt = t.get("type", "")
            if tt == "reasoning_block":
                content = t.get("content", "")[:200]
                print(f"  {YELLOW}🤔 {content}{RESET}")
            elif tt == "confidence_score":
                print(f"  {YELLOW}Confidence: {t.get('value')}%{RESET}")
            elif tt == "alternatives_considered":
                print(f"  {YELLOW}Alternatives considered{RESET}")
    elif etype == "human_review":
        tools = payload.get("tools", [])
        print(f"\n  {RED}{BOLD}[HITL PAUSED]{RESET}")
        for t in tools:
            print(f"    {t.get('tool')}: {t.get('description', '')[:100]}")
        print(f"  {RED}Resume via: POST /api/agent/resume/{payload.get('run_id')}{RESET}")
    elif etype == "parallel_start":
        print(f"\n  {MAGENTA}Spawning {payload.get('count')} sub-agents...{RESET}")
    elif etype == "parallel_complete":
        errs = payload.get("errors", 0)
        ok = payload.get("count", 0) - errs
        print(f"  {MAGENTA}{ok} sub-agents done, {errs} errors{RESET}")
    elif etype == "agent_step":
        print(f"\n  {GREEN}--- Round {payload.get('round')} ---{RESET}")
    elif etype == "agent_prep":
        pass
    elif etype == "metrics":
        data = payload.get("data", {})
        dur = data.get("response_time", 0)
        tps = data.get("tokens_per_second", 0)
        inp = data.get("input_tokens", 0)
        out = data.get("output_tokens", 0)
        print(f"\n  {DIM}Metrics: {dur:.1f}s | {inp}→{out} tok | {tps:.1f} t/s{RESET}")
    elif etype == "error":
        print(f"\n  {RED}Error: {payload.get('error', '?')}{RESET}")
    elif etype == "budget_exceeded":
        print(f"\n  {RED}Budget exceeded: {payload.get('used')}/{payload.get('limit')}{RESET}")


def stream_agent(server: str, message: str):
    url = f"{server.rstrip('/')}/api/agent/stream"
    body = json.dumps({"message": message, "session_id": "demo-cli"}).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    buf = ""
    with urllib.request.urlopen(req, timeout=None) as resp:
        while True:
            chunk = resp.read(1).decode()
            if not chunk:
                break
            buf += chunk
            if buf.endswith("\n\n"):
                for line in buf.strip().split("\n"):
                    if line.startswith("data: [DONE]"):
                        return
                    if line.startswith("data: "):
                        try:
                            payload = json.loads(line[6:])
                        except json.JSONDecodeError:
                            continue
                        delta = payload.get("delta") if not payload.get("type") else None
                        if delta is not None:
                            print(delta, end="", flush=True)
                        else:
                            _print_event(payload)
                buf = ""


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Stream agent events from JARVIS API")
    parser.add_argument("message", nargs="?", default="say hello", help="Message to send")
    parser.add_argument("--server", default=os.getenv("JARVIS_URL", "http://localhost:8000"), help="Server URL")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI colors")

    args = parser.parse_args()

    if args.no_color:
        global CYAN, GREEN, YELLOW, RED, MAGENTA, BOLD, DIM, RESET
        CYAN = GREEN = YELLOW = RED = MAGENTA = BOLD = DIM = RESET = ""

    print(f"{BOLD}Agent:{RESET} {args.message}")
    print(f"{BOLD}Server:{RESET} {args.server}")
    print(f"{DIM}{'─' * 50}{RESET}")

    try:
        stream_agent(args.server, args.message)
    except KeyboardInterrupt:
        print(f"\n{DIM}cancelled{RESET}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{RED}Error: {e}{RESET}")
        sys.exit(1)

    print(f"\n{DIM}{'─' * 50}{RESET}")
    print(f"{GREEN}Done{RESET}")


if __name__ == "__main__":
    main()
