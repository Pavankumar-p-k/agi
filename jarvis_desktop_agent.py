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
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from jarvis_provider import get_provider

from core.desktop.controller import desktop_controller as dc
from core.desktop.safety import DesktopActionType
from core.desktop.window import window_controller as wc
from core.workspace.process_monitor import ProcessMonitor
from core.workspace.clipboard_manager import ClipboardManager
from core.desktop.user_actions import user_actions as U
from core.desktop.task_graph import TaskGraph, TaskGraphError

# ---------- ACTIVE PROVIDER ----------
# Use the unified top-level provider (jarvis_provider). Role-chosen via CHAT_MODEL in .env.
PROVIDER = get_provider("chat")
REASONING_PROVIDER = get_provider("reasoning")
VISION_PROVIDER = get_provider("vision")

INVOCATION_LOG = ROOT / "logs" / "tool_invocations.jsonl"

def _log_invocation(tool: str, args: dict, status: str):
    """Append one tool invocation to logs/tool_invocations.jsonl so usage can be audited."""
    try:
        evt = {"t": time.time(), "tool": str(tool), "args": {k: str(v)[:200] for k, v in (args or {}).items()}, "status": status}
        INVOCATION_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(INVOCATION_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(evt) + "\n")
    except Exception:
        pass


# ---------- TOOL HEALTH FEEDBACK LOOP ----------
HEALTH_WINDOW = 200  # latest N invocations used for the summary
TOOL_HEALTH_FILE = ROOT / "data" / "tool_health.json"
TASK_LAUNCH_COUNTS: dict[str, int] = {}
MAX_INSTANCES_PER_APP = 2
TASK_BROWSER_TABS_OPENED = 0
MAX_BROWSER_TABS_PER_TASK = 5
MAX_REPEATED_ACTIONS = 3
_LAST_ACTION_SIGNATURE = ""
_ACTION_REPEAT_COUNT = 0


def _action_signature(tool: Any, args: dict) -> str:
    try:
        return f"{tool}:{json.dumps(args or {}, sort_keys=True, default=str)}"
    except Exception:
        return f"{tool}:{str(args)}"


def _repeat_limit_message(tool: str, args: dict) -> str | None:
    """Bound identical retries so a failed coordinate/UIA action cannot loop forever."""
    global _LAST_ACTION_SIGNATURE, _ACTION_REPEAT_COUNT
    signature = _action_signature(tool, args)
    if signature == _LAST_ACTION_SIGNATURE:
        _ACTION_REPEAT_COUNT += 1
    else:
        _LAST_ACTION_SIGNATURE = signature
        _ACTION_REPEAT_COUNT = 1
    if _ACTION_REPEAT_COUNT > MAX_REPEATED_ACTIONS:
        return (
            f"Tool '{tool}' blocked: identical action repeated more than "
            f"{MAX_REPEATED_ACTIONS} times. Change the target or verify the UI before retrying."
        )
    return None


def _reset_action_limits() -> None:
    global _LAST_ACTION_SIGNATURE, _ACTION_REPEAT_COUNT
    _LAST_ACTION_SIGNATURE = ""
    _ACTION_REPEAT_COUNT = 0

def _aggregate_health(lines: list[str]) -> dict[str, dict[str, int]]:
    stats: dict[str, dict[str, int]] = {}
    for ln in lines:
        try:
            e = json.loads(ln)
        except Exception:
            continue
        t = e.get("tool", "?")
        s = e.get("status", "?")
        d = stats.setdefault(t, {})
        d[s] = d.get(s, 0) + 1
    return stats

def _health_block(stats: dict[str, dict[str, int]], label: str) -> str:
    if not stats:
        return "[TOOL HEALTH] no invocation data yet."
    total = sum(sum(v.values()) for v in stats.values())
    # "worst" = genuine defects only (failed + error). blocked_by_user is NOT a tool
    # defect - it is the consent gate working (the user declined), so it must not teach
    # the planner to avoid fine tools. It is surfaced separately as a boundary signal.
    def fail_score(kv):
        t, ds = kv
        return ds.get("failed", 0) + ds.get("error", 0)
    broken = sorted([kv for kv in stats.items() if fail_score(kv) > 0],
                    key=lambda kv: (-fail_score(kv), -kv[1].get("ok", 0)))[:5]
    denied = sorted([kv for kv in stats.items() if kv[1].get("blocked_by_user", 0) > 0],
                    key=lambda kv: -kv[1].get("blocked_by_user", 0))[:3]
    parts = []
    for tool, ds in broken:
        parts.append(f"{tool}(ok={ds.get('ok', 0)},fail={ds.get('failed', 0)},err={ds.get('error', 0)})")
    bparts = []
    for tool, ds in denied:
        bparts.append(f"{tool}(denied={ds.get('blocked_by_user', 0)})")
    head = f"[TOOL HEALTH ({label}, {total} invocations)]"
    if parts:
        head += f" unreliable: {' | '.join(parts)}"
    if bparts:
        head += f" | user-denied (consent working, not a defect): {' | '.join(bparts)}"
    if not parts and not bparts:
        head += " all tools healthy."
    return (head + " | Avoid tools with high fail/error rates; prefer alternatives."
            if parts else head)

def _tool_health(refresh: bool = True) -> str:
    """Aggregate recent invocation-log statuses per tool and return a compact health block.
    Persists the summary so later runs can inject it even without new invocations."""
    try:
        lines = []
        if INVOCATION_LOG.exists():
            lines = INVOCATION_LOG.read_text(encoding="utf-8").splitlines()[-HEALTH_WINDOW:]
        stats = _aggregate_health(lines)
        if refresh:
            try:
                TOOL_HEALTH_FILE.parent.mkdir(parents=True, exist_ok=True)
                TOOL_HEALTH_FILE.write_text(json.dumps(stats, indent=1), encoding="utf-8")
            except Exception:
                pass
        return _health_block(stats, "live")
    except Exception:
        return "[TOOL HEALTH] health aggregation unavailable."

def _load_tool_health_for_prompt() -> str:
    """Return persisted health block for prompt injection (works even after a restart)."""
    try:
        if TOOL_HEALTH_FILE.exists():
            stats = json.loads(TOOL_HEALTH_FILE.read_text(encoding="utf-8"))
            if stats:
                return _health_block(stats, "persisted")
    except Exception:
        pass
    return ""


# ---------- TOOL DOCS ----------
TOOL_DOCS = {
    # Core desktop
    "list_windows": 'Lists open window titles. Args: {"filter":"optional substring, e.g. chrome"}. Returns count + names.',
    "get_screen_size": 'Gets screen width and height. Args: none.',
    "get_mouse_position": 'Gets current mouse x,y. Args: none.',
    "move_mouse": 'Moves mouse. Args: {"x":int,"y":int}.',
    "drag": 'Drags with the primary mouse button. Args: {"from_x":int,"from_y":int,"to_x":int,"to_y":int,"duration":float}.',
    "paint_draw_shapes": 'In the existing Paint window, maximize it, select Pencil via UI Automation, and draw a circle and square. Args: none.',
    "paint_select_control": 'Select a named Paint control via UI Automation. Args: {"name":"Pencil|Fill|Oval|Rectangle|..."}.',
    "paint_draw_path": 'Draw a model-planned path in Paint. Prefer normalized points [0..1,0..1] relative to paint_canvas_region. Args: {"points":[[x,y],...],"duration":0.12}.',
    "paint_canvas_region": 'Detect the visible Paint canvas. Args: none.',
    "paint_select_color": 'Select a named Paint palette color. Args: {"color":"blue|green|red|yellow|brown|white|..."}.',
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
    "focus_or_launch": 'If app is already running, focus it; otherwise launch it. Args: {"app":"notepad|chrome|code", "window_title":"optional partial title"}. Fixes duplicate reopening.',
    "new_window": 'Opens a NEW additional window/instance of an app even if already running. Args: {"app":"notepad|chrome", "cmd_extra":"optional e.g. --new-window"}.',
    "app_state": 'Show instances/windows of one app. Args: {"app_name":"chrome|notepad|code"}.',

    # FILE SYSTEM
    "list_files": 'List files/folders. Args: {"path":"str","recursive":bool}. Recursive results are bounded and include status/limits (depth, entries, symlinks, inaccessible).',
    "monitor_downloads": 'Monitor Downloads for newly added files. Args: {"duration": seconds, max 60}.',
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
    "system_info": 'OS, CPU, hostname, arch, boot time, and uptime. Args: none.',

    # NETWORK
    "network_info": 'Network interfaces, IPs, link speed. Args: none.',
    "network_speed": 'Measure current download/upload Mbps. Args: none.',
    "ping": 'Ping a host. Args: {"host":"google.com","count":1..10}.',

    # BLUETOOTH
    "bluetooth_devices": 'List bluetooth devices. Args: none.',
    "bluetooth_connect": 'Connect bluetooth device. Args: {"name":"str"}.',
    "bluetooth_disconnect": 'Disconnect bluetooth device. Args: {"name":"str"}.',

    # PROGRAMS
    "installed_programs": 'List installed programs. Args: none.',
    "uninstall_program": 'Uninstall program by name. Args: {"name":"str"}.',
    "install_program": 'Install/launch installer. Args: {"installer_path":"str"}.',

    # APP CONTROL
    "list_running_apps": 'List running GUI apps. Args: none. Returns count + names.',
    "use_app": 'Use app. Args: {"action":"focus|close|type|press|click|screenshot","app":"str","x":int,"y":int,"text":"str","key":"str"}',
    "ask_user": 'Ask the user a short clarifying question when truly needed. Args: {"question":"str","options":["a","b"] or empty}. The user reply comes back as the result.',

    # VISION (verification ONLY - descriptions, never click coordinates)
    "take_screenshot": 'Takes a screenshot. Args: {"path":"optional path"}. Returns image info.',
    "describe_screen": 'Takes a screenshot and asks the VISION MODEL to describe what is on screen (windows, text, buttons). Args: {"prompt":"optional question"}. Use ONLY to verify/understand the screen, NEVER to get click coordinates.',
    "find_on_screen": 'Find a UI element image on the screen. Args: {"image_path":"path to image","confidence":0.8}. Returns x,y. Uses template matching (reliable).',
    "click_image": 'Find a UI element image on screen and CLICK it. Args: {"image_path":"path to image","confidence":0.8}. Returns click coords. Uses template matching (reliable).',
    "crop_image": 'Crop a region from a screenshot and SAVE as a template image, so it can be found/clicked. Args: {"image_path":"screenshot.png","x":0,"y":0,"w":100,"h":40,"out_path":"template.png"}.',

    # UIA FORM ACCESS (semantic, coordinate-free) - prefer over vision clicks
    "list_form_fields": 'List editable input fields in an app window via UI Automation (name + pixel position). Args: {"app_name":"chrome|notepad|..."}. Use to find where to type without guessing coordinates.',
    "list_ui_controls": 'Inspect all native UI Automation controls, including custom app controls. Args: {"app_name":"WhatsApp"}.',
    "select_autocomplete_suggestion": 'Select one semantic UIA autocomplete suggestion and verify its actual value. Args: {"app_name":"chrome|...","suggestion":"exact visible value","control_label":"optional field label"}. Refuses ambiguity.',
    "set_form_field_value": 'Set a UIA ValuePattern field and verify the actual value read back. Args: {"app_name":"...","field_label":"...","value":"..."}.',
    "whatsapp_prepare_draft": 'Prepare "Hi" in the verified native WhatsApp recent chat without sending. Args: {"text":"Hi"}. Fails closed if recipient/composer cannot be verified.',
    "whatsapp_focus_probe": 'Probe native WhatsApp keyboard focus without typing or sending. Args: {"steps":1..8}.',
    "click_form_field": 'Click a form control found via UI Automation. Args: {"app_name":"optional","index":"explicit integer or omit","field_label":"optional partial label"}. Refuses ambiguous or stale matches.',
    "run_graph": 'Execute a dependency-aware multi-step action graph deterministically. Args: {"graph": <dict or JSON string of {"id","goal","steps":[{id,desc,tool,args,depends_on,wait,rollback?,rollback_capture?,verify?}]}>}. Each step runs through the same consent gate + self-healing layer as normal tools; destructive tools inside the graph STILL require user confirmation. On any failure or consent-block, completed steps roll back in reverse order. Use for multi-step tasks that must not leave partial state (e.g. create->modify->cleanup).',

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
    "open_file": 'Open a file in its DEFAULT app, or a specific app. Args: {"path":"C:\\...\\file.txt","app":"optional, e.g. notepad|code|chrome"}.',
    "browse_to": 'Open a URL in Chrome and FOCUS that tab so keyboard/vision input lands in the page. Args: {"url":"https://...","new_tab":bool(default true)}. Use this for web pages you will interact with.',
}


# ---------- TOOL IMPLEMENTATIONS ----------
def list_windows(filter=None):
    wins = wc.list_windows()
    if filter:
        f = str(filter).lower()
        wins = [w for w in wins if f in w["title"].lower()]
    return {"count": len(wins), "windows": [w["title"] for w in wins], "filter": filter}
def get_screen_size():
    s = dc.get_screen_size()
    return {"width": s.width, "height": s.height}
def get_mouse_position():
    p = dc.get_mouse_position()
    return {"x": int(p.x), "y": int(p.y)}
def move_mouse(x, y): return dc.move_mouse(int(x), int(y)).success
def drag(from_x, from_y, to_x, to_y, duration=0.5):
    return dc.drag(int(from_x), int(from_y), int(to_x), int(to_y), float(duration)).success


def paint_draw_shapes():
    """Focus/maximize Paint, select Pencil through UIA, and draw test shapes."""
    paint_titles = {
        str(record.get("Title", "")).lower()
        for record in U.list_running_apps().get("apps", [])
        if str(record.get("Name", "")).lower().replace(".exe", "") == "mspaint"
    }
    target = next((w["title"] for w in wc.list_windows()
                   if str(w["title"]).lower() in paint_titles), None)
    if not target:
        return {"success": False, "error": "No existing Paint window found"}
    focused = U.focus_window_win32(target)
    if not focused.get("success"):
        return {"success": False, "error": focused.get("error", "Unable to focus Paint")}
    maximized = wc.maximize(target)
    if not maximized.success:
        return {"success": False, "error": maximized.error or "Unable to maximize Paint"}
    time.sleep(0.5)

    controls = U.list_form_fields("paint")
    pencil = next((f for f in controls.get("fields", [])
                   if "pencil" in str(f.get("name", "")).lower()), None)
    if not pencil:
        return {"success": False, "error": "Paint Pencil tool was not found by UI Automation"}
    clicked = dc.click(int(pencil["x"] + pencil["w"] / 2), int(pencil["y"] + pencil["h"] / 2))
    if not clicked.success:
        return {"success": False, "error": clicked.error}

    # Maximized Paint's canvas is below the ribbon and inside the window margins.
    width, height = dc.get_screen_size()
    left, top = max(80, width // 5), 350
    radius = min(150, max(80, width // 12))
    cx, cy = left + radius, top + radius
    import math
    circle = [
        (int(cx + radius * math.cos(i * 2 * math.pi / 32)),
         int(cy + radius * math.sin(i * 2 * math.pi / 32)))
        for i in range(33)
    ]
    square_left, square_top = left + 2 * radius + 100, top
    square_size = radius * 2
    square = [
        (square_left, square_top),
        (square_left + square_size, square_top),
        (square_left + square_size, square_top + square_size),
        (square_left, square_top + square_size),
        (square_left, square_top),
    ]
    for points in (circle, square):
        for start, end in zip(points, points[1:]):
            result = dc.drag(*start, *end, duration=0.12)
            if not result.success:
                return {"success": False, "error": result.error}
    return {
        "success": True,
        "window": target,
        "tool": "Pencil",
        "shapes": ["circle", "square"],
        "canvas_region": {"x": left, "y": top, "width": width - left - 80, "height": height - top - 80},
    }


def paint_select_control(name):
    """Select a named Paint control through UI Automation."""
    fields = U.list_form_fields("paint").get("fields", [])
    requested = str(name).strip().lower()
    exact = [f for f in fields if str(f.get("name", "")).strip().lower() == requested]
    matches = exact or [f for f in fields if requested in str(f.get("name", "")).lower()]
    if len(matches) != 1:
        return {"success": False, "error": f"Expected one Paint control matching '{name}', found {len(matches)}"}
    target = matches[0]
    result = dc.click(int(target["x"] + target["w"] / 2), int(target["y"] + target["h"] / 2))
    return {"success": result.success, "control": target.get("name"), "error": result.error}


def paint_draw_path(points, duration=0.12):
    """Draw a model-planned freehand path in Paint with safe, bounded segments."""
    if not isinstance(points, list) or len(points) < 2:
        return {"success": False, "error": "points must contain at least two [x,y] pairs"}
    normalized = []
    canvas = paint_canvas_region()
    if not canvas.get("success"):
        return canvas
    left, top, right, bottom = (canvas["x"], canvas["y"],
                                canvas["x"] + canvas["width"],
                                canvas["y"] + canvas["height"])
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            return {"success": False, "error": "each point must be [x,y]"}
        x, y = float(point[0]), float(point[1])
        if 0 <= x <= 1 and 0 <= y <= 1:
            x = left + x * canvas["width"]
            y = top + y * canvas["height"]
        x, y = int(x), int(y)
        if not (left <= x <= right and top <= y <= bottom):
            return {"success": False, "error": "path point is outside the detected Paint canvas",
                    "canvas_region": canvas}
        normalized.append((x, y))
    if len(set(normalized)) < 2:
        return {"success": False, "error": "path must contain at least two distinct points"}
    for start, end in zip(normalized, normalized[1:]):
        distance = ((end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2) ** 0.5
        safe_speed = min(dc.safety.max_mouse_speed_px_per_sec,
                         dc.safety.config.max_mouse_speed_px_per_sec)
        safe_duration = distance / safe_speed + 0.02 if safe_speed > 0 else 0.12
        result = dc.drag(*start, *end, duration=max(0.12, float(duration), safe_duration))
        if not result.success:
            return {"success": False, "error": result.error, "from": start, "to": end}
    return {"success": True, "points": len(normalized)}


def paint_canvas_region():
    """Detect the largest bright canvas rectangle in the focused Paint window."""
    import numpy as np
    from PIL import ImageGrab
    image = np.asarray(ImageGrab.grab().convert("RGB"))
    bright = np.all(image > 245, axis=2)
    rows = np.where(bright.sum(axis=1) > image.shape[1] * 0.25)[0]
    cols = np.where(bright.sum(axis=0) > image.shape[0] * 0.25)[0]
    if len(rows) < 2 or len(cols) < 2:
        return {"success": False, "error": "Unable to detect a visible Paint canvas"}
    x, y = int(cols[0]), int(rows[0])
    right, bottom = int(cols[-1]), int(rows[-1])
    if right - x < 200 or bottom - y < 150:
        return {"success": False, "error": "Detected bright region is not a usable Paint canvas"}
    return {"success": True, "x": x, "y": y, "width": right - x, "height": bottom - y}


def paint_select_color(color):
    """Choose a named Paint palette color without encoding scene-specific artwork."""
    palette = {
        "black": (988, 105), "gray": (1018, 105), "red": (1048, 105),
        "orange": (1108, 105), "yellow": (1138, 105), "green": (1168, 105),
        "blue": (1198, 105), "purple": (1228, 105), "white": (988, 135),
        "light blue": (1198, 135), "brown": (1048, 135),
    }
    key = str(color).lower().strip()
    if key not in palette:
        return {"success": False, "error": f"Unsupported Paint palette color '{color}'"}
    result = dc.click(*palette[key])
    return {"success": result.success, "color": key, "error": result.error}


def click(x, y): return dc.click(int(x), int(y)).success
def type_text(text): return dc.type_text(str(text)).success
def press_key(key): return dc.press_key(str(key)).success
def hotkey(key1, key2=None):
    if key2: return dc.hotkey(str(key1), str(key2)).success
    return dc.press_key(str(key1)).success
def open_url(url): return dc.open_url(str(url)).success
APP_WINDOW_HINTS = {
    "notepad": ("notepad",),
    "calculator": ("calculator",),
    "calc": ("calculator",),
    "chrome": ("chrome", "google chrome"),
    "msedge": ("edge", "microsoft edge"),
    "explorer": ("file explorer", "explorer"),
    "spotify": ("spotify",),
    "paint": ("paint",),
    "powershell": ("powershell", "windows powershell"),
}


def _app_matches_window(app: str, title: str) -> bool:
    key = str(app).lower().strip().replace(".exe", "")
    haystack = str(title).lower()
    if key == "paint":
        return haystack.endswith(" - paint") or haystack in {"paint", "untitled - paint"}
    hints = APP_WINDOW_HINTS.get(key, (key,))
    return any(hint in haystack for hint in hints)


def _running_app_matches(app: str, record: dict) -> bool:
    """Match arbitrary installed apps by process name or visible window title."""
    key = str(app).lower().strip().replace(".exe", "")
    process = str(record.get("Name", "")).lower().replace(".exe", "")
    title = str(record.get("Title", "")).lower()
    if _app_matches_window(key, title):
        return True
    if process == key or key in process:
        return True
    # Natural-language app names often correspond to a distinctive title.
    words = [word for word in key.replace("-", " ").replace("_", " ").split() if len(word) > 2]
    return bool(words) and all(word in title for word in words)


def _start_menu_launch(app: str) -> dict:
    """Launch an arbitrary installed app through Windows Search."""
    try:
        dc.hotkey("win")
        time.sleep(0.35)
        dc.type_text(str(app), interval=0.02)
        time.sleep(0.5)
        dc.press_key("enter")
        return {"success": True, "method": "start_menu_search", "app": app}
    except Exception as exc:
        return {"success": False, "error": str(exc), "app": app}


def launch_app(app):
    """Focus an existing app instance; launch only when no instance is available."""
    name = str(app).strip()
    running = bool(U._app_pids(name)) or ProcessMonitor().is_running(name)
    windows = wc.list_windows()
    running_records = U.list_running_apps().get("apps", [])
    candidates = [
        w for w in windows
        if _app_matches_window(name, w["title"])
        or any(
            str(record.get("Title", "")).lower() == str(w["title"]).lower()
            and _running_app_matches(name, record)
            for record in running_records
        )
    ]
    if candidates:
        focused = U.focus_window_win32(candidates[0]["title"])
        return {
            "success": bool(focused.get("success")),
            "action": "focused_existing",
            "app": name,
            "window": candidates[0]["title"],
            "error": focused.get("error", ""),
        }
    if running:
        return {
            "success": True,
            "action": "already_running_no_visible_window",
            "app": name,
        }
    launch_name = _resolve_app(name) if name.lower().replace(".exe", "") == "paint" else name
    result = dc.launch_app(launch_name)
    if not result.success:
        started = _start_menu_launch(name)
        if started["success"]:
            return {
                "success": True,
                "action": "launched",
                "app": name,
                "method": started["method"],
                "error": "",
            }
    return {
        "success": result.success,
        "action": "launched",
        "app": name,
        "error": result.error,
    }
def focus_window(title):
    """Focus a window by title substring. Uses reliable Win32 foregrounding."""
    if str(title).lower().strip() in {"paint", "mspaint", "mspaint.exe"}:
        paint_titles = [
            str(record.get("Title", ""))
            for record in U.list_running_apps().get("apps", [])
            if str(record.get("Name", "")).lower().replace(".exe", "") == "mspaint"
            and record.get("Title")
        ]
        if not paint_titles:
            return {"focused": False, "error": "Microsoft Paint is not running"}
        title = paint_titles[0]
    decision = dc.safety.check(DesktopActionType.WINDOW_FOCUS, {"window_title": title})
    if not decision.allowed:
        return {"focused": False, "error": decision.reason}
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
def focus_or_launch(app, window_title=None):
    """If app already running, focus its window. Otherwise launch it."""
    try:
        running = bool(U._app_pids(str(app))) or ProcessMonitor().is_running(str(app))
        if running:
            if window_title:
                for w in wc.list_windows():
                    if str(window_title).lower() in w["title"].lower():
                        focused = U.focus_window_win32(w["title"])
                        return {"status": "focused_existing", "app": app, "window": w["title"],
                                "success": bool(focused.get("success")), "launched": False}
            running_records = U.list_running_apps().get("apps", [])
            for w in wc.list_windows():
                if _app_matches_window(str(app), w["title"]) or any(
                    str(record.get("Title", "")).lower() == str(w["title"]).lower()
                    and _running_app_matches(str(app), record)
                    for record in running_records
                ):
                    focused = U.focus_window_win32(w["title"])
                    return {"status": "focused_existing", "app": app, "window": w["title"],
                            "success": bool(focused.get("success")), "launched": False}
            return {"status": "running_but_no_window", "app": app, "running": True,
                    "success": True, "launched": False}
        else:
            result = launch_app(str(app))
            return {"status": "launched", "app": app, **result}
    except Exception as e:
        return {"error": str(e)}

def new_window(app, cmd_extra=None):
    """Open an ADDITIONAL window/instance of an app (fixes multiple tabs/reopen issue)."""
    try:
        import shlex
        import subprocess
        base = str(app)
        extra = shlex.split(str(cmd_extra), posix=True) if cmd_extra else []
        if cmd_extra:
            subprocess.Popen([_resolve_app(base), *extra], shell=False)
        else:
            subprocess.Popen([_resolve_app(base)], shell=False)
        return {"success": True, "app": app, "extra_window_opened": True, "cmd_extra": cmd_extra}
    except Exception as e:
        return {"error": str(e)}

def _resolve_app(app):
    import os
    import shutil
    resolved = shutil.which(str(app))
    if resolved:
        return resolved
    if os.name == "nt" and str(app).lower() in {"chrome", "chrome.exe"}:
        for path in (
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        ):
            if os.path.exists(path):
                return path
    if os.name == "nt" and str(app).lower().replace(".exe", "") == "paint":
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        paint_path = os.path.join(system_root, "System32", "mspaint.exe")
        if os.path.exists(paint_path):
            return paint_path
    return str(app)

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
def monitor_downloads(duration=10):
    """Poll Downloads for newly appearing paths during a bounded interval."""
    import time as _time
    path = str(Path.home() / "Downloads")
    before_result = U.list_files(path, recursive=False)
    before_entries = before_result.get("entries", []) if isinstance(before_result, dict) else before_result
    before = {item["path"] for item in before_entries if isinstance(item, dict) and "path" in item}
    _time.sleep(max(0.0, min(float(duration), 60.0)))
    after_result = U.list_files(path, recursive=False)
    after = after_result.get("entries", []) if isinstance(after_result, dict) else after_result
    added = [item for item in after if isinstance(item, dict) and item.get("path") not in before]
    return {"success": bool(after_result.get("success", True)) if isinstance(after_result, dict) else True,
            "path": path, "duration_seconds": duration, "new_files": added,
            "scan_status": after_result.get("status", "ok") if isinstance(after_result, dict) else "ok"}
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
def ping(host="8.8.8.8", count=1): return U.ping(host, count)

def bluetooth_devices(): return U.bluetooth_devices()
def bluetooth_connect(name): return U.bluetooth_connect(name)
def bluetooth_disconnect(name): return U.bluetooth_disconnect(name)

def installed_programs(): return U.installed_programs()
def uninstall_program(name): return U.uninstall_program(name)
def install_program(installer_path, silent_args=None):
    return U.install_program(installer_path, silent_args)

def list_running_apps():
    r = U.list_running_apps()
    if isinstance(r, dict) and r.get("apps"):
        r["count"] = len(r["apps"])
    return r
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
def open_file(path, app=None): return U.open_with(path, app)

def browse_to(url, new_tab=True):
    """Reuse a matching tab or navigate an existing Chrome window before launching."""
    global TASK_BROWSER_TABS_OPENED
    import re as _re, subprocess as _sp
    import shutil as _shutil
    host = _re.sub(r"^https?://(www\.)?", "", str(url)).split("/")[0].split(":")[0] or "chrome"
    existing = U.focus_tab("chrome", host)
    if existing.get("success"):
        return {"success": True, "url": url, "focused_tab": host, "reused": True,
                "window": existing.get("window")}

    chrome_running = bool(U._app_pids("chrome"))
    if chrome_running and new_tab:
        if TASK_BROWSER_TABS_OPENED >= MAX_BROWSER_TABS_PER_TASK:
            return {
                "success": False,
                "url": url,
                "error": f"Browser tab limit reached for this task (max {MAX_BROWSER_TABS_PER_TASK}).",
                "reused": False,
            }
        focused = U.focus_window_win32("Chrome")
        if not focused.get("success"):
            focused = U.focus_window_win32("Google Chrome")
        if focused.get("success"):
            dc.hotkey("ctrl", "t")
            dc.type_text(str(url), interval=0.01)
            dc.press_key("enter")
            TASK_BROWSER_TABS_OPENED += 1
            time.sleep(3)
            focused_tab = U.focus_tab("chrome", host)
            return {
                "success": bool(focused_tab.get("success") or focused.get("success")),
                "url": url,
                "focused_tab": host,
                "reused": False,
                "opened_new_tab": True,
                "window": focused.get("window"),
            }
    if chrome_running and not new_tab:
        focused = U.focus_window_win32("Chrome")
        if not focused.get("success"):
            focused = U.focus_window_win32("Google Chrome")
        if focused.get("success"):
            dc.hotkey("ctrl", "l")
            dc.type_text(str(url), interval=0.01)
            dc.press_key("enter")
            time.sleep(3)
            return {
                "success": True,
                "url": url,
                "focused_tab": host,
                "reused": False,
                "opened_new_tab": False,
                "window": focused.get("window"),
            }

    chrome = _shutil.which("chrome") or _shutil.which("chrome.exe")
    launched = False
    if chrome or _resolve_app("chrome") != "chrome":
        chrome = chrome or _resolve_app("chrome")
        _sp.Popen([chrome, str(url)], shell=False)
        launched = True
    else:
        import webbrowser
        launched = bool(webbrowser.open(str(url), new=0 if not new_tab else 1))
    if not launched:
        return {"success": False, "url": url, "error": "Unable to open or reuse browser"}
    TASK_BROWSER_TABS_OPENED += 1
    time.sleep(3)
    focused = U.focus_tab("chrome", host)
    if not focused.get("success"):
        focused = U.focus_tab("chrome", url)
    if not focused.get("success"):
        focused = U.focus_window_win32(host)
    if not focused.get("success"):
        for window_hint in ("Google Chrome", "Chrome"):
            focused = U.focus_window_win32(window_hint)
            if focused.get("success"):
                break
    # ensure the matching window is actually foreground before typing
    time.sleep(0.5)
    return {"success": bool(focused.get("success")), "url": url, "focused_tab": host,
            "error": "" if focused.get("success") else focused.get("error", "Unable to focus tab")}

def ask_user(question, options=None):
    """Ask the user a quick clarifying question mid-task and get a reply, then continue."""
    options = options or []
    opts = ""
    if options:
        opts = "  [" + " / ".join(str(o) for o in options) + "]"
    try:
        ans = input(f"\n[JARVIS -> YOU] {question}{opts}\n[YOU -> JARVIS] ")
    except EOFError:
        return {
            "success": False,
            "asked": question,
            "error": "Interactive input is unavailable; do not retry ask_user in this session.",
        }
    return {"success": True, "asked": question, "user_answer": ans.strip()}


# Vision: screenshot + describe (so Jarvis can "see" and understand UI)
def take_screenshot(path=None):
    r = U.take_screenshot(path)
    return r

def _save_screenshot_to_temp() -> str:
    """Take screenshot, save to temp path, return path."""
    import tempfile
    handle = tempfile.NamedTemporaryFile(suffix=".png", prefix="jarvis_", delete=False)
    tmp = handle.name
    handle.close()
    r = U.take_screenshot(tmp)
    if r.get("success"):
        return tmp
    try:
        os.unlink(tmp)
    except OSError:
        pass
    return None

def describe_screen(prompt=None):
    """Take a screenshot and ask the vision model what is on screen."""
    decision = dc.safety.check(DesktopActionType.SCREEN_CAPTURE)
    if not decision.allowed:
        return {"error": decision.reason}
    path = _save_screenshot_to_temp()
    if not path:
        return {"error": "screenshot failed"}
    try:
        desc = VISION_PROVIDER.vision(path, prompt or "Describe what is on this screen in detail: windows, text, buttons, positions.")
        return {"description": desc}
    except Exception as e:
        return {"error": f"vision failed: {e}", "screenshot": path}
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass

def find_on_screen(image_path, confidence=0.8):
    """Find a UI element (button image) on the screen. Returns coords."""
    decision = dc.safety.check(DesktopActionType.SCREEN_CAPTURE)
    if not decision.allowed:
        return {"found": False, "error": decision.reason}
    return U.find_on_screen(image_path, confidence)

def click_image(image_path, confidence=0.8):
    """Find a UI element on screen and physically click it."""
    decision = dc.safety.check(DesktopActionType.SCREEN_CAPTURE)
    if not decision.allowed:
        return {"success": False, "error": decision.reason}
    return U.click_image(image_path, confidence)

def crop_image(image_path, x, y, w, h, out_path):
    """Crop a region of a screenshot into a template image that find_on_screen/click_image can match.
    Args: {"image_path":"screenshot.png","x":0,"y":0,"w":100,"h":40,"out_path":"template.png"}."""
    return U.crop_image(image_path, x, y, w, h, out_path)

def list_form_fields(app_name=None):
    """Discover interactive form controls (Edit/ComboBox/Radio/CheckBox/Button) in an app
    window via UI Automation. Self-healing: if live UIA is empty it returns the cached
    element map (from_cache=true) so typing/clicks still work after UI drift."""
    return U.list_form_fields(app_name)

def list_ui_controls(app_name):
    return U.list_ui_controls(str(app_name))


def whatsapp_focus_probe(steps=6):
    """Probe native WhatsApp focus navigation without typing or sending."""
    if not U._app_pids("whatsapp"):
        return {"success": False, "status": "blocked", "error": "Native WhatsApp is not running"}
    focused = U.focus_window_win32("WhatsApp")
    if not focused.get("success"):
        return {"success": False, "status": "blocked", "error": focused.get("error", "Cannot focus WhatsApp")}
    count = max(1, min(int(steps), 8))
    observations = []
    for key in ["tab"] * count:
        result = dc.press_key(key)
        if not result.success:
            return {"success": False, "status": "blocked", "error": result.error, "observations": observations}
        time.sleep(0.15)
        observations.append(U.focused_ui_control("whatsapp"))
    return {
        "success": True,
        "status": "probe_complete",
        "typed": False,
        "sent": False,
        "observations": observations,
        "next_step": "Use screenshot and observations to verify recipient and composer before typing.",
    }


def whatsapp_prepare_draft(text="Hi"):
    """Prepare a native WhatsApp draft only after the composer is verifiable."""
    if str(text) != "Hi":
        return {"success": False, "error": "This guarded workflow only prepares the requested 'Hi' draft"}
    pids = U._app_pids("whatsapp")
    if not pids:
        return {"success": False, "error": "Native WhatsApp process WhatsApp.Root is not running"}
    records = U.list_running_apps().get("apps", [])
    native = [r for r in records if int(r.get("PID", -1)) in pids
              and str(r.get("Name", "")).lower().replace(".exe", "") == "whatsapp.root"]
    if not native:
        return {"success": False, "error": "Verified WhatsApp.Root process/window was not found"}
    title = next((str(r.get("Title")) for r in native if r.get("Title")), "WhatsApp")
    focused = U.focus_window_win32(title)
    if not focused.get("success"):
        return {"success": False, "error": focused.get("error", "Unable to focus native WhatsApp")}
    controls = U.list_ui_controls("whatsapp")
    names = [str(c.get("name", "")).lower() for c in controls.get("controls", [])]
    composer = [c for c in controls.get("controls", [])
                if any(token in str(c.get("name", "")).lower()
                       for token in ("message", "type a message", "compose"))]
    if not composer:
        return {
            "success": False,
            "status": "blocked",
            "error": "Native WhatsApp WebView exposes no verifiable message composer",
            "window": title,
            "controls": len(names),
            "keyboard_probe": "not_started",
        }
    return {"success": False, "status": "blocked",
            "error": "Composer verification requires a supported native control",
            "window": title}

def click_form_field(app_name=None, index=None, field_label=None):
    """Click INTO a form control via UI Automation (semantic, no coordinate guessing).
    Self-healing: if the exact automation id is gone, recovers via cached map using
    name-similarity + relative offset from a live anchor (drift_recovered=true)."""
    return U.click_form_field(app_name, index=index, field_label=field_label)

def select_autocomplete_suggestion(app_name, suggestion, control_label=None):
    return U.select_autocomplete_suggestion(app_name, suggestion, control_label=control_label)

def set_form_field_value(app_name, field_label, value):
    return U.set_form_field_value(app_name, field_label, value)

def run_graph(graph):
    """Execute a dependency-aware multi-step action graph (list of {"id","tool","args",
    "depends_on","rollback"...} steps) deterministically. Each step runs through the SAME
    consent gate + self-healing layer as normal tools. On any failure/consent-block, earlier
    steps roll back in reverse order (declared 'rollback' action or captured pre-state).
    Accepts a graph dict or a JSON string. Returns a full plan report."""
    if isinstance(graph, str):
        try:
            graph = json.loads(graph)
        except Exception as e:
            return {"success": False, "error": f"graph must be valid JSON or a dict: {e}"}
    try:
        plan = TaskGraph(graph)
        return plan.run(execute_action)
    except TaskGraphError as e:
        return {"success": False, "error": str(e)}


TOOLS = {
    "list_windows": list_windows,
    "get_screen_size": get_screen_size,
    "get_mouse_position": get_mouse_position,
    "move_mouse": move_mouse,
    "drag": drag,
    "paint_draw_shapes": paint_draw_shapes,
    "paint_select_control": paint_select_control,
    "paint_draw_path": paint_draw_path,
    "paint_canvas_region": paint_canvas_region,
    "paint_select_color": paint_select_color,
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
    "monitor_downloads": monitor_downloads,
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
    "focus_or_launch": focus_or_launch,
    "new_window": new_window,
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
    "open_file": open_file,
    "browse_to": browse_to,
    "crop_image": crop_image,
    "list_form_fields": list_form_fields,
    "list_ui_controls": list_ui_controls,
    "whatsapp_prepare_draft": whatsapp_prepare_draft,
    "whatsapp_focus_probe": whatsapp_focus_probe,
    "click_form_field": click_form_field,
    "select_autocomplete_suggestion": select_autocomplete_suggestion,
    "set_form_field_value": set_form_field_value,
    "run_graph": run_graph,
}

# ---------- CONSENT / RISK TIER ----------
# Every tool carries a risk level. Destructive tools REQUIRE explicit user confirmation
# before execute_action fires (chained multi-step tasks can otherwise destroy data
# silently). Levels:
#   read        - no side effects; safe to run freely
#   write-safe  - modifies state but reversible/low blast radius; runs if the task implies it
#   destructive - irreversible or high-impact (delete/overwrite/uninstall/radio-off/lock);
#                 blocked until the user types yes in the console
RISK_LEVELS = {
    # read
    "list_windows": "read", "get_screen_size": "read", "get_mouse_position": "read",
    "process_running": "read", "clipboard_get": "read", "list_files": "read",
    "read_file": "read", "storage_info": "read", "current_time": "read",
    "monitor_downloads": "read",
    "system_info": "read", "network_info": "read", "network_speed": "read", "ping": "read",
    "bluetooth_devices": "read", "bluetooth_radio_state": "read", "installed_programs": "read",
    "list_running_apps": "read", "app_state": "read", "describe_screen": "read",
    "take_screenshot": "read", "find_on_screen": "read", "get_brightness": "read",
    "get_volume": "read", "radio_state": "read", "cpu_ram_usage": "read",
    "list_tabs": "read", "list_form_fields": "read", "ask_user": "read",
    "list_ui_controls": "read", "select_autocomplete_suggestion": "write-safe",
    "whatsapp_prepare_draft": "write-safe",
    "whatsapp_focus_probe": "write-safe",
    "crop_image": "read",
    # write-safe
    "run_graph": "write-safe",
    "move_mouse": "write-safe", "click": "write-safe", "type_text": "write-safe",
    "drag": "write-safe",
    "paint_draw_shapes": "write-safe",
    "paint_select_control": "write-safe", "paint_draw_path": "write-safe", "paint_select_color": "write-safe",
    "paint_canvas_region": "read",
    "press_key": "write-safe", "hotkey": "write-safe", "open_url": "write-safe",
    "launch_app": "write-safe", "focus_window": "write-safe", "clipboard_set": "write-safe",
    "focus_or_launch": "write-safe", "new_window": "write-safe", "use_app": "write-safe",
    "create_file": "write-safe", "create_folder": "write-safe", "open_file": "write-safe",
    "browse_to": "write-safe", "focus_tab": "write-safe", "reveal_in_explorer": "write-safe",
    "copy_file": "write-safe", "click_image": "write-safe", "click_form_field": "write-safe",
    "set_form_field_value": "write-safe",
    "set_brightness": "write-safe", "set_volume": "write-safe", "mute": "write-safe",
    "unmute": "write-safe", "bluetooth_connect": "write-safe", "bluetooth_disconnect": "write-safe",
    # destructive (need confirmation)
    "delete_path": "destructive", "move_file": "destructive", "rename_file": "destructive",
    "write_file": "destructive", "uninstall_program": "destructive",
    "install_program": "destructive", "power_state": "destructive",
    "bluetooth_radio": "destructive", "wifi_radio": "destructive", "airplane_mode": "destructive",
    "close_window": "destructive",
}

def _confirm_destructive(tool: str, args: dict) -> bool:
    """Ask the human for explicit yes before a destructive action fires.
    No interactive stdin (EOF/automation context) = DENY: destructive actions never run
    without a live typed 'yes'."""
    try:
        summary = json.dumps(args, ensure_ascii=False)[:300]
    except Exception:
        summary = str(args)[:300]
    print(f"\n  [CONSENT REQUIRED] Tool '{tool}' is DESTRUCTIVE.\n  Args: {summary}")
    try:
        ans = input("  Type 'yes' to allow, anything else to block: ").strip().lower()
        return ans in ("yes", "y")
    except EOFError:
        print("  [CONSENT] no interactive stdin -> treating as DENIED.")
        return False

def _maybe_confirm(tool: str, args: dict) -> str | None:
    """Returns None if ok to run, else a user-block message (tool not executed)."""
    risk = RISK_LEVELS.get(tool, "write-safe")
    if tool == "use_app" and str(args.get("action", "")).lower() == "close":
        risk = "destructive"
    if risk != "destructive":
        return None
    if _confirm_destructive(tool, args):
        _log_invocation(tool, args, "approved")
        return None
    _log_invocation(tool, args, "blocked_by_user")
    return f"Tool '{tool}' BLOCKED: you (the user) declined confirmation. Do NOT retry it; adapt (e.g. skip the action or ask)."

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
    "DESTRUCTIVE TOOLS (delete_path, write_file, move_file, rename_file, uninstall_program, "
    "install_program, power_state, bluetooth_radio, wifi_radio, airplane_mode, close_window) "
    "require the user to type 'yes' in the console. If one gets blocked, the user refused - "
    "ADAPT, do not retry the same destructive call. Prefer reversible alternatives (e.g. copy_file instead of move, "
    "create_file instead of overwriting) whenever possible, and ask_user before destroying data.\n"
    "VISION IS FOR VERIFICATION ONLY - take_screenshot/describe_screen tell you WHAT is on screen (page state, result of an action). "
    "NEVER use describe_screen, click_image coordinates from the vision model, or any vision-based click to land a click or type - "
    "the vision model's coordinates are NOT reliable. Use UIA (list_form_fields, click_form_field) or keyboard (type_text/press_key -> tab -> enter) "
    "for all interaction. Use find_on_screen/click_image ONLY for template images you already cropped with crop_image.\n"
    "For opening/launching apps, creating/writing/deleting files, opening URLs, and system/network tasks, act DIRECTLY without vision.\n"
    "AFTER creating, writing, renaming, or moving any file/folder, reveal it with reveal_in_explorer "
    "AND open the file with open_file (default app) so the user can see its contents, "
    "UNLESS the user explicitly said not to focus/open. After opening a file in an app, focus that app window.\n"
    "If a tool fails, adapt: use a working tool or a real path from your environment, NEVER repeat the same failed action.\n"
    "Only use ask_user when genuinely ambiguous (e.g. which file/app the user means). Never ask about things you can detect yourself.\n"
    "If you are unsure which tool to use, respond with 'done' rather than guessing.\n"
    "BROWSER TASKS: preserve unrelated tabs (for example, music or a user's work). "
    "Use browse_to with new_tab=true for a separate task tab; it reuses only a matching URL tab and otherwise opens one new tab. "
    "Never navigate the current tab unless the user explicitly requests replacing it (new_tab=false). "
    "Do not use new_window unless the user explicitly requests a separate browser window. "
    "Do NOT use focus_window/focus_or_launch to 'open' a URL — those only focus existing windows. "
    "Use browse_to (not open_url) when you will TYPE or CLICK inside the page — it FOCUSES the right tab so input lands correctly.\n"
    "FORMS: after browse_to/focus on a form page, fill fields with keyboard: type_text into the focused field, "
    "press 'tab' to move to the next field, and press 'enter' to submit. This is RELIABLE. "
    "If keyboard Tab order is unknown, use list_form_fields to discover the fields and click_form_field to focus one, "
    "then type_text. Do NOT ask the vision model for click coordinates - they are inaccurate.\n"
    "APP INSTANCE RULE: launch_app and focus_or_launch reuse/focus an existing application instance. "
    "Never call launch_app repeatedly. Use new_window only when the user explicitly requests another instance, "
    "and never create more than two instances of one app in a task. Always inspect list_windows/app_state first "
    "when an app may already be open.\n"
    "NATIVE WHATSAPP: use list_ui_controls('WhatsApp') rather than list_form_fields. "
    "Only use controls belonging to the verified WhatsApp.Root process/window. "
    "For a recent-chat draft, inspect the control tree and screenshot, focus the most recent chat, type 'Hi', "
    "then stop before Enter or Send and report the detected recipient.\n"
    "Use whatsapp_prepare_draft for the guarded native draft workflow. It fails closed when the WebView "
    "does not expose a verifiable recipient and composer; never bypass that failure with guessed coordinates.\n"
    "Before any native WhatsApp draft, use whatsapp_focus_probe with at most 8 steps. This probe never types "
    "or sends; inspect its focused control observations and a screenshot, then proceed only when the recipient "
    "and composer are verifiable.\n"
    "FORM CONFIDENCE RULE: never fill a form by guessed Tab order or coordinates when multiple controls are present. "
    "Use list_form_fields, match the requested labels, and use click_form_field with field_label. "
    "If the target form or required field cannot be identified, stop and report blocked instead of clicking.\n"
    "AUTOCOMPLETE: use select_autocomplete_suggestion for a semantic UIA suggestion and require its verified actual value; "
    "use set_form_field_value when a ValuePattern field can be read back. Never accept a merely successful keystroke as a selected value.\n"
    "MULTI-STEP ROUTING: keep simple one-action work in the flat loop. For explicit dependent steps, rollback requirements, "
    "or a structured steps/graph response, use run_graph so consent, verification, and rollback are deterministic. "
    "A graph does not bypass consent for destructive steps.\n"
    "PAINT ART TASKS: for user-requested artwork, do not use paint_draw_shapes (that is only a regression test). "
    "Use paint_select_control to choose Pencil, Line, Oval, Rectangle, Fill, or other named Paint controls; "
    "use paint_select_color for named palette colors; call paint_canvas_region before drawing and use normalized "
    "paint_draw_path points in the 0..1 range (or verified absolute points) "
    "for each planned element. Work from background to foreground, take screenshots between layers, and only finish "
    "after the screenshot visibly verifies the requested artwork. Do not repeat an unchanged click or claim completion "
    "after a failed drawing action.\n"
    "Do not use done as proof of success. Before done, perform a read-back or other observable verification and only "
    'then respond: {"tool": "done", "args": {}, "then_wait": 0}\n'
)


def execute_action(action):
    global TASK_LAUNCH_COUNTS
    tool = action.get("tool")
    args = action.get("args", {}) or {}
    if tool == "paint_select_control" and "name" not in args and "control" in args:
        args = {**args, "name": args["control"]}
    if tool == "then_wait":
        return "Invalid action: then_wait belongs beside args, not in tool.", False
    if tool == "done":
        return "DONE_REQUESTED", False
    repeat_block = _repeat_limit_message(tool, args)
    if repeat_block:
        _log_invocation(tool, args, "blocked_by_limit")
        return repeat_block, False
    if tool == "take_screenshot":
        decision = dc.safety.check(DesktopActionType.SCREEN_CAPTURE)
        if not decision.allowed:
            _log_invocation(tool, args, "blocked_by_safety")
            return f"Tool '{tool}' BLOCKED by safety policy: {decision.reason}", False
        r = take_screenshot(args.get("path"))
        return f"Screenshot: {json.dumps(r) if not isinstance(r, str) else r}", False
    if not isinstance(tool, str) or tool not in TOOLS:
        _log_invocation(tool, args, "unknown_tool")
        return f"Unknown tool: {tool}. Stick to the tools listed above.", False
    if tool in {"new_window", "launch_app"} or (
        tool == "use_app" and str(args.get("action", "")).lower() in {"open", "open_new", "launch"}
    ):
        app_key = str(args.get("app", "unknown")).lower().strip().replace(".exe", "")
        count = TASK_LAUNCH_COUNTS.get(app_key, 0)
        if count >= MAX_INSTANCES_PER_APP:
            _log_invocation(tool, args, "blocked_by_limit")
            return (
                f"Tool '{tool}' blocked: task instance limit reached for '{app_key}' "
                f"(max {MAX_INSTANCES_PER_APP}). Focus an existing instance instead.",
                False,
            )
    blocked = _maybe_confirm(tool, args)
    if blocked:
        return blocked, False
    safety_types = {
        "new_window": DesktopActionType.WINDOW_MANAGE,
        "browse_to": DesktopActionType.WINDOW_MANAGE,
        "use_app": DesktopActionType.WINDOW_MANAGE,
    }
    action_type = safety_types.get(tool)
    if action_type is not None:
        try:
            safety_params = dict(args)
            if tool == "type_text":
                interval = float(safety_params.pop("interval", 0.05))
                safety_params["rate_char_per_sec"] = 1.0 / interval if interval > 0 else float("inf")
            decision = dc.safety.check(action_type, safety_params, update_state=False)
        except (TypeError, ValueError, OverflowError) as exc:
            _log_invocation(tool, args, "error")
            return f"Tool '{tool}' error: invalid arguments: {exc}", False
        if not decision.allowed:
            _log_invocation(tool, args, "blocked_by_safety")
            return f"Tool '{tool}' BLOCKED by safety policy: {decision.reason}", False
    fn = TOOLS[tool]
    try:
        result = fn(**args)
    except TypeError:
        try:
            result = fn(*list(args.values()))
        except Exception as e:
            _log_invocation(tool, args, "error")
            return f"Tool '{tool}' error: {e}", False
    except Exception as e:
        _log_invocation(tool, args, "error")
        return f"Tool '{tool}' error: {e}", False
    if action_type is not None and isinstance(result, dict) and result.get("success", True):
        dc.safety.check(action_type, dict(args), update_state=True)
    ok = True
    if isinstance(result, dict):
        ok = result.get("success", not bool(result.get("error")))
    elif result is False or result == "False" or isinstance(result, str) and result.lower().startswith(("false", "error")):
        ok = False
    if tool in {"click", "move_mouse", "drag"} or (
        tool == "use_app" and str(args.get("action", "")).lower() == "click"
    ):
        if isinstance(result, dict):
            result.setdefault("interaction_method", "coordinate")
            result.setdefault("coordinate_fallback", True)
            result.setdefault("verified", False)
        else:
            result = {
                "success": ok,
                "interaction_method": "coordinate",
                "coordinate_fallback": True,
                "verified": False,
                "result": result,
            }
    _log_invocation(tool, args, "ok" if ok else "failed")
    if ok and (tool in {"new_window", "launch_app"} or (
        tool == "use_app" and str(args.get("action", "")).lower() in {"open", "open_new", "launch"}
    )):
        app_key = str(args.get("app", "unknown")).lower().strip().replace(".exe", "")
        TASK_LAUNCH_COUNTS[app_key] = TASK_LAUNCH_COUNTS.get(app_key, 0) + 1
    return f"Tool '{tool}' result: {json.dumps(result, default=str, ensure_ascii=False) if not isinstance(result, (str, bool)) else result}", False


def _route_structured_actions(actions: list[dict]) -> list[dict]:
    """Keep the flat loop compatible while routing explicit plans through TaskGraph."""
    if len(actions) == 1:
        candidate = actions[0]
        if "tool" not in candidate and ("steps" in candidate or "graph" in candidate):
            graph = candidate.get("graph", candidate)
            return [{"tool": "run_graph", "args": {"graph": graph}}]
        return actions
    if actions and all(
        isinstance(item, dict) and item.get("tool") and
        any(key in item for key in ("id", "depends_on", "rollback", "rollback_capture", "verify"))
        for item in actions
    ):
        steps = []
        for index, item in enumerate(actions, 1):
            step = dict(item)
            step.setdefault("id", f"step_{index}")
            steps.append(step)
        return [{"tool": "run_graph", "args": {"graph": {"steps": steps}}}]
    return actions


def parse_actions(response_text: str):
    """Robustly parse one or more JSON actions from model output."""
    response_text = response_text.strip().strip("`")
    if response_text.startswith("json"):
        response_text = response_text[4:].lstrip()
    try:
        parsed = json.loads(response_text)
        parsed = parsed if isinstance(parsed, list) else [parsed]
        if len(parsed) == 1 and isinstance(parsed[0], dict) and (
            "steps" in parsed[0] or "graph" in parsed[0]
        ):
            return _route_structured_actions(parsed)
        return _route_structured_actions([
            a for a in parsed if isinstance(a, dict) and (
                (isinstance(a.get("tool"), str) and a["tool"] != "None")
                or "steps" in a or "graph" in a
            )
        ])
    except json.JSONDecodeError:
        pass

    # Brace-balanced scan: extract each top-level {...} object, tolerating nested braces.
    actions = []
    depth = 0
    start = None
    for i, ch in enumerate(response_text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                chunk = response_text[start:i + 1]
                try:
                    a = json.loads(chunk)
                    if isinstance(a, dict) and (
                        (isinstance(a.get("tool"), str) and a["tool"] != "None")
                        or "steps" in a or "graph" in a
                    ):
                        actions.append(a)
                except json.JSONDecodeError:
                    pass
                start = None
    return _route_structured_actions(actions)


_OBSERVATION_TOOLS = {
    "read_file", "list_files", "list_windows", "list_running_apps", "app_state",
    "process_running", "desktop_state", "clipboard_get", "current_time",
    "system_info", "storage_info", "network_info", "bluetooth_devices",
    "installed_programs", "list_tabs", "list_form_fields", "list_ui_controls",
    "describe_screen", "take_screenshot", "focus_tab", "run_graph",
}


def _parse_action_result(text: str) -> dict[str, Any]:
    marker = "result:"
    if marker not in str(text):
        return {}
    payload = str(text).split(marker, 1)[1].strip()
    try:
        parsed = json.loads(payload)
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except (TypeError, json.JSONDecodeError):
        return {}


def _completion_is_verified(records: list[dict[str, Any]]) -> bool:
    """A done request is not success until a tool reports an observable outcome."""
    for record in reversed(records):
        if record.get("tool") == "done":
            continue
        payload = record.get("payload") or _parse_action_result(record.get("result", ""))
        if payload.get("verified") is True:
            return True
        if record.get("tool") in _OBSERVATION_TOOLS:
            if record.get("tool") == "run_graph":
                return payload.get("success") is True and payload.get("status") == "completed"
            if payload.get("error") or payload.get("success") is False:
                continue
            return bool(payload) or "DONE" not in str(record.get("result", ""))
    return False


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    goal = " ".join(sys.argv[1:])
    TASK_LAUNCH_COUNTS.clear()
    _reset_action_limits()
    global TASK_BROWSER_TABS_OPENED
    TASK_BROWSER_TABS_OPENED = 0
    print(f"\n[GOAL] {goal}")
    print(f"[PROVIDER] reasoning={REASONING_PROVIDER.provider_id}/{REASONING_PROVIDER.model} "
          f"vision={VISION_PROVIDER.provider_id}/{VISION_PROVIDER.model}")
    print(_tool_health() + "\n")

    health_hint = _load_tool_health_for_prompt()
    history = SYSTEM_PROMPT + (f"\n\n{health_hint}\n" if health_hint else "") + f"\n\nUSER TASK: {goal}\n"

    max_steps = 20
    max_runtime_seconds = 600
    started_at = time.monotonic()
    recent_actions: list[str] = []
    invalid_tries = 0
    done = False
    steps_executed = 0  # track how many non-done actions have run
    execution_records: list[dict[str, Any]] = []
    for step in range(max_steps):
        if time.monotonic() - started_at >= max_runtime_seconds:
            print(f"[STOP] Task runtime exceeded {max_runtime_seconds} seconds.")
            break
        print(f"\n--- Step {step+1}: {REASONING_PROVIDER.provider_id}/{REASONING_PROVIDER.model} thinking... ---")
        try:
            raw = REASONING_PROVIDER.chat(history)
        except Exception as e:
            print(f"[ERROR] Provider call failed: {e}")
            print("[HINT] Is Ollama running? Type 'ollama serve' in another tab.")
            break

        actions = parse_actions(raw)
        if not actions:
            invalid_tries += 1
            print(f"[RAW] {raw[:300]}")
            if invalid_tries >= 3:
                history += (
                    f"\nYou must make progress on the ORIGINAL TASK: {goal}\n"
                    "Output exactly ONE JSON action from the tool list to continue. "
                    "Do NOT output prose, explanations, errors, or markdown. "
                    "If the remaining task needs no more actions, output {\"tool\":\"done\",\"args\":{}}.\n"
                )
                invalid_tries = 0
            else:
                history += "\nInvalid output. Output exactly one JSON action object, no prose.\n"
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
            clipped = str(result)
            if len(clipped) > 900:
                clipped = clipped[:900] + f" ... [truncated, {len(str(result))-900} chars omitted]"
            print(f"[RESULT] {clipped}")
            history += f"\nExecuted: {json.dumps(single)}\nResult: {clipped}\n"
            record = {
                "tool": single.get("tool"),
                "args": single.get("args", {}),
                "result": result,
                "payload": _parse_action_result(str(result)),
            }
            execution_records.append(record)
            if single.get("tool") != "done":
                steps_executed += 1
            if single.get("tool") == "done":
                verified = _completion_is_verified(execution_records)
                if re.search(r"\b(landscape|house|mountain|water|painting|artwork)\b", goal, re.I):
                    verification = describe_screen(
                        "Verify the requested Paint artwork. Identify whether a complete colored "
                        "landscape is visibly present, including sky, mountains, house, water, and "
                        "foreground details. Start with YES or NO."
                    )
                    verdict = str(verification.get("description", "")).strip().upper()
                    verified = verdict.startswith("YES")
                    record["payload"] = {"verified": verified, "description": verification.get("description", "")}
                    if not verified:
                        history += (
                            "\nThe final artwork verification failed or did not confirm the requested "
                            "scene. Do not finish. Inspect Paint and continue with a different valid action.\n"
                        )
                        continue
                if steps_executed > 0 and verified:
                    done = True
                    break
                else:
                    history += (
                        "\nCompletion was requested without a verified observable outcome. "
                        "Perform a read-back/check (for example read_file, list_windows, "
                        "list_form_fields, or describe_screen) before using done.\n"
                    )
                    invalid_tries += 1
                    recent_actions.clear()
                    break
            time.sleep(max(0.5, single.get("then_wait", 1.0)))

        if done:
            break
        history += "Continue.\n"

    print("\n" + "=" * 50)
    print(" TASK COMPLETED" if done else " Stopped at max steps")
    print("=" * 50)
    print(_tool_health() + "\n")


if __name__ == "__main__":
    main()
