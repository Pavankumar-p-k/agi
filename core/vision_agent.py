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
# core/vision_agent.py
"""
╔══════════════════════════════════════════════════════════════════╗
║   J.A.R.V.I.S  VISION AGENT  —  See → Think → Act → Verify    ║
╠══════════════════════════════════════════════════════════════════╣
║  Works exactly like Cursor/Devin/Claude Computer Use but 100%   ║
║  offline on YOUR machine using Gemma4 + Moondream via Ollama.   ║
║                                                                  ║
║  You say: "open chrome, go to amazon, buy white tshirt ₹500"   ║
║  JARVIS:                                                         ║
║   1. Screenshot → Moondream: "desktop with taskbar"             ║
║   2. Llama3 plans: 12 steps                                     ║
║   3. Executes: type "chrome" → Enter → wait → navigate...      ║
║   4. After each step: screenshot → Moondream verifies it worked ║
║   5. If wrong: self-corrects, retries with new approach         ║
║   6. Reports: "Done! Added Roadster White T-Shirt ₹399 to cart"║
╚══════════════════════════════════════════════════════════════════╝
"""

import asyncio
import base64
import io
import json
import logging
import os
import re
import shlex
import time
from dataclasses import dataclass, field

import httpx
import mss
import pyautogui
from PIL import Image

from core.model_router import get_ollama_url, model_for_role

logger = logging.getLogger(__name__)

pyautogui.FAILSAFE = True   # move mouse top-left to emergency stop
pyautogui.PAUSE    = 0.35

# Safe print that won't crash on Windows consoles with limited Unicode
_SAFE_PRINT = True


_ORIGINAL_PRINT = print


def _sp(*args, **kwargs):
    """Print with Unicode-safe encoding fallback."""
    if not _SAFE_PRINT:
        return
    text = " ".join(str(a) for a in args)
    try:
        _ORIGINAL_PRINT(text, **kwargs)
    except UnicodeEncodeError:
        safe = text.encode("ascii", errors="replace").decode("ascii")
        _ORIGINAL_PRINT(safe, **kwargs)


print = _sp

VISION_MODEL = model_for_role("vision")
PLAN_MODEL = model_for_role("planning")
QUALITY_MODEL = model_for_role("quality")

# ─── Data classes ────────────────────────────────────────────

@dataclass
class ScreenState:
    b64:   str          # JPEG base64 (half-res for Moondream speed)
    w:     int = 1920
    h:     int = 1080
    ts:    float = field(default_factory=time.time)

@dataclass
class StepResult:
    step_num: int
    desc:     str
    action:   str
    status:   str = "pending"  # pending/done/failed/skipped
    output:   str = ""
    error:    str = ""

@dataclass
class Task:
    id:          str
    instruction: str
    platform:    str = "pc"
    steps:       list = field(default_factory=list)
    status:      str  = "planning"
    result:      str  = ""
    error:       str  = ""
    t_start:     float = field(default_factory=time.time)
    t_end:       float = 0.0

# ─── Prompts ─────────────────────────────────────────────────

PLAN_SYS = """You are JARVIS, an expert PC automation agent planning steps for pyautogui.
Given a screenshot description and a task, return ONLY a JSON array of steps.

Available actions and their params:
  open_app   → {"app": "chrome"}
  navigate   → {"url": "amazon.in"}
  click      → {"target": "describe exactly what to click"}
  dblclick   → {"target": "describe what to double-click"}
  rclick     → {"target": "describe what to right-click"}
  type       → {"text": "text to type"}
  clear_type → {"text": "clear field then type this"}
  press      → {"key": "enter|tab|escape|delete|f5"}
  hotkey     → {"keys": ["ctrl","a"]}
  scroll     → {"dir": "down", "n": 3}
  wait       → {"sec": 1.5}
  screenshot → {}

Rules:
- Each step does ONE thing
- Be very specific in "target" descriptions for clicks
- Always wait after opening apps (sec: 2.5)
- Always wait after navigation (sec: 2.0)
- Max 25 steps
- Return ONLY the JSON array, nothing else

Example for "search amazon for shoes":
[
  {"step_num":1,"desc":"Open Chrome browser","action":"open_app","params":{"app":"chrome"}},
  {"step_num":2,"desc":"Wait for Chrome to open","action":"wait","params":{"sec":2.5}},
  {"step_num":3,"desc":"Go to Amazon India","action":"navigate","params":{"url":"amazon.in"}},
  {"step_num":4,"desc":"Wait for Amazon to load","action":"wait","params":{"sec":2.0}},
  {"step_num":5,"desc":"Click the search bar","action":"click","params":{"target":"Amazon search input bar at the top center"}},
  {"step_num":6,"desc":"Type search query","action":"type","params":{"text":"shoes"}},
  {"step_num":7,"desc":"Press Enter to search","action":"press","params":{"key":"enter"}},
  {"step_num":8,"desc":"Wait for results","action":"wait","params":{"sec":1.5}}
]"""

FIND_SYS = """You locate UI elements on screenshots.
Return ONLY JSON: {"x": NUMBER, "y": NUMBER}
Coordinates are in HALF the real screen resolution (image was scaled 50%).
If element not found: {"x": null, "y": null}
No explanation. Only JSON."""

VERIFY_SYS = """You verify if a UI action succeeded.
Return ONLY JSON: {"ok": true/false, "reason": "one line"}"""

SCREEN_SYS = """Describe this screenshot in 2-3 sentences.
List: what app/website is open, windows visible, UI elements, text, colors, icons."""

CORRECT_SYS = """A step failed. Suggest one alternative.
Return ONLY JSON: {"desc":"new approach","action":"action_name","params":{}}"""


class VisionAgent:
    """PC Vision Agent — natural language → automated PC actions"""

    def __init__(self):
        self._sct   = mss.mss()
        self._http  = httpx.AsyncClient(timeout=120.0)
        self._history: list[Task] = []
        self.MAX_STEPS = 25

    # ═══ PUBLIC: run a task ══════════════════════════════════

    async def run(self, instruction: str) -> Task:
        task = Task(id=f"t{int(time.time())}", instruction=instruction)
        print(f"\n[Vision] ══ '{instruction}' ══")

        try:
            # 1. Capture current screen
            state = await self._capture()

            # 2. Describe screen + plan steps
            screen_desc = await self._describe(state)
            print(f"[Vision] Screen: {screen_desc[:100]}")
            steps = await self._plan(instruction, screen_desc)
            task.steps  = steps
            task.status = "running"
            print(f"[Vision] {len(steps)} steps planned")

            # 3. Execute each step
            for i, step in enumerate(steps[:self.MAX_STEPS]):
                print(f"[Vision] Step {i+1}: {step.get('desc','')}")
                res = await self._do(step)

                if res.status == "failed":
                    alt = await self._correct(step, res.error)
                    if alt:
                        print(f"[Vision] Retrying with: {alt.get('desc','')}")
                        res = await self._do(alt)

                step["_status"] = res.status
                step["_output"] = res.output

                # Verify every click/navigate/type
                if res.status == "done" and step.get("action") in ("click","navigate","press","open_app"):
                    await asyncio.sleep(0.6)
                    state = await self._capture()
                    ok = await self._verify(step, state)
                    if not ok:
                        print(f"[Vision] Step {i+1} verify failed — retrying")
                        await self._do(step)

                await asyncio.sleep(0.2)

            task.status = "done"
            task.t_end  = time.time()
            task.result = await self._summarize(task)
            print(f"[Vision] ✓ {task.result}")

        except Exception as e:
            task.status = "failed"
            task.error  = str(e)
            print(f"[Vision] ✗ {e}")

        self._history.append(task)
        return task

    # ═══ SCREENSHOT ═════════════════════════════════════════

    async def _capture(self, region=None) -> ScreenState:
        mon  = self._sct.monitors[1]
        sct  = self._sct.grab(region or mon)
        img  = Image.frombytes("RGB", sct.size, sct.bgra, "raw", "BGRX")
        w, h = img.size
        half = img.resize((w//2, h//2), Image.LANCZOS)
        buf  = io.BytesIO()
        half.save(buf, "JPEG", quality=75)
        return ScreenState(b64=base64.b64encode(buf.getvalue()).decode(), w=w, h=h)

    # ═══ Moondream VISION ═══════════════════════════════════

    async def _describe(self, s: ScreenState) -> str:
        r = await self._llava(SCREEN_SYS, "Describe this screen:", s.b64, 80)
        return r or "Desktop"

    async def _find(self, target: str, s: ScreenState) -> tuple | None:
        prompt = f"Find '{target}' on this screen. Return its center pixel coordinates."
        raw = await self._llava(FIND_SYS, prompt, s.b64, 40)
        try:
            m = re.search(r'\{[^}]+\}', raw or "")
            if m:
                d = json.loads(m.group())
                x, y = d.get("x"), d.get("y")
                if x is not None and y is not None:
                    return (int(x)*2, int(y)*2)   # scale back to full res
        except Exception as e:
            logging.getLogger(__name__).warning("[VisionAgent] _cluster_coord parse failed: %s", e)
        return None

    async def _verify(self, step: dict, s: ScreenState) -> bool:
        prompt = f"Did this action succeed: '{step.get('desc','')}'?"
        raw = await self._llava(VERIFY_SYS, prompt, s.b64, 50)
        try:
            m = re.search(r'\{[^}]+\}', raw or "")
            if m:
                return json.loads(m.group()).get("ok", True)
        except Exception as e:
            logging.getLogger(__name__).debug("[VisionAgent] _verify JSON parse failed: %s", e)
        return True

    # ═══ PLANNING ═══════════════════════════════════════════

    async def _plan(self, task: str, screen_desc: str) -> list:
        prompt = f"Current screen: {screen_desc}\n\nTask to complete: {task}"
        raw = await self._llm(PLAN_SYS, prompt, PLAN_MODEL, 900)
        try:
            m = re.search(r'\[.*\]', raw or "", re.DOTALL)
            if m:
                return json.loads(m.group())
        except Exception as e:
            logging.getLogger(__name__).debug("[VisionAgent] _plan parse failed: %s", e)
        return [{"step_num":1,"desc":"Take screenshot","action":"screenshot","params":{}}]

    # ═══ EXECUTION ══════════════════════════════════════════

    async def _do(self, step: dict) -> StepResult:
        action = step.get("action","")
        params = step.get("params",{})
        num    = step.get("step_num", 0)
        desc   = step.get("desc","")
        try:
            out = await self._exec(action, params)
            return StepResult(num, desc, action, "done", out)
        except Exception as e:
            return StepResult(num, desc, action, "failed", error=str(e))

    async def _exec(self, action: str, p: dict) -> str:
        if action == "open_app":
            app = p.get("app","").lower()
            import shutil
            import subprocess
            CMDS = {
                "chrome": shutil.which("chrome") or "start chrome",
                "firefox": shutil.which("firefox") or "start firefox",
                "notepad": shutil.which("notepad") or "notepad",
                "explorer": shutil.which("explorer") or "explorer",
                "photos": "start ms-photos:",
                "settings": "start ms-settings:",
                "calculator": shutil.which("calc") or "calc",
                "cmd": "start cmd",
                "spotify": shutil.which("spotify") or "start spotify",
                "vscode": shutil.which("code") or "code",
                "terminal": "start cmd",
            }
            cmd = CMDS.get(app, shutil.which(app) or f"start {shlex.quote(app)}")
            if isinstance(cmd, str) and cmd.startswith("start "):
                # Avoid shell=True: invoke platform shell explicitly
                if os.name == 'nt':
                    subprocess.Popen(["cmd", "/c"] + shlex.split(cmd), shell=False)
                else:
                    subprocess.Popen(["/bin/sh", "-c", cmd], shell=False)
            else:
                if isinstance(cmd, str) and ' ' in cmd:
                    subprocess.Popen(shlex.split(cmd), shell=False)
                else:
                    subprocess.Popen([cmd], shell=False)
            await asyncio.sleep(2.5)
            return f"Opened {app}"

        elif action == "navigate":
            url = p.get("url","")
            if not url.startswith("http"): url = "https://" + url
            pyautogui.hotkey("ctrl","l")
            await asyncio.sleep(0.3)
            pyautogui.hotkey("ctrl","a")
            pyautogui.typewrite(url, interval=0.04)
            pyautogui.press("enter")
            await asyncio.sleep(2.2)
            return f"Navigated to {url}"

        elif action in ("click","dblclick","rclick"):
            target = p.get("target","")
            state  = await self._capture()
            coords = await self._find(target, state)
            if not coords: raise Exception(f"'{target}' not found on screen")
            x, y = coords
            if action == "dblclick": pyautogui.doubleClick(x, y)
            elif action == "rclick":  pyautogui.rightClick(x, y)
            else:                     pyautogui.click(x, y)
            await asyncio.sleep(0.5)
            return f"Clicked '{target}' at ({x},{y})"

        elif action == "type":
            await asyncio.sleep(0.2)
            pyautogui.typewrite(p.get("text",""), interval=0.05)
            return f"Typed: {p.get('text','')}"

        elif action == "clear_type":
            pyautogui.hotkey("ctrl","a")
            await asyncio.sleep(0.1)
            pyautogui.typewrite(p.get("text",""), interval=0.05)
            return f"Cleared and typed: {p.get('text','')}"

        elif action == "press":
            pyautogui.press(p.get("key","enter"))
            await asyncio.sleep(0.3)
            return f"Pressed {p.get('key','enter')}"

        elif action == "hotkey":
            pyautogui.hotkey(*p.get("keys",[]))
            await asyncio.sleep(0.3)
            return f"Hotkey: {'+'.join(p.get('keys',[]))}"

        elif action == "scroll":
            n = p.get("n",3)
            pyautogui.scroll(-n if p.get("dir","down")=="down" else n)
            await asyncio.sleep(0.3)
            return f"Scrolled {p.get('dir','down')} {n}x"

        elif action == "wait":
            await asyncio.sleep(float(p.get("sec",1.0)))
            return f"Waited {p.get('sec',1.0)}s"

        elif action == "screenshot":
            await self._capture()
            return "Screenshot taken"

        elif action == "select_all":
            pyautogui.hotkey("ctrl","a")
            return "Selected all"

        elif action == "copy":
            pyautogui.hotkey("ctrl","c")
            return "Copied"

        elif action == "paste":
            pyautogui.hotkey("ctrl","v")
            return "Pasted"

        elif action == "delete":
            pyautogui.press("delete")
            return "Deleted"

        else:
            return f"Unknown action skipped: {action}"

    # ═══ SELF-CORRECTION ════════════════════════════════════

    async def _correct(self, step: dict, error: str) -> dict | None:
        prompt = f"Step '{step.get('desc','')}' with action '{step.get('action','')}' failed: {error}. Alternative?"
        raw = await self._llm(CORRECT_SYS, prompt, QUALITY_MODEL, 120)
        try:
            m = re.search(r'\{.*\}', raw or "", re.DOTALL)
            if m:
                return json.loads(m.group())
        except Exception as e:
            logging.getLogger(__name__).warning("[VisionAgent] _correct parse failed: %s", e)
        return None

    async def _summarize(self, task: Task) -> str:
        done = sum(1 for s in task.steps if s.get("_status")=="done")
        secs = round(task.t_end - task.t_start, 1)
        prompt = f"Task '{task.instruction}' finished {done}/{len(task.steps)} steps in {secs}s. Write one short result sentence."
        return await self._llm("Be concise, friendly.", prompt, QUALITY_MODEL, 60) or f"{done}/{len(task.steps)} steps done in {secs}s"

    # ═══ LLM helpers ════════════════════════════════════════

    async def _llm(self, sys: str, prompt: str, model=PLAN_MODEL, maxt=400) -> str:
        try:
            r = await self._http.post(f"{get_ollama_url(model)}/api/generate", json={
                "model":model,"system":sys,"prompt":prompt,
                "stream":False,"options":{"num_predict":maxt,"num_gpu":99,"temperature":0.25}})
            return r.json().get("response","").strip()
        except Exception as e:
            logging.getLogger(__name__).error(f"[VisionAgent] _llm failed: {e}")
            logger.warning("[VisionAgent] _llm returning empty after failure")
            return ""

    async def _llava(self, sys: str, prompt: str, b64: str, maxt=80) -> str:
        for model in (VISION_MODEL, "moondream:latest"):
            try:
                r = await self._http.post(f"{get_ollama_url(model)}/api/generate", json={
                    "model": model, "system": sys, "prompt": prompt,
                    "images": [b64], "stream": False,
                    "options": {"num_predict": maxt, "num_gpu": 99, "temperature": 0.1}})
                if r.status_code == 200:
                    return r.json().get("response", "").strip()
            except Exception as e:
                logger.debug("[VisionAgent] _llava model %s failed: %s", model, e)
                continue
        logger.warning("[VisionAgent] _llava all models failed")
        return ""

    def get_history(self) -> list:
        return [{"id":t.id,"instruction":t.instruction,"status":t.status,
                 "result":t.result,"steps":len(t.steps),
                 "done":sum(1 for s in t.steps if s.get("_status")=="done"),
                 "duration_s":round(t.t_end-t.t_start,1) if t.t_end else 0}
                for t in self._history[-20:]]

    async def close(self):
        await self._http.aclose()
