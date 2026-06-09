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

"""cli_slash_commands.py — Interactive slash command handler and help text."""
from __future__ import annotations
import logging

import argparse
import json
import os
from pathlib import Path

from cli_utils import colorize
from cli_state import CliState, HISTORY_PATH
logger = logging.getLogger(__name__)


def handle_cli_slash_command(text: str, state: CliState) -> str:
    from core.session import ConversationManager, list_sessions

    lowered = text.lower().strip()

    if lowered in {"/session", "/s"}:
        s = state.session
        name = getattr(s, "name", None) or ""
        name_str = f" ({name})" if name else ""
        print(f"Session: {s.session_id}{name_str}")
        print(f"Created: {s.created_at}")
        print(f"Messages: {s.message_count}")
        print(f"Tokens: {s.token_count}")
        print(f"Mode: {state.mode}")
        print(f"Model: {state.current_model}")
        return "handled"

    if lowered == "/sessions":
        sessions = list_sessions()
        if not sessions:
            print("No sessions found.")
        else:
            print(f"{'ID':<40} {'Created':<28} {'Msgs':<6} {'Name':<20}")
            print("-" * 94)
            for s in sessions:
                sid = s.get("session_id", "?")
                created = s.get("created_at", "")[:19]
                count = s.get("message_count", 0)
                name = ""
                spath = Path.home() / ".jarvis" / "sessions" / f"{sid}.json"
                if spath.exists():
                    try:
                        sdata = json.loads(spath.read_text(encoding="utf-8"))
                        name = sdata.get("name", "") or ""
                    except Exception as e:
                        logger.warning("[cli_slash_commands] execute_slash_command failed: %s", e)
                print(f"{sid:<40} {created:<28} {count:<6} {name:<20}")
        return "handled"

    if lowered == "/session-new":
        state.session.save()
        state.session = ConversationManager()
        print(f"JARVIS > new session: {state.session.session_id}")
        return "handled"

    if lowered.startswith("/session-switch "):
        sid = text.split(None, 1)[1].strip()
        spath = Path.home() / ".jarvis" / "sessions" / f"{sid}.json"
        if not spath.exists():
            print(f"JARVIS > session not found: {sid}")
        else:
            state.session.save()
            state.session = ConversationManager(session_id=sid)
            state.session.load()
            print(f"JARVIS > switched to session: {sid} ({state.session.message_count} messages)")
        return "handled"

    if lowered.startswith("/session-rename "):
        name = text.split(None, 1)[1].strip()
        state.session.rename(name)
        print(f"JARVIS > session renamed to: {name}")
        return "handled"

    if lowered == "/session-export":
        path = state.session.export_transcript()
        print(f"JARVIS > session exported to: {path}")
        return "handled"

    if lowered == "/session-fork":
        new_cm = state.session.fork()
        print(f"JARVIS > forked new session: {new_cm.session_id}")
        state.session.save()
        state.session = new_cm
        return "handled"

    if lowered == "/session-compact":
        before = state.session.message_count
        state.session.compact()
        after = state.session.message_count
        print(f"JARVIS > compacted session: {before} -> {after} messages")
        return "handled"

    if lowered == "/undo":
        msgs = state.session.messages
        if len(msgs) < 2:
            print("JARVIS > nothing to undo.")
        else:
            removed = msgs[-2:]
            if removed[0]["role"] == "user" and removed[-1]["role"] == "assistant":
                state.session.messages = msgs[:-2]
                state.session.save()
                print(f"JARVIS > removed last exchange ({len(removed)} messages).")
            else:
                last = msgs.pop()
                state.session.save()
                print(f"JARVIS > removed last {last['role']} message.")
        return "handled"

    if lowered == "/model":
        print(f"JARVIS > current model: {state.current_model}")
        return "handled"
    if lowered.startswith("/model "):
        model = text.split(None, 1)[1].strip()
        state.current_model = model
        if state.config:
            state.config.default_model = model
            state.config.save()
        print(f"JARVIS > model set to: {model}")
        return "handled"

    if lowered == "/clear":
        os.system("cls" if os.name == "nt" else "clear")
        return "handled"

    if lowered == "/timestamps":
        state.show_timestamps = not state.show_timestamps
        if state.config:
            state.config.show_timestamps = state.show_timestamps
            state.config.save()
        status = "ON" if state.show_timestamps else "OFF"
        print(f"JARVIS > timestamps {status}")
        return "handled"

    if lowered == "/debug":
        state.debug = not state.debug
        if state.config:
            state.config.debug = state.debug
            state.config.save()
        status = "ON" if state.debug else "OFF"
        print(f"JARVIS > debug {status}")
        return "handled"

    if lowered == "/debug-search":
        state.debug_search = not state.debug_search
        if state.config:
            state.config.debug_search = state.debug_search
            state.config.save()
        status = "ON" if state.debug_search else "OFF"
        print(f"JARVIS > debug-search {status}")
        return "handled"

    if lowered == "/theme":
        if state.config:
            new_theme = "light" if state.config.theme == "dark" else "dark"
            state.config.theme = new_theme
            state.config.save()
            print(f"JARVIS > theme set to {new_theme}. (restart to take full effect)")
        else:
            print("JARVIS > theme toggled.")
        return "handled"

    if lowered == "/history" or lowered.startswith("/history "):
        parts = text.split()
        n = 10
        if len(parts) > 1:
            try:
                n = int(parts[1])
            except ValueError:
                pass
        msgs = state.session.messages
        if not msgs:
            print("No messages.")
        else:
            for msg in msgs[-n:]:
                ts = msg.get("timestamp", "")[:19]
                ts_str = f"[{ts}] " if ts else ""
                print(f"{ts_str}{msg['role'].upper()}: {msg['content'][:200]}")
        return "handled"

    if lowered == "/agent":
        print(f"JARVIS > current mode: {state.mode}")
        return "handled"
    if lowered.startswith("/agent "):
        target = text.split(None, 1)[1].strip().lower()
        if target not in {"chat", "agent"}:
            print("JARVIS > mode must be 'chat' or 'agent'.")
        else:
            state.mode = target
            if state.config:
                state.config.mode = target
                state.config.save()
            print(f"JARVIS > mode set to {target}.")
        return "handled"

    if lowered.startswith("/mode "):
        target = text.split(None, 1)[1].strip().lower()
        if target not in {"chat", "agent"}:
            print("JARVIS > mode must be 'chat' or 'agent'.")
        else:
            state.mode = target
            if state.config:
                state.config.mode = target
                state.config.save()
            print(f"JARVIS > mode set to {target}.")
        return "handled"

    if lowered == "/stash":
        return "stash_capture"
    if lowered.startswith("/stash "):
        stash_text = text.split(None, 1)[1].strip()
        idx = state.session.stash_prompt(stash_text)
        print(f"JARVIS > stashed as #{idx}.")
        return "handled"

    if lowered == "/stash-list":
        items = state.session.list_stash()
        if not items:
            print("No stashed prompts.")
        else:
            for item in items:
                idx = item.get("index", 0)
                label = item.get("label", "") or ""
                text_preview = item.get("text", "")[:80]
                print(f"  #{idx:3d}  {label:15} {text_preview}")
        return "handled"

    if lowered.startswith("/stash-load "):
        parts = text.split()
        try:
            idx = int(parts[1])
        except (IndexError, ValueError):
            print("Usage: /stash-load <n>")
            return "handled"
        stash_text = state.session.load_stash(idx)
        if not stash_text:
            print(f"JARVIS > stash #{idx} not found.")
        else:
            state._pending_text = stash_text
            print(f"JARVIS > loaded stash #{idx}.")
            return "skip"
        return "handled"

    if lowered.startswith("/read "):
        path = text.split(None, 1)[1].strip()
        import asyncio
        from core.file_agent import file_agent
        try:
            content = asyncio.run(file_agent.read_file(path))
            if len(content) > 2000:
                print(f"{path} ({len(content)} chars, showing first 2000):")
                print(content[:2000])
                print(f"\n... ({len(content) - 2000} more chars)")
            else:
                print(content)
        except Exception as e:
            print(f"Error reading {path}: {e}")
        return "handled"

    if lowered.startswith("/write "):
        path = text.split(None, 1)[1].strip()
        print("Enter file content (end with '---END---' on its own line):")
        lines = []
        try:
            while True:
                line = input()
                if line.strip() == "---END---":
                    break
                lines.append(line)
        except (KeyboardInterrupt, EOFError):
            print("\nCancelled.")
            return "handled"
        content = "\n".join(lines)
        import asyncio
        from core.file_agent import file_agent
        result = asyncio.run(file_agent.write_file(path, content))
        if result.get("cancelled"):
            print("Write cancelled.")
        elif result.get("changed"):
            print(f"Written to {path} ({result['size']} bytes)")
        else:
            print(f"File unchanged: {path}")
        return "handled"

    if lowered.startswith("/edit "):
        path = text.split(None, 1)[1].strip()
        print("Enter SEARCH block (end with '---REPLACE---' on its own line, then REPLACE block, end with '---END---'):")
        lines = []
        try:
            while True:
                line = input()
                if line.strip() == "---END---":
                    break
                lines.append(line)
        except (KeyboardInterrupt, EOFError):
            print("\nCancelled.")
            return "handled"
        full = "\n".join(lines)
        if "---REPLACE---" in full:
            parts = full.split("---REPLACE---", 1)
            search_text = parts[0].strip("\n")
            replace_text = parts[1].strip("\n")
            import asyncio
            from core.file_agent import file_agent
            result = asyncio.run(file_agent.edit_file(path, search_text, replace_text))
            if result.get("error"):
                print(f"Edit failed: {result['error']}")
            elif result.get("cancelled"):
                print("Edit cancelled.")
            else:
                print(f"Edited {path} ({'exact' if result.get('exact_match') else 'fuzzy'} match)")
        else:
            print("Error: no ---REPLACE--- separator found.")
        return "handled"

    if lowered.startswith("/ls") or lowered.startswith("/dir "):
        parts = text.split(None, 1)
        path = parts[1].strip() if len(parts) > 1 else "."
        recursive = " -r" in lowered or " --recursive" in lowered
        import asyncio
        from core.file_agent import file_agent
        try:
            files = asyncio.run(file_agent.list_files(path, recursive=recursive))
            if not files:
                print(f"No files in {path}")
            else:
                total = len(files)
                for f in files[:30]:
                    size = f["size"]
                    size_str = f"{size:,} B" if size < 1024 else f"{size/1024:.1f} KB" if size < 1048576 else f"{size/1048576:.1f} MB"
                    print(f"  {f['name']:<50} {size_str:>10}")
                if total > 30:
                    print(f"  ... and {total - 30} more files")
        except Exception as e:
            print(f"Error: {e}")
        return "handled"

    if lowered.startswith("/tree "):
        path = text.split(None, 1)[1].strip()
        import asyncio
        from core.file_agent import file_agent
        try:
            tree = asyncio.run(file_agent.tree_view(path))
            print(tree)
        except Exception as e:
            print(f"Error: {e}")
        return "handled"

    if lowered.startswith("/run "):
        cmd = text.split(None, 1)[1].strip()
        import asyncio
        from core.file_agent import file_agent
        result = asyncio.run(file_agent.run_command(cmd))
        if result.get("error"):
            print(f"Error: {result['error']}")
        elif result.get("cancelled"):
            print("Command cancelled.")
        else:
            if result["stdout"]:
                print(result["stdout"])
            if result["stderr"]:
                print(f"[stderr]\n{result['stderr']}")
            print(f"[exit code: {result['returncode']}]")
        return "handled"

    if lowered == "/diff":
        import asyncio
        from core.file_agent import file_agent
        result = asyncio.run(file_agent.run_command("git diff", skip_confirm=True))
        if result.get("stdout"):
            print(result["stdout"])
        else:
            print("No changes or not a git repository.")
        return "handled"

    if lowered.startswith("/diff "):
        path = text.split(None, 1)[1].strip()
        import asyncio
        from core.file_agent import file_agent
        result = asyncio.run(file_agent.run_command(f"git diff -- {path}", skip_confirm=True))
        if result.get("stdout"):
            print(result["stdout"])
        else:
            print(f"No changes to {path}")
        return "handled"

    if lowered == "/config":
        cfg = state.config
        print(f"default_model: {cfg.default_model}")
        print(f"debug: {cfg.debug}")
        print(f"debug_search: {cfg.debug_search}")
        print(f"show_timestamps: {cfg.show_timestamps}")
        print(f"mode: {cfg.mode}")
        print(f"theme: {cfg.theme}")
        print(f"aliases: {json.dumps(cfg.aliases or {}, indent=2)}")
        return "handled"

    if lowered.startswith("/config "):
        parts = text.split(None, 2)
        if len(parts) < 3:
            print("Usage: /config <key> <value>")
            return "handled"
        key = parts[1]
        val = parts[2]
        cfg = state.config
        if not hasattr(cfg, key):
            print(f"Unknown config key: {key}")
            return "handled"
        if isinstance(getattr(cfg, key), bool):
            setattr(cfg, key, val.lower() in ("true", "yes", "1", "on"))
        elif isinstance(getattr(cfg, key), int):
            setattr(cfg, key, int(val))
        else:
            setattr(cfg, key, val)
        cfg.save()
        print(f"Config updated: {key} = {getattr(cfg, key)}")
        if key == "debug":
            state.debug = cfg.debug
        elif key == "debug_search":
            state.debug_search = cfg.debug_search
        elif key == "show_timestamps":
            state.show_timestamps = cfg.show_timestamps
        elif key == "default_model":
            state.current_model = cfg.default_model
        elif key == "mode":
            state.mode = cfg.mode
        return "handled"

    if lowered == "/alias":
        cfg = state.config
        if not cfg.aliases:
            print("No aliases defined.")
        else:
            for k, v in cfg.aliases.items():
                print(f"  /{k} -> {v}")
        return "handled"

    if lowered.startswith("/alias "):
        parts = text.split(None, 2)
        if len(parts) < 3:
            print("Usage: /alias <name> <command>")
            return "handled"
        name = parts[1].lstrip("/")
        command = parts[2]
        cfg = state.config
        if cfg.aliases is None:
            cfg.aliases = {}
        cfg.aliases[name] = command
        cfg.save()
        print(f"Alias set: /{name} -> {command}")
        return "handled"

    if lowered.startswith("/alias-del "):
        name = text.split(None, 1)[1].strip().lstrip("/")
        cfg = state.config
        if cfg.aliases and name in cfg.aliases:
            del cfg.aliases[name]
            cfg.save()
            print(f"Alias removed: /{name}")
        else:
            print(f"Alias not found: /{name}")
        return "handled"

    if lowered == "/status":
        from cli_commands import cmd_status
        cmd_status(argparse.Namespace())
        return "handled"

    if lowered == "/boot":
        from cli_visuals import render_boot_screen
        render_boot_screen(animated=True, delay=0.025)
        return "handled"

    if lowered == "/agents":
        from cli_visuals import render_agents
        render_agents()
        return "handled"

    if lowered == "/design":
        from cli_visuals import render_design_plan
        render_design_plan()
        return "handled"

    if lowered == "/frames" or lowered.startswith("/frames "):
        from cli_visuals import render_state_frames
        parts = lowered.split(maxsplit=1)
        render_state_frames(parts[1] if len(parts) > 1 else "all")
        return "handled"

    if lowered in {"/help", "/h", "/?"}:
        print_help()
        return "handled"

    if lowered in {"/exit"}:
        print("JARVIS > saving session and exiting...")
        return "exit"

    if lowered.startswith("/generate-ui ") or lowered.startswith("/gui "):
        from cli_requests import request_json
        prompt = text.split(None, 1)[1].strip()
        context = "html"
        if " --flutter" in lowered or " --fl" in lowered:
            context = "flutter"
        prompt_clean = prompt.replace(" --flutter", "").replace(" --fl", "")
        result = request_json(state.base_url, "/api/generate-ui", {
            "message": prompt_clean,
            "context": context,
        })
        if result.get("error"):
            print(f"{colorize('Error:', 'red')} {result['error']}")
        else:
            fp = result.get("file_path", "?")
            template_name = result.get("template_name", "?")
            template_cat = ", ".join(result.get("template_category", []))
            print(f"{colorize('Generated UI:', 'green')} {fp}")
            if template_name:
                print(f"{colorize('Template:', 'cyan')} {template_name} ({template_cat})")
            print(f"{colorize('Preview:', 'cyan')}")
            code = result.get("code", "")
            if len(code) > 500:
                print(code[:500])
                print(f"\n... ({len(code) - 500} more chars)")
            else:
                print(code)
        return "handled"

    if lowered.startswith("/templates "):
        parts = lowered.split()
        subcmd = parts[1] if len(parts) > 1 else "help"
        if subcmd == "sync":
            from tools.template_library import TemplateLibrary
            print(f"{colorize('Syncing templates...', 'yellow')} (this may take 5-15 minutes)")
            tl = TemplateLibrary()
            tl.sync()
            print(f"{colorize('Done!', 'green')} {len(tl.registry)} templates available")
        elif subcmd == "list":
            from tools.template_library import TemplateLibrary
            tl = TemplateLibrary()
            tl._load_registry()
            cats = {}
            for t in tl.registry:
                for c in t.get("category", ["uncategorized"]):
                    cats.setdefault(c, []).append(t.get("name", "?"))
            for cat in sorted(cats):
                items = cats[cat]
                print(f"  {colorize(cat, 'cyan')} ({len(items)})")
                for name in items[:5]:
                    print(f"    - {name}")
                if len(items) > 5:
                    print(f"    ... and {len(items)-5} more")
        elif subcmd == "search":
            query = " ".join(parts[2:]) if len(parts) > 2 else ""
            if not query:
                print("Usage: /templates search <query>")
            else:
                from tools.template_library import TemplateLibrary
                tl = TemplateLibrary()
                tl._load_registry()
                matches = tl.find_template(query, top_n=10)
                if matches:
                    print(f"{colorize(f'Top {len(matches)} matches:', 'green')}")
                    for m in matches:
                        print(f"  - {m.get('name')} ({', '.join(m.get('category', []))})")
                else:
                    print("No matches found")
        else:
            print("Usage: /templates <sync|list|search <query>>")
        return "handled"

    if lowered.startswith("/website "):
        topic = text.split(None, 1)[1].strip()
        if not topic:
            print("Usage: /website <topic> [pages...]")
            return "handled"
        from tools.website_generator import generate_site
        pages = None
        rest = topic.split(" --pages ")
        if len(rest) > 1:
            topic = rest[0].strip()
            pages = [p.strip() for p in rest[1].split(",")]
        print(f"{colorize('Building website:', 'cyan')} {topic}")
        result = generate_site(topic, pages)
        if result.get("error"):
            print(f"{colorize('Error:', 'red')} {result['error']}")
        else:
            print(f"{colorize('Site:', 'green')} {result['directory']}")
            print(f"{colorize('Pages:', 'cyan')} {result['page_count']}")
            for p in result['pages'][:6]:
                print(f"  {p['page']:15s} {os.path.basename(p['file']):20s} ({p['size']} bytes)")
        return "handled"

    if lowered == "/tools":
        from cli_requests import request_json
        result = request_json(state.base_url, "/os/tools", method="GET")
        tools = [tool.get("name", "") for tool in result.get("tools", [])]
        print("Tools:", ", ".join(sorted(name for name in tools if name)))
        return "handled"

    if lowered.startswith("/opencode "):
        task = text.split(None, 1)[1].strip()
        import asyncio
        from core.context_hub import ContextHub
        from core.opencode_delegate import delegate_to_opencode, is_opencode_task
        if not is_opencode_task(task) and " --force" not in lowered:
            print(f"{colorize('Not clearly an opencode task.', 'yellow')} Use --force to override.")
            return "handled"
        print(f"{colorize('Delegating to opencode...', 'cyan')}")
        hub = ContextHub()
        ctx = asyncio.run(hub.gather(task_type="code", prompt=task))
        result = asyncio.run(delegate_to_opencode(
            task=task,
            context={"context_hub": hub, "extra_context": hub.format_for_prompt(ctx)},
            timeout=300,
        ))
        if result.get("success"):
            print(f"{colorize('OpenCode completed:', 'green')}")
            if result["stdout"]:
                print(result["stdout"][:3000])
        else:
            print(f"{colorize('OpenCode failed:', 'red')} {result.get('error', 'unknown')}")
            if result.get("stdout"):
                print(result["stdout"][:1000])
        return "handled"

    if lowered.startswith("/plan "):
        from cli_helpers import build_cli_context, print_plan_preview
        from cli_requests import request_json
        prompt = text.split(None, 1)[1].strip()
        context = build_cli_context(prompt)
        context["cli_mode"] = state.mode
        endpoint = "/os/agents/preview" if state.mode == "agent" else "/os/agent/plan"
        payload = {"prompt": prompt, "context": context}
        if state.mode == "agent":
            payload["agent_name"] = "auto"
        preview = request_json(state.base_url, endpoint, payload)
        specialist = preview.get("specialist", {}).get("name")
        if specialist:
            print(f"Agent: {specialist}")
        print_plan_preview(preview)
        return "handled"
    if lowered.startswith("/goal "):
        from cli_helpers import build_cli_context, print_plan_preview
        from cli_requests import request_json
        prompt = text.split(None, 1)[1].strip()
        context = build_cli_context(prompt)
        context["cli_mode"] = state.mode
        endpoint = "/os/agents/submit" if state.mode == "agent" else "/os/agent/submit"
        payload = {"prompt": prompt, "context": context}
        if state.mode == "agent":
            payload["agent_name"] = "auto"
        result = request_json(state.base_url, endpoint, payload)
        specialist = result.get("specialist", {}).get("name")
        if specialist:
            print(f"Agent: {specialist}")
        print(f"JARVIS > queued goal {result['goal']['goal_id']} as job {result['job_id']}")
        print_plan_preview(result)
        return "handled"
    if lowered.startswith("/develop "):
        from cli_helpers import build_cli_context, print_plan_preview
        from cli_requests import request_json, poll_job
        prompt = text.split(None, 1)[1].strip()
        context = build_cli_context(prompt)
        context["cli_mode"] = state.mode
        endpoint = "/os/agents/submit" if state.mode == "agent" else "/os/agent/submit"
        payload = {"prompt": prompt, "context": context}
        if state.mode == "agent":
            payload["agent_name"] = "auto"
        result = request_json(state.base_url, endpoint, payload)
        specialist = result.get("specialist", {}).get("name")
        if specialist:
            print(f"Agent: {specialist}")
        print(f"JARVIS > starting development goal {result['goal']['goal_id']}")
        print_plan_preview(result)
        poll_job(state.base_url, result["job_id"])
        return "handled"
    if lowered.startswith("/supervisor "):
        from cli_requests import request_json, poll_supervisor
        goal = text.split(None, 1)[1].strip()
        print(f"JARVIS > Starting autonomous build: {goal}")
        try:
            result = request_json(state.base_url, "/api/supervisor/start", {
                "goal": goal, "auto_approve": True, "max_parallel": 2
            })
            bid = result.get("build_id", "?")
            print(f"  Build ID: {bid}")
            print(f"  Project: {result.get('project', '?')}")
            print(f"  Tasks: {result.get('tasks', 0)}")
            print(f"  Status: {result.get('status', '?')}")
            print(f"  Workspace: {result.get('workspace', '?')}")
            print(f"\n  Check status with: /supervisor-status")
            if bid != "?":
                poll_supervisor(state.base_url, bid)
        except Exception as e:
            print(f"  Failed: {e}")
        return "handled"
    if lowered.startswith("/supervisor-status"):
        from cli_requests import request_json
        try:
            result = request_json(state.base_url, "/api/supervisor/list", method="GET")
            builds = result.get("builds", [])
            if not builds:
                print("No active builds.")
            else:
                for b in builds:
                    print(f"  [{b['status']}] {b['id']}: {b['goal']} ({b['completed']}/{b['failed']})")
        except Exception as e:
            print(f"  Failed: {e}")
        return "handled"
    if lowered.startswith("/build "):
        from cli_requests import request_json
        goal = text.split(None, 1)[1].strip()
        print(f"JARVIS > Starting autonomous build: {goal}")
        try:
            result = request_json(state.base_url, "/api/build/start", {
                "goal": goal, "auto_approve": True
            })
            print(f"  Project: {result.get('name', '?')}")
            print(f"  Status: {result.get('status', '?')}")
            print(f"  Retries: {result.get('retries', 0)}")
            issues = result.get('issues', [])
            if issues:
                print(f"  Issues: {', '.join(issues[:5])}")
            print(f"\n  Check status with: /projects")
        except Exception as e:
            print(f"  Failed: {e}")
        return "handled"
    if lowered.startswith("/projects"):
        from cli_requests import request_json
        try:
            result = request_json(state.base_url, "/api/build/projects", method="GET")
            projects = result.get("projects", [])
            if not projects:
                print("No projects found.")
            else:
                print(f"\nProjects ({len(projects)}):")
                for p in projects:
                    status_icon = {"done": "✓", "failed": "✗", "building": "▶", "running": "▶",
                                   "queued": "○", "paused": "⏸", "cancelled": "⊘", "created": "·"}
                    icon = status_icon.get(p.get("status", ""), "·")
                    name = p.get("name", "?")
                    goal = p.get("goal", "")[:60]
                    retries = p.get("retries", 0)
                    issues = p.get("issues", 0)
                    print(f"  {icon} {name}: {goal} [{p.get('status', '?')}] "
                          f"retries={retries} issues={issues}")
        except Exception as e:
            print(f"  Failed: {e}")
        return "handled"
    if lowered.startswith("/service "):
        from cli_requests import request_json
        action = text.split(None, 1)[1].strip().lower()
        try:
            result = request_json(state.base_url, "/api/build/daemon", {"action": action})
            print(f"Daemon: {result.get('status', 'done')}")
        except Exception as e:
            print(f"  Failed: {e}")
        return "handled"
    if lowered.startswith("/interrupt ") or lowered.startswith("/pause "):
        from cli_requests import request_json
        target = text.split(None, 1)[1].strip()
        try:
            result = request_json(state.base_url, f"/api/build/interrupt/{target}", method="POST")
            print(f"Interrupt: {result.get('status')} for {target}")
        except Exception as e:
            print(f"  Failed: {e}")
        return "handled"
    if lowered.startswith("/override "):
        from cli_requests import request_json
        parts = text.split(None, 2)
        if len(parts) < 3:
            print("Usage: /override <project> <field=value> [field2=value2 ...]")
            return "handled"
        proj = parts[1]
        pairs = parts[2].split()
        overrides = {}
        for p in pairs:
            if "=" in p:
                k, v = p.split("=", 1)
                overrides[k.strip()] = v.strip()
        try:
            result = request_json(state.base_url, f"/api/build/override/{proj}",
                                  {"overrides": overrides}, method="POST")
            print(f"Override: {result.get('status')} on {proj}")
        except Exception as e:
            print(f"  Failed: {e}")
        return "handled"
    if lowered.startswith("/resume "):
        from cli_requests import request_json
        target = text.split(None, 1)[1].strip()
        try:
            result = request_json(state.base_url, f"/api/build/resume/{target}", method="POST")
            print(f"Resume: {result.get('status')} for {target}")
        except Exception as e:
            print(f"  Failed: {e}")
        return "handled"
    if lowered.startswith("/checkpoints "):
        from cli_requests import request_json
        target = text.split(None, 1)[1].strip()
        try:
            result = request_json(state.base_url, f"/api/build/checkpoints/{target}", method="GET")
            cps = result.get("checkpoints", [])
            print(f"Checkpoints for {target}: {len(cps)}")
            for cp in cps[-10:]:
                print(f"  {cp}")
        except Exception as e:
            print(f"  Failed: {e}")
        return "handled"
    if lowered.startswith("/decisions "):
        from cli_requests import request_json
        target = text.split(None, 1)[1].strip()
        try:
            result = request_json(state.base_url, f"/api/build/decisions/{target}", method="GET")
            entries = result.get("decisions", [])
            seed = result.get("seed")
            replay = result.get("replay_mode", False)
            print(f"Decisions for {target} (seed={seed}, replay={replay}): {len(entries)} entries")
            for e in entries[-10:]:
                print(f"  [{e['step']}] {e['decision_type']} → {e['chosen'][:60]}")
        except Exception as e:
            print(f"  Failed: {e}")
        return "handled"
    if lowered.startswith("/identity"):
        from cli_requests import request_json
        try:
            result = request_json(state.base_url, "/api/build/identity", method="GET")
            print(f"JARVIS v{result.get('version', '?')}")
            print(f"  Capabilities ({len(result.get('capabilities', []))}): {', '.join(result.get('capabilities', [])[:8])}")
            print(f"  Models: {result.get('models', {})}")
            print(f"  Phases: {len(result.get('phases_implemented', []))}")
        except Exception as e:
            print(f"  Identity error: {e}")
        return "handled"
    if lowered.startswith("/governor "):
        from cli_requests import request_json
        target = text.split(None, 1)[1].strip()
        try:
            result = request_json(state.base_url, f"/api/build/governor/history/{target}", method="GET")
            decisions = result.get("decisions", [])
            print(f"Governor history for {target}: {len(decisions)} decisions")
            for d in decisions[-5:]:
                print(f"  {d['action']} ({d['confidence']}): {d['reason']}")
        except Exception as e:
            print(f"  Failed: {e}")
        return "handled"
    if lowered.startswith("/env"):
        from cli_requests import request_json
        try:
            result = request_json(state.base_url, "/api/build/environment", method="GET")
            print("Environment:")
            print(f"  Disk: {result.get('disk_free_gb', '?')}/{result.get('disk_total_gb', '?')} GB free")
            print(f"  Memory: {result.get('memory_free_mb', '?')}/{result.get('memory_total_mb', '?')} MB")
            print(f"  Ollama: {'✓' if result.get('ollama_available') else '✗'} ({result.get('ollama_latency_ms', 0):.0f}ms)")
            print(f"  Network: {'✓' if result.get('network_reachable') else '✗'}")
            for w in result.get('warnings', []):
                print(f"  ⚠ {w}")
        except Exception as e:
            print(f"  Failed: {e}")
        return "handled"
    if lowered.startswith("/adapt"):
        from cli_requests import request_json
        try:
            result = request_json(state.base_url, "/api/build/adaptation", method="GET")
            actions = result.get("actions", [])
            rules = result.get("rules_triggered", {})
            if actions:
                print(f"Adaptation: {len(actions)} actions")
                for a in actions:
                    print(f"  {a['action']}: {a['reason']}")
            else:
                print("No adaptation actions needed")
            if rules:
                print(f"Rules triggered: {rules}")
        except Exception as e:
            print(f"  Failed: {e}")
        return "handled"
    if lowered.startswith("/vision "):
        from cli_helpers import build_cli_context
        from cli_requests import request_json, extract_reply
        prompt = text.split(None, 1)[1].strip()
        context = build_cli_context(prompt)
        context["intent"] = "vision"
        context["cli_mode"] = state.mode
        result = request_json(state.base_url, "/os/agent/think", {"prompt": prompt, "context": context})
        print(f"JARVIS > {extract_reply(result)}")
        return "handled"
    if lowered.startswith("/feedback "):
        from cli_requests import request_json
        parts = text.split(None, 2)
        if len(parts) >= 3:
            accepted = parts[1].lower() in ("yes", "y", "good", "correct", "1", "true")
            reason = parts[2]
            try:
                result = request_json(state.base_url, "/feedback", {
                    "message": "", "response": "", "accepted": accepted, "reason": reason
                })
                print(f"JARVIS > Feedback recorded. Rules: {result.get('rules', 0)}")
            except Exception as exc:
                print(f"Feedback failed: {exc}")
        else:
            print("Usage: /feedback <yes|no> <reason>")
        return "handled"

    from core.plugins.api import CLI_COMMANDS
    if text.startswith("/"):
        cmd_name = text[1:].split()[0].lower()
        if cmd_name in CLI_COMMANDS:
            entry = CLI_COMMANDS[cmd_name]
            try:
                result = entry["handler"](text)
                if result:
                    print(result)
            except Exception as e:
                print(colorize(f"[Plugin /{cmd_name}] Error: {e}", "red"))
            return "handled"

    return "ignored"


def print_help():
    print(colorize("""JARVIS CLI Commands:

Session:
  /session /s           Show current session info
  /sessions             List all sessions
  /session-new          Start a new session
  /session-switch <id>  Switch to a session
  /session-rename <name> Rename session
  /session-export       Export session transcript
  /session-fork         Fork current session
  /session-compact      Compact session (summarize old)
  /undo                 Remove last exchange

Model:
  /model                Show current model
  /model <name>         Switch model

Config:
  /config               Show all config values
  /config <key> <val>   Set a config value (saved to ~/.jarvis/config.json)
  /alias                List aliases
  /alias <name> <cmd>   Define a command alias
  /alias-del <name>     Remove an alias

Display:
  /clear                Clear screen
  /timestamps           Toggle timestamps
  /debug                Toggle debug mode
  /debug-search         Toggle search result debugging
  /theme                Toggle dark/light theme

History:
  /history [n]          Show last N exchanges (default 10)

Agent:
  /agent /mode          Show current mode
  /agent <mode>         Switch mode (chat/agent)

Stash:
  /stash <text>         Save a prompt
  /stash-list           List stashed prompts
  /stash-load <n>       Load a stashed prompt

System:
  /status               Show system status
  /boot                 Show diamond mascot boot screen
  /agents               Show the 9-agent terminal overview
  /design               Show CLI animation/build plan
  /frames [state]       Print mascot frames (idle/thinking/talking/error/success)
  /help /h /?           Show this help
  /exit                 Save and exit

Files:
  /read <path>          Read and display a file
  /write <path>         Write content to a file
  /edit <path>          Edit file with SEARCH/REPLACE blocks
  /ls [path]            List files in directory
  /tree <path>          Show directory tree
  /run <command>        Run a shell command
  /diff [path]          Show git diff

Templates:
  /templates sync       Download all templates (~3 GB)
  /templates list       List template categories
  /templates search <q> Search templates by keyword

Sites:
  /website <topic>      Generate multi-page website from templates

Generate:
  /generate-ui <desc>   Generate a UI from template (--flutter for Flutter)
  /gui <desc>           Shortcut for /generate-ui

Delegation:
  /opencode <task>      Delegate heavy coding task to opencode (--force to bypass detection)

Build System:
  /build <goal>         Start autonomous build with control loop
  /projects             List all projects and their status
  /service <action>     Daemon: start|stop|install|uninstall|status
  /interrupt <proj>     Pause build after current step
  /cancel <proj>        Cancel build immediately
  /override <proj> k=v  Override a field (e.g. status=done, retries=0)
  /resume <proj>        Resume a paused build
  /checkpoints <proj>   List checkpoints for a project
  /decisions <proj>     Show decision log for a project
  /identity             Show JARVIS system identity
  /governor <proj>      Show governor decision history
  /env                  Show environment health snapshot
  /adapt                Show proactive adaptation actions
  /plan <goal>          Preview an execution plan
  /goal <goal>          Submit a long-running goal

Supervisor:
  /supervisor <goal>    Launch autonomous multi-agent build (parallel CLI agents)
  /supervisor-status    Check active supervisor builds
  /develop <goal>       Start development workflow

Other:
  /vision <prompt>      Vision analysis
  /feedback <yes|no> <reason>  Provide feedback
  /tools                List available tools

Plugin Commands:
  See /plugins for plugin-provided CLI commands.

CLI Enhancements:
  Tab completion        Hit Tab to complete commands, paths, sessions, models
  History               Up/Down arrows navigate command history
  Aliases               Define shortcuts with /alias <name> <command>
  Persistent config     Settings saved to ~/.jarvis/config.json""", 'cyan'))
