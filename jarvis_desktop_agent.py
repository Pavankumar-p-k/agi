#!/usr/bin/env python3
"""
JARVIS Desktop Agent - MODEL-AGNOSTIC agent that interprets a goal via an LLM
provider (Ollama default for testing) and drives real desktop automation.

DESIGN: The agent is decoupled from any single model.
  - Uses `ModelProvider` abstraction (model_provider.py)
  - Default: Ollama (local, for TESTING only)
  - After build: switch via JARVIS_MODEL_PROVIDER=openai|anthropic, no code changes

USAGE:
    python jarvis_desktop_agent.py "your goal here"

EXAMPLE:
    python jarvis_desktop_agent.py "open notepad and type hello world"
    python jarvis_desktop_agent.py "how much disk space is free"
    python jarvis_desktop_agent.py "list my bluetooth devices"
    python jarvis_desktop_agent.py "check if chrome is running"
"""
import sys
import json
import time
import re
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from jarvis_provider import get_provider

from core.desktop.controller import desktop_controller as dc
from core.desktop.window import window_controller as wc
from core.workspace.process_monitor import ProcessMonitor
from core.workspace.clipboard_manager import ClipboardManager
from core.desktop.user_actions import user_actions as U

# ---------- ACTIVE PROVIDER ----------
# Use the unified top-level provider (jarvis_provider). Role-chosen via CHAT_MODEL in .env.
PROVIDER = get_provider("chat")
VISION_PROVIDER = get_provider("vision")


# ---------- TOOL DOCS ----------
TOOL_DOCS = {
    # Core desktop
    "list_windows": 'Lists all open window titles. Args: none.',
    "get_screen_size": 'Gets screen width and height. Args: none.',
    "get_mouse_position": 'Gets current mouse x,y. Args: none.',
    "move_mouse": 'Moves mouse. Args: {"x":int,"y":int}.',
    "click": 'Clicks at coordinate. Args: {"x":int,"y":int}.',
    "type_text": 'Types text. Args: {"text":"str"}.',
    "press_key": 'Presses key. Args: {"key":"enter|tab|escape|ctrl|..."}.',
    "hotkey": 'Presses combo. Args: {"key1":"ctrl","key2":"c"}.',
    "open_url": 'Opens URL in browser. Args: {"url":"str"}.',
    "launch_app": 'Launches app. Args: {"app":"notepad|chrome|..."}.',
    "focus_window": 'Focuses window. Args: {"title":"str"}.',
    "close_window": 'Closes window. Args: {"title":"str"}.',
    "process_running": 'Checks if process runs. Args: {"name":"chrome"}.',
    "clipboard_get": 'Reads clipboard. Args: none.',
    "clipboard_set": 'Writes clipboard. Args: {"text":"str"}.',

    # SMART APP CONTROL
    "count_windows": 'Counts open windows/apps. Args: {"filter":"optional substring, e.g. chrome"}. Returns count + names.',
    "count_running_apps": 'Counts running GUI apps. Args: none.',
    "focus_or_launch": 'If app is already running, focus it; otherwise launch it. Args: {"app":"notepad|chrome|code", "window_title":"optional partial title"}. Fixes duplicate reopening.',
    "new_window": 'Opens a NEW additional window/instance of an app even if already running. Args: {"app":"notepad|chrome", "cmd_extra":"optional e.g. --new-window"}.',
    "open_in_app": 'Open a file in a specific app/IDE. Args: {"path":"C:\\...\\file.txt","app":"notepad|code|chrome"}.',
    "app_state": 'Show instances/windows of one app. Args: {"app_name":"chrome|notepad|code"}.',

    # FILE SYSTEM
    "list_files": 'List files/folders. Args: {"path":"str","recursive":bool}.',
    "create_file": 'Create file with content. Args: {"path":"str","content":"str"}.',
    "read_file": 'Read file content. Args: {"path":"str"}.',
    "create_folder": 'Create folder. Args: {"path":"str"}.',
    "move_file": 'Move file. Args: {"src":"str","dst":"str"}.',
    "copy_file": 'Copy file. Args: {"src":"str","dst":"str"}.',
    "delete_path": 'Delete file/folder. Args: {"path":"str","recursive":bool}.',
    "rename_file": 'Rename file. Args: {"path":"str","new_name":"str"}.',
    "write_file": 'Overwrite file. Args: {"path":"str","content":"str"}.',

    # STORAGE / TIME / SYSTEM
    "storage_info": 'Disk/drive usage in GB. Args: none.',
    "current_time": 'Current date/time/timezone. Args: none.',
    "system_info": 'OS, CPU, hostname, arch. Args: none.',

    # NETWORK
    "network_info": 'Network interfaces, IPs, link speed. Args: none.',
    "network_speed": 'Measure current download/upload Mbps. Args: none.',
    "ping": 'Ping a host. Args: {"host":"8.8.8.8"}.',

    # BLUETOOTH
    "bluetooth_devices": 'List bluetooth devices. Args: none.',
    "bluetooth_connect": 'Connect bluetooth device. Args: {"name":"str"}.',
    "bluetooth_disconnect": 'Disconnect bluetooth device. Args: {"name":"str"}.',

    # PROGRAMS
    "installed_programs": 'List installed programs. Args: none.',
    "uninstall_program": 'Uninstall program by name. Args: {"name":"str"}.',
    "install_program": 'Install/launch installer. Args: {"installer_path":"str"}.',

    # APP CONTROL
    "list_running_apps": 'List running GUI apps. Args: none.',
    "use_app": 'Use app. Args: {"action":"focus|close|type|press|click|screenshot","app":"str","x":int,"y":int,"text":"str","key":"str"}',
    "ask_user": 'Ask the user a short clarifying question when truly needed. Args: {"question":"str","options":["a","b"] or empty}. The user reply comes back as the result.',

    # VISION
    "take_screenshot": 'Takes a screenshot. Args: {"path":"optional path"}. Returns image info.',
    "describe_screen": 'Takes a screenshot and asks the VISION MODEL to describe what is on screen (windows, text, buttons). Args: {"prompt":"optional question"}.',
    "find_on_screen": 'Find a UI element image on the screen. Args: {"image_path":"path to image","confidence":0.8}. Returns x,y.',
    "click_image": 'Find a UI element image on screen and CLICK it. Args: {"image_path":"path to image","confidence":0.8}. Returns click coords.',

    # SYSTEM CONTROLS (device settings)
    "get_brightness": 'Get current screen brightness 0-100. Args: none.',
    "set_brightness": 'Set screen brightness. Args: {"level":0..100}.',
    "get_volume": 'Get current master volume 0-100. Args: none.',
    "set_volume": 'Set master volume. Args: {"level":0..100}.',
    "mute": 'Mute audio. Args: none.',
    "unmute": 'Unmute audio (set to 50%). Args: none.',
    "bluetooth_radio": 'Turn the Bluetooth ADAPTER on/off (real radio). Args: {"on":true/false}. Requests admin.',
    "bluetooth_radio_state": 'Is the Bluetooth adapter on/off. Args: none.',
    "wifi_radio": 'Turn the Wi-Fi adapter on/off. Args: {"on":true/false}. Requests admin.',
    "airplane_mode": 'Turn airplane mode on/off (toggles Wi-Fi + Bluetooth). Args: {"on":true/false}. Requests admin.',
    "radio_state": 'Overall wifi/bluetooth/airplane state. Args: none.',
    "power_state": 'Lock or sleep the PC. Args: {"action":"lock|sleep"}.',
    "cpu_ram_usage": 'Current CPU % and RAM usage. Args: none.',

    # TABS & FOCUS
    "list_tabs": 'List tabs in ANY tabbed app (Chrome, Edge, Explorer, VS Code, Notepad++, etc.). Args: {"app_name":"chrome|msedge|explorer|Code|notepad++|..."}.' ,
    "focus_tab": 'Switch to a specific tab in a tabbed app by title. Args: {"app_name":"chrome|msedge|Code|...","tab_title":"partial tab name or URL"}.' ,
    "reveal_in_explorer": 'Reveal/focus a file or folder in Windows Explorer (selects it). Args: {"path":"C:\\...\\file"}.',
}


# ---------- TOOL IMPLEMENTATIONS ----------
def list_windows(): return [w["title"] for w in wc.list_windows()]
def get_screen_size():
    s = dc.get_screen_size()
    return {"width": s.width, "height": s.height}
def get_mouse_position():
    p = dc.get_mouse_position()
    return {"x": int(p.x), "y": int(p.y)}
def move_mouse(x, y): return dc.move_mouse(int(x), int(y)).success
def click(x, y): return dc.click(int(x), int(y)).success
def type_text(text): return dc.type_text(str(text)).success
def press_key(key): return dc.press_key(str(key)).success
def hotkey(key1, key2=None):
    if key2: return dc.hotkey(str(key1), str(key2)).success
    return dc.press_key(str(key1)).success
def open_url(url): return dc.open_url(str(url)).success
def launch_app(app): return dc.launch_app(str(app)).success
def focus_window(title):
    """Focus a window by title substring. Uses reliable Win32 foregrounding."""
    r = U.focus_window_win32(str(title))
    if r.get("success"):
        return {"focused": True, "window": r["window"]}
    # Fallback: pygetwindow
    for w in wc.list_windows():
        if str(title).lower() in w["title"].lower():
            return {"focused": wc.focus(w["title"]).success, "window": w["title"]}
    return {"focused": False, "error": f"No window matches '{title}'", **r}
def close_window(title):
    for w in wc.list_windows():
        if str(title).lower() in w["title"].lower():
            return wc.close(w["title"]).success
    return False
def process_running(name): return ProcessMonitor().is_running(str(name))

# ---------- SMART APP CONTROL IMPLEMENTATIONS ----------
def count_windows(filter=None):
    wins = wc.list_windows()
    if filter:
        f = str(filter).lower()
        wins = [w for w in wins if f in w["title"].lower()]
    return {"count": len(wins), "windows": [w["title"] for w in wins], "filter": filter}

def count_running_apps():
    pm = ProcessMonitor()
    procs = [p for p in pm.list_processes(limit=200) if p.name]
    gui_names = set(p.name for p in procs if p.name)
    return {"count": len(gui_names), "apps": sorted(gui_names)}

def focus_or_launch(app, window_title=None):
    """If app already running, focus its window. Otherwise launch it."""
    try:
        running = ProcessMonitor().is_running(str(app))
        if running:
            if window_title:
                for w in wc.list_windows():
                    if str(window_title).lower() in w["title"].lower():
                        ok = wc.focus(w["title"]).success
                        return {"status": "focused_existing", "app": app, "window": w["title"], "success": ok}
            for w in wc.list_windows():
                if str(app).lower() in w["title"].lower():
                    ok = wc.focus(w["title"]).success
                    return {"status": "focused_existing", "app": app, "window": w["title"], "success": ok}
            return {"status": "running_but_no_window", "app": app, "running": True}
        else:
            dc.launch_app(str(app))
            return {"status": "launched", "app": app, "success": True}
    except Exception as e:
        return {"error": str(e)}

def new_window(app, cmd_extra=None):
    """Open an ADDITIONAL window/instance of an app (fixes multiple tabs/reopen issue)."""
    try:
        import subprocess
        base = str(app)
        if cmd_extra:
            subprocess.Popen(f'start "" "{base}" {cmd_extra}', shell=True)
        else:
            subprocess.Popen(f'start "" "{base}"', shell=True)
        return {"success": True, "app": app, "extra_window_opened": True, "cmd_extra": cmd_extra}
    except Exception as e:
        return {"error": str(e)}

def open_in_app(path, app):
    """Open a file in a specific app/IDE."""
    return U.open_with(path, app)

def app_state(app_name):
    """Instances/windows of one app."""
    pm = ProcessMonitor()
    procs = pm.find_by_name(str(app_name))
    wins = [w["title"] for w in wc.list_windows() if str(app_name).lower() in w["title"].lower()]
    return {
        "app": app_name,
        "running_instances": [{"name": p.name, "pid": p.pid} for p in procs],
        "windows": wins,
        "window_count": len(wins),
    }

def clipboard_get(): return ClipboardManager().get_text()
def clipboard_set(text): return ClipboardManager().set_text(str(text)).success

def list_files(path=".", recursive=False): return U.list_files(path, recursive)
def create_file(path, content=""): return U.create_file(path, content)
def read_file(path): return U.read_file(path)
def create_folder(path): return U.create_folder(path)
def move_file(src, dst): return U.move_file(src, dst)
def copy_file(src, dst): return U.copy_file(src, dst)
def delete_path(path, recursive=False): return U.delete_path(path, recursive)
def rename_file(path, new_name): return U.rename_file(path, new_name)
def write_file(path, content): return U.write_file(path, content)

def storage_info(): return U.storage_info()
def current_time(): return U.current_time()
def system_info(): return U.system_info()

def network_info(): return U.network_info()
def network_speed(): return U.network_speed_test(measure_secs=1.5)
def ping(host="8.8.8.8"): return U.ping(host)

def bluetooth_devices(): return U.bluetooth_devices()
def bluetooth_connect(name): return U.bluetooth_connect(name)
def bluetooth_disconnect(name): return U.bluetooth_disconnect(name)

def installed_programs(): return U.installed_programs()
def uninstall_program(name): return U.uninstall_program(name)
def install_program(installer_path, silent_args=None):
    return U.install_program(installer_path, silent_args)

def list_running_apps(): return U.list_running_apps()
def use_app(action, app="", **kw): return U.use_app_ui(action, app=app, **kw)

# System controls (brightness / volume / power / radio) via real Windows APIs
def get_brightness(): return U.get_brightness()
def set_brightness(level): return U.set_brightness(level)
def get_volume(): return U.get_volume()
def set_volume(level): return U.set_volume(level)
def mute(): return U.mute()
def unmute(): return U.unmute()
def bluetooth_radio(on): return U.bluetooth_radio(on)
def bluetooth_radio_state(): return U.bluetooth_radio_state()
def wifi_radio(on): return U.wifi_radio(on)
def airplane_mode(on): return U.airplane_mode(on)
def radio_state(): return U.radio_state()
def power_state(action): return U.power_state(action)
def cpu_ram_usage(): return U.cpu_ram_usage()

# Tabs & focus enhancement (works for ALL tabbed apps, not just browsers)
def list_tabs(app_name): return U.list_tabs(app_name)
def focus_tab(app_name, tab_title): return U.focus_tab(app_name, tab_title)
def reveal_in_explorer(path): return U.reveal_in_explorer(path)

def ask_user(question, options=None):
    """Ask the user a quick clarifying question mid-task and get a reply, then continue."""
    options = options or []
    opts = ""
    if options:
        opts = "  [" + " / ".join(str(o) for o in options) + "]"
    ans = input(f"\n[JARVIS -> YOU] {question}{opts}\n[YOU -> JARVIS] ")
    return {"asked": question, "user_answer": ans.strip()}


# Vision: screenshot + describe (so Jarvis can "see" and understand UI)
def take_screenshot(path=None):
    r = U.take_screenshot(path)
    return r

def _save_screenshot_to_temp() -> str:
    """Take screenshot, save to temp path, return path."""
    import tempfile
    tmp = tempfile.mktemp(suffix=".png", prefix="jarvis_")
    r = U.take_screenshot(tmp)
    if r.get("success"):
        return tmp
    return None

def describe_screen(prompt=None):
    """Take a screenshot and ask the vision model what is on screen."""
    path = _save_screenshot_to_temp()
    if not path:
        return {"error": "screenshot failed"}
    try:
        desc = VISION_PROVIDER.vision(path, prompt or "Describe what is on this screen in detail: windows, text, buttons, positions.")
        return {"description": desc, "screenshot": path}
    except Exception as e:
        return {"error": f"vision failed: {e}", "screenshot": path}

def find_on_screen(image_path, confidence=0.8):
    """Find a UI element (button image) on the screen. Returns coords."""
    return U.find_on_screen(image_path, confidence)

def click_image(image_path, confidence=0.8):
    """Find a UI element on screen and physically click it."""
    return U.click_image(image_path, confidence)


TOOLS = {
    "list_windows": list_windows,
    "get_screen_size": get_screen_size,
    "get_mouse_position": get_mouse_position,
    "move_mouse": move_mouse,
    "click": click,
    "type_text": type_text,
    "press_key": press_key,
    "hotkey": hotkey,
    "open_url": open_url,
    "launch_app": launch_app,
    "focus_window": focus_window,
    "close_window": close_window,
    "process_running": process_running,
    "clipboard_get": clipboard_get,
    "clipboard_set": clipboard_set,
    "list_files": list_files,
    "create_file": create_file,
    "read_file": read_file,
    "create_folder": create_folder,
    "move_file": move_file,
    "copy_file": copy_file,
    "delete_path": delete_path,
    "rename_file": rename_file,
    "write_file": write_file,
    "storage_info": storage_info,
    "current_time": current_time,
    "system_info": system_info,
    "network_info": network_info,
    "network_speed": network_speed,
    "ping": ping,
    "bluetooth_devices": bluetooth_devices,
    "bluetooth_connect": bluetooth_connect,
    "bluetooth_disconnect": bluetooth_disconnect,
    "installed_programs": installed_programs,
    "uninstall_program": uninstall_program,
    "install_program": install_program,
    "list_running_apps": list_running_apps,
    "use_app": use_app,
    "ask_user": ask_user,
    "count_windows": count_windows,
    "count_running_apps": count_running_apps,
    "focus_or_launch": focus_or_launch,
    "new_window": new_window,
    "open_in_app": open_in_app,
    "app_state": app_state,
    "take_screenshot": take_screenshot,
    "describe_screen": describe_screen,
    "find_on_screen": find_on_screen,
    "click_image": click_image,
    "get_brightness": get_brightness,
    "set_brightness": set_brightness,
    "get_volume": get_volume,
    "set_volume": set_volume,
    "mute": mute,
    "unmute": unmute,
    "bluetooth_radio": bluetooth_radio,
    "bluetooth_radio_state": bluetooth_radio_state,
    "wifi_radio": wifi_radio,
    "airplane_mode": airplane_mode,
    "radio_state": radio_state,
    "power_state": power_state,
    "cpu_ram_usage": cpu_ram_usage,
    "list_tabs": list_tabs,
    "focus_tab": focus_tab,
    "reveal_in_explorer": reveal_in_explorer,
}

# ---------- SELF-KNOWLEDGE (auto-detected so the model never guesses paths) ----------
def _self_knowledge() -> str:
    import getpass as _getpass
    username = _getpass.getuser()
    home = str(Path.home())
    desktop = str(Path.home() / "Desktop")
    docs = str(Path.home() / "Documents")
    try:
        si = U.system_info()
        host = si.get("hostname", "unknown")
        os_ = si.get("os", "unknown")
        cpus = si.get("cpu_cores", "?")
        drives = U.storage_info().get("drives", [])
        free = drives[0].get("free_gb", "?") if drives else "?"
        total = drives[0].get("total_gb", "?") if drives else "?"
    except Exception:
        host = os_ = cpus = free = total = "unknown"
    return "\n".join([
        "=== YOUR ENVIRONMENT (facts you MUST use — never invent usernames or paths) ===",
        f"Current Windows user: '{username}'   Home: '{home}'",
        f"Desktop folder: '{desktop}'   Documents: '{docs}'",
        f"Hostname: '{host}'   OS: {os_}   CPU cores: {cpus}",
        f"Disk C: {free} GB free / {total} GB total",
        f"Active provider: {PROVIDER.provider_id}:{PROVIDER.model}",
        "If a task needs a file/folder location, ALWAYS use the real paths above.",
        "=============================================================================\n",
    ])


SYSTEM_PROMPT = (
    "You are JARVIS, a desktop automation agent that does what a real user does on Windows.\n"
            f"Active model provider: {PROVIDER.provider_id}/{PROVIDER.model}\n\n"
    + _self_knowledge()
    + "Given a task, choose tools to complete it. Respond ONLY valid JSON, no markdown.\n"
    "You may call these tools:\n"
    + json.dumps(TOOL_DOCS, indent=2)
    + "\n\nRules:\n"
    'Format: {"tool": "tool_name", "args": {...}, "then_wait": 1.0}\n'
    '"then_wait" = seconds to wait after action (default 1.0).\n'
    "Do multiple tools across multiple responses. Start with ONE action. Gather info first if needed.\n"
    "For reading a file's content, use read_file.\n"
    "Use ONLY tool names listed above. NEVER invent or guess a tool name.\n"
    "VISION IS OPTIONAL - only use take_screenshot/describe_screen when you must LOOK at the screen "
    "(clicking browser buttons, filling forms, verifying a page, finding an element). "
    "For opening/launching apps, creating/writing/deleting files, opening URLs, and system/network tasks, act DIRECTLY without vision.\n"
    "AFTER creating, writing, renaming, or moving any file/folder, reveal/focus it with reveal_in_explorer "
    "UNLESS the user explicitly said not to focus. After opening a file in an app, focus_that app window.\n"
    "If a tool fails, adapt: use a working tool or a real path from your environment, NEVER repeat the same failed action.\n"
    "Only use ask_user when genuinely ambiguous (e.g. which file/app the user means). Never ask about things you can detect yourself.\n"
    "If you are unsure which tool to use, respond with 'done' rather than guessing.\n"
    'When done respond: {"tool": "done", "args": {}, "then_wait": 0}\n'
)


def execute_action(action):
    tool = action.get("tool")
    args = action.get("args", {}) or {}
    if tool == "done":
        return "DONE", True
    if tool == "take_screenshot":
        r = take_screenshot(args.get("path"))
        return f"Screenshot: {json.dumps(r) if not isinstance(r, str) else r}", False
    if not isinstance(tool, str) or tool not in TOOLS:
        return f"Unknown tool: {tool}. Stick to the tools listed above.", False
    fn = TOOLS[tool]
    try:
        result = fn(**args)
    except TypeError:
        try:
            result = fn(*list(args.values()))
        except Exception as e:
            return f"Tool '{tool}' error: {e}", False
    except Exception as e:
        return f"Tool '{tool}' error: {e}", False
    return f"Tool '{tool}' result: {json.dumps(result, default=str, ensure_ascii=False) if not isinstance(result, (str, bool)) else result}", False


def parse_actions(response_text: str):
    """Robustly parse one or more JSON actions from model output."""
    response_text = response_text.strip().strip("`")
    if response_text.startswith("json"):
        response_text = response_text[4:].lstrip()
    try:
        parsed = json.loads(response_text)
        return parsed if isinstance(parsed, list) else [parsed]
    except json.JSONDecodeError:
        objects = re.findall(r'\{[^{}]*\}', response_text)
        actions = []
        for obj in objects:
            try:
                a = json.loads(obj)
                if isinstance(a, dict):
                    actions.append(a)
            except json.JSONDecodeError:
                continue
        return actions


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    goal = " ".join(sys.argv[1:])
    print(f"\n[GOAL] {goal}")
    print(f"[PROVIDER] {PROVIDER.provider_id}/{PROVIDER.model}")

    history = SYSTEM_PROMPT + f"\n\nUSER TASK: {goal}\n"

    max_steps = 20
    recent_actions: list[str] = []
    for step in range(max_steps):
        print(f"\n--- Step {step+1}: {PROVIDER.provider_id}/{PROVIDER.model} thinking... ---")
        try:
            raw = PROVIDER.chat(history)
        except Exception as e:
            print(f"[ERROR] Provider call failed: {e}")
            print("[HINT] Is Ollama running? Type 'ollama serve' in another tab.")
            break

        actions = parse_actions(raw)
        if not actions:
            print(f"[RAW] {raw[:300]}")
            history += "\nInvalid output. Respond with exactly one JSON object.\n"
            continue

        done = False
        for single in actions:
            if not isinstance(single, dict):
                continue
            tool_sig = f"{single.get('tool')}:{json.dumps(single.get('args', {}), sort_keys=True)}"
            recent_actions.append(tool_sig)

            # --- SELF-CORRECTION: break out of a repetition loop ---
            if len(recent_actions) >= 4 and len(set(recent_actions[-4:])) == 1:
                print(f"[SELF-CORRECT] Repeating same action {tool_sig} — redirecting.")
                history += (
                    f"\nYou repeated the same action ({single.get('tool')}) many times and it's not completing the task. "
                    "This action is NOT working. Choose a DIFFERENT tool or DIFFERENT arguments to make real progress, "
                    "or finish with 'done' if the task is actually complete.\n"
                )
                recent_actions.clear()
                break

            print(f"[ACTION] {single.get('tool')}({single.get('args', {})})")
            result, is_done = execute_action(single)
            print(f"[RESULT] {result}")
            history += f"\nExecuted: {json.dumps(single)}\nResult: {result}\n"
            if is_done:
                done = True
                break
            time.sleep(max(0.5, single.get("then_wait", 1.0)))

        if done:
            break
        history += "Continue.\n"

    print("\n" + "=" * 50)
    print(" TASK COMPLETED" if done else " Stopped at max steps")
    print("=" * 50)


if __name__ == "__main__":
    main()
