"""
core/main.py — JARVIS FastAPI server: all routes + WebSocket + startup
"""
import os
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import asyncio
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional, List, Literal

from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import base64
import httpx
import webbrowser
import subprocess
import json
import re
import urllib.parse
import numpy as np
import cv2
import instructor
from openai import OpenAI
from smolagents import ToolCallingAgent, tool, LiteLLMModel

from .composio_tools import COMPOSIO_TOOLS
from .config import HOST, PORT, ALLOWED_ORIGINS
from .database import get_db, init_db, User
from .auth import verify_token, init_firebase

startup_status = {
    "autonomy": False,
    "hybrid": False,
    "warnings": [],
}


def _warmup_ollama_models():
    """Verify Ollama is reachable and models are available (no pre-loading to save GPU memory)."""
    try:
        from core.model_router import ROLE_MODELS, resolve_model
    except ImportError:
        return

    ollama_url = "http://localhost:11434"

    try:
        import json
        from urllib.request import urlopen
        from urllib.error import URLError
        with urlopen(f"{ollama_url}/api/tags", timeout=2) as resp:
            data = json.loads(resp.read().decode())
            # Normalize model names (handle :latest tag)
            available_models = set()
            for m in data.get("models", []):
                name = m.get("name", "")
                available_models.add(name)
                # Also add version without :latest
                if name.endswith(":latest"):
                    available_models.add(name[:-7])  # Remove ":latest"
    except Exception:
        print("  [OLLAMA] Not reachable, skipping model check")
        return

    # Just verify configured models exist, don't pre-load them (saves GPU memory)
    required_models = sorted({resolve_model(m) for m in ROLE_MODELS.values()})
    missing = [m for m in required_models if m not in available_models]

    if missing:
        print(f"  [OLLAMA] {len(missing)} model(s) not installed: {', '.join(missing[:3])}...")
        startup_status["warnings"].append(f"ollama: {len(missing)} model(s) missing")
    else:
        print(f"  [OLLAMA] All {len(required_models)} models verified installed [OK]")


# ==============================================
#  STARTUP / SHUTDOWN
# ==============================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("=" * 50)
    print("  JARVIS — Starting up...")
    print("=" * 50)

    # Init DB
    await init_db()

    # Init Firebase
    init_firebase()

    # Load pending reminders
    from reminders.manager import reminder_manager
    await reminder_manager.load_and_schedule_all()

    # Inject TTS into reminder manager
    from assistant.engine import jarvis
    reminder_manager.inject_tts(jarvis.tts)

    # Initialize 4-layer autonomous intelligence system (L1-L4)
    try:
        import autonomy
        await autonomy.initialize_autonomous_stack()
        startup_status["autonomy"] = True
        print("  [AUTONOMY] Autonomous stack initialized [OK]")
    except Exception as e:
        startup_status["warnings"].append(f"autonomy: {e}")
        print(f"  [WARNING] Autonomous system init failed: {e}")

    try:
        if startup_status["autonomy"]:
            print("  [HYBRID] Initializing research-grade automation system...")
            from orchestrator.hybrid_orchestrator import hybrid_orchestrator
            from models.hybrid_models import hybrid_manager
            from tools.executor import open_claw_executor

            await hybrid_manager._init_clients()
            startup_status["hybrid"] = True
            print("  [HYBRID] Model fallback system ready [OK]")

            _warmup = asyncio.ensure_future(hybrid_manager._warmup_models())
            _warmup.add_done_callback(lambda t: print(f"  [HYBRID] Warmup {'OK' if not t.exception() else 'FAILED: '+str(t.exception())}" if t.exception() else None))
            print("  [HYBRID] Hybrid Automation System ready [OK]")
        else:
            print("  [HYBRID] Skipping hybrid automation init because autonomy layer failed.")
    except Exception as e:
        startup_status["warnings"].append(f"hybrid: {e}")
        print(f"  [WARNING] Hybrid automation init failed: {e}")

    # Verify Ollama models (wait for Ollama to be ready first)
    try:
        # Wait for Ollama to be ready (up to 30 seconds)
        for _ in range(30):
            try:
                from urllib.request import urlopen
                with urlopen("http://localhost:11434/api/tags", timeout=1) as resp:
                    if resp.status == 200:
                        break
            except Exception:
                await asyncio.sleep(1)
        # Now check models
        _warmup_ollama_models()
    except Exception as e:
        startup_status["warnings"].append(f"ollama_check: {e}")

    # Start WakeWordDetector + VoiceLoop
    try:
        from assistant.voice_pipeline import get_pipeline, VoiceLoop
        _voice_loop = VoiceLoop()
        app.state.voice_loop = _voice_loop
        _voice_loop.start()
        print("  [VOICE] Wake word + voice loop started [OK]")
    except Exception as e:
        print(f"  [WARNING] Wake word/voice loop: {e}")

    if startup_status["warnings"]:
        print("[JARVIS] Startup completed with warnings:")
        for warning in startup_status["warnings"]:
            print(f"  - {warning}")
    else:
        print("[JARVIS] All systems online [OK]")
    yield

    # Shutdown
    from automation.messaging import messaging
    messaging.shutdown()
    if hasattr(app.state, "voice_loop"):
        app.state.voice_loop.stop()
        print("  [VOICE] Voice loop stopped")
    print("[JARVIS] Shutdown complete.")


# ==============================================
#  APP
# ==============================================
app = FastAPI(
    title="JARVIS API",
    description="Personal AI Life Operating System",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Optional routers (kept separate so missing optional deps don't break startup)
try:
    from api.agi_routes import router as agi_router
    app.include_router(agi_router)
except Exception as e:
    print(f"[Router] AGI routes not loaded: {e}")

try:
    from api.vision_routes import router as vision_router
    app.include_router(vision_router)
except Exception as e:
    print(f"[Router] Vision routes not loaded: {e}")

try:
    from api.server import router as brain_router
    app.include_router(brain_router)
except Exception as e:
    print(f"[Router] Brain routes not loaded: {e}")

try:
    from api.os_routes import router as os_router
    app.include_router(os_router)
    print("[Router] AI OS routes loaded")
except Exception as e:
    print(f"[Router] AI OS routes not loaded: {e}")

try:
    from api.ai_os_routes import router as ai_os_router
    app.include_router(ai_os_router)
    print("[Router] AI OS CUSTOM routes loaded")
except Exception as e:
    print(f"[Router] AI OS CUSTOM routes not loaded: {e}")

try:
    from automation.routes import router as automation_router
    app.include_router(automation_router)
except Exception as e:
    print(f"[Router] Automation routes not loaded: {e}")

try:
    from automation.call_sync_server import get_fastapi_router
    app.include_router(get_fastapi_router())
except Exception as e:
    print(f"[Router] Call sync routes not loaded: {e}")

try:
    from api.hybrid_integration import setup_hybrid_routes
    setup_hybrid_routes(app)
    print("[Router] Hybrid Automation routes loaded [OK]")
except Exception as e:
    print(f"[Router] Hybrid Automation routes not loaded: {e}")

# Autonomous Intelligence Layers (L1-L4) — integrated into main system
try:
    import autonomy
    router = autonomy.get_router()
    if router:
        # Mount autonomous API under /autonomy for namespacing
        app.include_router(router, prefix="/autonomy", tags=["Autonomous"])
        # Also mount at root for backward compat (CLI + legacy calls)
        app.include_router(router)
        print("[Router] Autonomous layers routes loaded")
except Exception as e:
    print(f"[Router] Autonomous routes not loaded: {e}")

# Student AGI System — optional separate service
# Runs as: python learning/student_agi/student_agi_main.py
# Can be called via /student-agi/... endpoints when available
try:
    from learning.student_agi.api.student_routes import router as student_router
    app.include_router(student_router, prefix="/student-agi", tags=["Student AGI"])
    print("[Router] Student AGI routes loaded")
except Exception as e:
    print(f"[Router] Student AGI routes not loaded (service may not be started): {e}")


# ==============================================
#  PYDANTIC SCHEMAS
# ==============================================
class ChatRequest(BaseModel):
    message: str
    context: Optional[str] = ""
    tier: Optional[str] = None  # "local", "cloud", or None for default

class ReminderCreate(BaseModel):
    title: str
    remind_at: datetime
    description: Optional[str] = ""
    repeat: Optional[str] = "none"

class NoteCreate(BaseModel):
    title: str
    content: str
    tags: Optional[str] = ""

class NoteUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None

class MessageRequest(BaseModel):
    platform: str        # whatsapp | instagram
    recipient: str       # contact name or @username
    message: str

class FaceRegisterRequest(BaseModel):
    person_name: str
    relation: Optional[str] = "unknown"
    info: Optional[str] = ""
    access_level: Optional[str] = "visitor"


# ==============================================
#  ROUTES — HEALTH
# ==============================================
@app.get("/")
async def root():
    return FileResponse("static/index.html")

app.mount("/assets", StaticFiles(directory="static/assets"), name="assets")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/health")
async def health():
    from assistant.stt import get_stt
    from assistant.tts import get_tts
    from core.database import get_db
    
    stt_loaded = False
    try:
        stt_loaded = get_stt().model is not None
    except: pass
    
    tts_loaded = False
    try:
        tts_loaded = get_tts().pipeline is not None
    except: pass
    
    ollama_ready = False
    try:
        import requests
        resp = requests.get("http://localhost:11434/api/tags", timeout=1)
        ollama_ready = resp.status_code == 200
    except: pass

    db_connected = False
    try:
        # Simple check for DB file existence or a quick query
        import os
        db_connected = os.path.exists("data/jarvis.db")
    except: pass

    return {
        "ollama": ollama_ready,
        "stt_loaded": stt_loaded,
        "tts_loaded": tts_loaded,
        "db_connected": db_connected,
        "timestamp": datetime.utcnow().isoformat()
    }


# ==============================================
#  LLM INTENT EXTRACTION + ACTION EXECUTOR
# ==============================================

class IntentResult(BaseModel):
    intent: Literal[
        "play_media", "open_url", "open_app",
        "web_search", "reminder", "pc_control", "browser_task", "message", "chat"
    ]
    target: str = ""
    parameters: dict = {}


_STRICT_EXAMPLES = """
Examples:
User: play cry for me on youtube
Intent: play_media

User: open youtube
Intent: open_url

User: search latest AI news
Intent: web_search

User: open notepad
Intent: pc_control

User: remind me to drink water in 1 minute
Intent: reminder

User: what is python
Intent: chat

User: launch chrome
Intent: pc_control

User: go to github
Intent: open_url

User: open github
Intent: open_url

User: open github and complete sign up
Intent: browser_task

User: go to amazon and add a monitor to cart
Intent: browser_task

User: login to gmail and send an email
Intent: browser_task

User: send an email to john@example.com with subject hello saying hi
Intent: message

User: send a slack message to general
Intent: message

User: create a github issue in my repo
Intent: message

User: browse amazon for laptops
Intent: browser_task

User: sign up for a new account on any site
Intent: browser_task

User: register for github with google
Intent: browser_task

User: open spotify
Intent: open_url

User: go to youtube and search for music
Intent: browser_task

User: fill out the contact form
Intent: browser_task
"""


_INTENT_CLIENT = None


def _get_intent_client():
    global _INTENT_CLIENT
    if _INTENT_CLIENT is None:
        _INTENT_CLIENT = instructor.from_openai(
            OpenAI(base_url="http://localhost:11434/v1", api_key="ollama"),
            mode=instructor.Mode.JSON,
        )
    return _INTENT_CLIENT


async def extract_intent(message: str) -> dict:
    try:
        client = _get_intent_client()
        result = client.chat.completions.create(
            model="qwen2.5:7b",
            response_model=IntentResult,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an intent classifier. Output ONLY the intent, target, and parameters.\n\n"
                        "Intents:\n"
                        "- play_media: user wants to play music/video/media\n"
                        "- open_url: ONLY when the user simply wants to navigate to a URL with no further action. Single verb like 'open youtube', 'go to github'.\n"
                        "- web_search: user explicitly says 'search for', 'look up', or wants current/live information from the web\n"
                        "- reminder: user wants to set a reminder/alarm\n"
                        "- pc_control: user wants to open a desktop app (notepad, vscode, chrome, etc.)\n"
                        "- browser_task: ANY multi-step browser operation — signup, login, form filling, shopping, booking, clicking, scrolling, filling fields, submitting forms, OR when the user says 'open X and Y' where Y is an action beyond just opening. This includes any mention of: sign up, sign in, register, create account, login, fill, submit, search for (on a site), add to cart, purchase, book, order.\n"
                        "- message: user wants to send an email, Slack message, or any electronic message. Examples: 'send an email', 'send a message', 'send email to', 'send slack message', 'create a github issue', 'create an issue'.\n"
                        "- chat: general knowledge questions ('what is X', 'who is Y', 'how does Z work'), greetings, conversation, stories, jokes, opinions, advice, explanations. CRITICAL: 'what is X', 'who is Y', 'how does Z work', 'tell me about X' are ALWAYS chat, NOT web_search.\n\n"
                        "CRITICAL RULE: if the user wants to do ANYTHING beyond just navigating to a URL (like sign up, login, search on a site, fill a form, buy something), use browser_task — NOT open_url.\n"
                        "CRITICAL RULE: 'remember that' or 'remember my' is chat (storing info), NOT reminder.\n"
                        f"{_STRICT_EXAMPLES}"
                    ),
                },
                {"role": "user", "content": message},
            ],
            max_retries=3,
        )
        intent_data = result.model_dump()
    except Exception:
        intent_data = {"intent": "chat", "target": message, "parameters": {}}

    # Rule-based overrides for common misclassifications
    msg_lower = message.lower().strip()

    # "open [app]" → pc_control if app is a known desktop app
    if msg_lower.startswith("open "):
        app_name = msg_lower.replace("open ", "", 1).strip()
        if app_name in ("notepad", "calculator", "cmd", "terminal", "vscode", "code", "chrome", "edge", "firefox", "explorer", "settings"):
            if intent_data.get("intent") not in ("pc_control",):
                intent_data["intent"] = "pc_control"
                intent_data["target"] = app_name

    # "what is X", "who is Y" → chat (not web_search), but allow weather/time queries
    if msg_lower.startswith(("what is ", "what are ", "who is ", "who's ",
                              "how does ", "how do ", "how can ", "how to ",
                              "tell me about ", "explain ")):
        if intent_data.get("intent") == "web_search":
            intent_data["intent"] = "chat"

    # "what's the weather/time/news" → keep as web_search if LLM said so
    if msg_lower.startswith("what's "):
        rest = msg_lower[6:]
        if any(w in rest for w in ("weather", "time", "news", "temperature", "forecast", "stock")):
            pass  # keep whatever the LLM decided
        elif intent_data.get("intent") == "web_search":
            intent_data["intent"] = "chat"

    # "remember that" or "remember my" → chat (not reminder)
    if msg_lower.startswith("remember"):
        if intent_data.get("intent") == "reminder":
            intent_data["intent"] = "chat"
            intent_data["target"] = message

    # "create a github issue" or "create issue" → message (not browser_task)
    if any(p in msg_lower for p in ["create a github", "create an issue", "create issue",
                                      "send an email", "send email", "send a message"]):
        if intent_data.get("intent") in ("browser_task", "open_url"):
            intent_data["intent"] = "message"

    # "play [song]" without "search" → play_media (not web_search)
    if msg_lower.startswith("play ") and "search" not in msg_lower:
        if intent_data.get("intent") == "web_search":
            intent_data["intent"] = "play_media"

    return intent_data


# ══════════════════════════════════════════════
#  SMOLAGENTS TOOL FUNCTIONS
# ══════════════════════════════════════════════

@tool
def open_website(name: str) -> str:
    """Opens a website or web app in the browser.
    Use for: youtube, google, whatsapp, gmail, github, amazon, netflix, spotify, twitter, instagram, facebook, reddit, linkedin.
    Args:
        name: The name of the website to open (e.g., youtube, google, gmail, github, amazon)
    """
    sites = {
        "youtube": "https://youtube.com", "google": "https://google.com",
        "whatsapp": "https://web.whatsapp.com", "gmail": "https://gmail.com",
        "github": "https://github.com", "amazon": "https://amazon.com",
        "netflix": "https://netflix.com", "spotify": "https://open.spotify.com",
        "twitter": "https://twitter.com", "instagram": "https://instagram.com",
        "facebook": "https://facebook.com", "reddit": "https://reddit.com",
        "linkedin": "https://linkedin.com",
    }
    for key, url in sites.items():
        if key in name.lower():
            webbrowser.open(url)
            return f"Opened {key}"
    webbrowser.open(f"https://google.com/search?q={urllib.parse.quote(name)}")
    return f"Searched google for {name}"


@tool
def launch_app(name: str) -> str:
    """Launches a desktop application on the computer.
    Use for: notepad, calculator, vscode, cmd, terminal, chrome, edge, firefox, explorer, folder, settings.
    Args:
        name: The application name (e.g., notepad, vscode, chrome, cmd, explorer)
    """
    apps = {
        "notepad": "notepad.exe", "calculator": "calc.exe",
        "vscode": "code", "code": "code",
        "cmd": "cmd.exe", "terminal": "cmd.exe",
        "chrome": "chrome.exe", "edge": "msedge.exe",
        "firefox": "firefox.exe", "explorer": "explorer.exe",
        "folder": "explorer.exe",
    }
    for key, exe in apps.items():
        if key in name.lower():
            try:
                subprocess.Popen([exe])
                return f"Launched {key}"
            except Exception as e:
                return f"Failed to launch {key}: {e}"
    return f"Unknown app: {name}"


@tool
def play_media(query: str) -> str:
    """Plays music, video, or media from YouTube.
    Use when the user asks to play a song, video, music, or any media.
    Args:
        query: The song or video name to search and play
    """
    q = urllib.parse.quote(query)
    search_url = f"https://www.youtube.com/results?search_query={q}"
    try:
        r = httpx.get(search_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        match = re.search(r"/watch\?v=([a-zA-Z0-9_-]{11})", r.text)
        if match:
            video_url = f"https://www.youtube.com/watch?v={match.group(1)}"
            webbrowser.open(video_url)
            return f"Playing {query}"
    except Exception:
        pass
    webbrowser.open(search_url)
    return f"Searching YouTube for {query}"


@tool
def web_search(query: str) -> str:
    """Searches the web for information.
    Use when the user wants to search for news, facts, information, or anything online.
    Args:
        query: The search query
    """
    try:
        q = urllib.parse.quote(query)
        r = httpx.get(
            f"http://localhost:8888/search?q={q}&format=json",
            timeout=15,
        )
        data = r.json()
        results = []
        for item in data.get("results", [])[:5]:
            title = item.get("title", "")
            content = item.get("content", "")
            if title and content:
                results.append(f"{title}: {content[:300]}")
            elif content:
                results.append(content[:300])
        if results:
            return "Search results: " + " | ".join(results)
        return f"No search results found for {query}"
    except Exception as e:
        return f"Search failed: {e}"


_KNOWN_SITES = {
    "github": "https://github.com",
    "google": "https://google.com",
    "youtube": "https://youtube.com",
    "gmail": "https://gmail.com",
    "amazon": "https://amazon.com",
    "netflix": "https://netflix.com",
    "spotify": "https://open.spotify.com",
    "twitter": "https://twitter.com",
    "instagram": "https://instagram.com",
    "facebook": "https://facebook.com",
    "reddit": "https://reddit.com",
    "linkedin": "https://linkedin.com",
    "whatsapp": "https://web.whatsapp.com",
}


def _extract_url(task: str) -> str:
    """Extract a URL from a task description."""
    url = task.strip()
    if not url.startswith("http"):
        for site, site_url in _KNOWN_SITES.items():
            if site in url.lower():
                url = site_url
                break
        else:
            m = re.search(r'(?:https?://\S+)', url)
            if m:
                url = m.group(0)
            else:
                url = "https://google.com/search?q=" + urllib.parse.quote(task)
    return url


async def _browser_automation(task: str) -> str:
    """Core async Playwright browser.
    Extracts a URL from the task description and navigates to it.
    Fresh Playwright context per call — avoids stale browser crashes.
    """
    try:
        url = _extract_url(task)
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"]
            )
            page = await browser.new_page()
            await page.goto(url, timeout=60000, wait_until="domcontentloaded")
            title = await page.title()
            await browser.close()
            return f"Navigated to {url}: {title}"
    except Exception as e:
        return f"Browser error: {e}"


def _browser_automation_sync(task: str) -> str:
    """Synchronous wrapper: runs Playwright in a dedicated event loop
    (avoids Windows event loop conflicts when called from FastAPI routes)."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_browser_automation(task))
    finally:
        loop.close()


@tool
def browser_automation(task: str) -> str:
    """Opens a URL in the browser using Playwright.
    Use for: navigating to a specific webpage to see its content or interact with it.
    Args:
        task: A URL or description starting with 'go to', 'open', or a direct URL
    """
    return _browser_automation_sync(task)


_ACTION_AGENT = None


def _get_action_agent():
    global _ACTION_AGENT
    if _ACTION_AGENT is None:
        model = LiteLLMModel(model_id="ollama/llama3.1:8b", api_base="http://localhost:11434")
        _ACTION_AGENT = ToolCallingAgent(
            tools=[play_media, open_website, web_search, launch_app, browser_automation] + COMPOSIO_TOOLS,
            model=model,
            instructions=(
                "You are JARVIS's action executor. You have full autonomy to decide which tools to use. "
                "Users often ask for MULTIPLE actions in one message. "
                "You MUST identify and execute EVERY distinct action requested — do NOT stop after just one. "
                "Use the right tool for each task: play_media for music/video playback, "
                "open_website for navigating to a URL (simple open), web_search for information lookups, "
                "launch_app for desktop applications, "
                "browser_automation for visiting a specific URL in the Playwright browser (use this instead of open_website when the user wants to interact with the page content). "
                "You also have access to external service tools via Composio: gmail_send_email (requires Gmail OAuth), "
                "github_create_issue (requires GitHub OAuth), slack_send_message (requires Slack OAuth). "
                "Be honest about what you can do — if a task is too complex, say so."
            ),
            max_steps=12,
        )
    return _ACTION_AGENT


async def execute_action(intent_data: dict, message: str = "", db=None, user=None) -> dict:
    intent = intent_data.get("intent", "chat")

    # Handle reminders via old path (needs db+user)
    if intent in ("reminder", "set_reminder"):
        target = intent_data.get("target", "")
        if db is not None and user is not None:
            try:
                from reminders.manager import create_reminder
                params = intent_data.get("parameters", {})
                time_str = params.get("time", "")
                remind_at = parse_time_relative(time_str)
                r = await create_reminder(db, user, target, remind_at, f"Reminder: {target}")
                return {"executed": True, "action": "reminder_created", "title": target, "remind_at": remind_at.isoformat(), "id": r.id}
            except Exception as e:
                return {"executed": False, "error": f"Failed to create reminder: {e}"}
        return {"executed": True, "action": f"Reminder noted: {target}"}

    # Browser task → use synchronous wrapper (avoids Windows event loop conflict with Playwright)
    if intent == "browser_task":
        target = intent_data.get("target") or message or ""
        if target:
            result = await asyncio.to_thread(_browser_automation_sync, target)
            if "error" in result.lower() or "failed" in result.lower() or "can't" in result.lower():
                return {"executed": True, "error": result}
            return {"executed": True, "action": result}
        return {"executed": False, "error": "no browser task target"}

    # Open URL → direct webbrowser open (avoids agent model failures)
    if intent == "open_url":
        target = intent_data.get("target") or message or ""
        if not target:
            # Try to extract a URL/name from the message
            for site, url in _KNOWN_SITES.items():
                if site in message.lower():
                    target = site
                    break
        if target:
            site_url = _KNOWN_SITES.get(target.lower(), "")
            if site_url:
                webbrowser.open(site_url)
                return {"executed": True, "action": f"Opened {target}"}
            # Treat as direct URL
            if not target.startswith("http"):
                target = "https://" + target
            webbrowser.open(target)
            return {"executed": True, "action": f"Navigated to {target}"}
        return {"executed": False, "error": "no URL target"}

    # Play media → direct YouTube search + open (avoids agent model failures)
    if intent == "play_media":
        target = intent_data.get("target") or message or ""
        if not target:
            return {"executed": False, "error": "no media target"}
        try:
            q = urllib.parse.quote(target)
            search_url = f"https://www.youtube.com/results?search_query={q}"
            r = httpx.get(search_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            match = re.search(r"/watch\?v=([a-zA-Z0-9_-]{11})", r.text)
            if match:
                video_url = f"https://www.youtube.com/watch?v={match.group(1)}"
                webbrowser.open(video_url)
                return {"executed": True, "action": f"Playing {target} on YouTube"}
            return {"executed": True, "action": f"Opened YouTube search for {target}"}
        except Exception as e:
            return {"executed": False, "error": f"Failed to play media: {e}"}

    # Chat intent → no action
    if intent == "chat":
        return {"executed": False, "action": "chat_only"}

    # Everything else → smolagens agent decides tools and handles multi-step
    try:
        agent = _get_action_agent()
        msg = message or intent_data.get("target", "")
        if not msg:
            return {"executed": False, "error": "no message to act on"}
        loop = asyncio.get_event_loop()
        future = loop.run_in_executor(None, agent.run, msg)
        result = await asyncio.wait_for(future, timeout=90)
        return {"executed": True, "action": str(result)}
    except asyncio.TimeoutError:
        return {"executed": False, "error": "Agent timed out after 90s"}
    except Exception as e:
        return {"executed": False, "error": str(e)}


def parse_time_relative(time_str: str):
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    if not time_str:
        return now + timedelta(hours=1)
    tl = time_str.lower()
    if "minute" in tl:
        nums = re.findall(r'\d+', tl)
        minutes = int(nums[0]) if nums else 1
        return now + timedelta(minutes=minutes)
    if "hour" in tl:
        nums = re.findall(r'\d+', tl)
        hours = int(nums[0]) if nums else 1
        return now + timedelta(hours=hours)
    if "tomorrow" in tl:
        nums = re.findall(r'\d+', tl)
        if nums:
            return now + timedelta(days=1, hours=int(nums[0]) % 24)
        return now + timedelta(days=1)
    if "today" in tl or "now" in tl:
        nums = re.findall(r'\d+', tl)
        if nums:
            return now.replace(hour=int(nums[0]) % 24, minute=0, second=0)
        return now + timedelta(minutes=1)
    return now + timedelta(hours=1)


# ==============================================
#  ROUTES — ASSISTANT
# ==============================================
@app.post("/api/chat")
async def chat(
    req: ChatRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token)
):
    from core.database import ChatHistory
    from core.model_router import route_request, get_router_model
    from core.llm_router import router as llm_router, health_check

    # Step 1: Check LLM connectivity
    if not await health_check():
        # fallback: direct Ollama ping
        try:
            ollama_check = httpx.get("http://localhost:11434/api/tags", timeout=2)
            if ollama_check.status_code != 200:
                return JSONResponse(
                    status_code=503,
                    content={"response": "Ollama is offline. Run: ollama serve", "intent": {"intent": "chat"}, "action": {"executed": False}}
                )
        except (httpx.ConnectError, httpx.TimeoutException):
            return JSONResponse(
                status_code=503,
                content={"response": "Ollama is offline. Run: ollama serve", "intent": {"intent": "chat"}, "action": {"executed": False}}
            )

    # Step 2: Privacy routing (tier-based model selection + PII sanitization)
    model_name, privacy_tier, sanitized_message = route_request(req.message, force_tier=req.tier)

    # Step 3: Extract intent using LLM
    intent_data = await extract_intent(sanitized_message)

    # Step 4: Execute real action if needed
    action_result = await execute_action(intent_data, message=req.message, db=db, user=user)

    # Step 4: Determine current intent for history scoping
    current_intent = intent_data.get("intent", "chat")

    # Step 5: If action failed, respond directly without LLM (avoid hallucination)
    if action_result.get("executed") and action_result.get("error"):
        reply = f"I tried but couldn't complete that: {action_result['error']}"
        result = {
            "response": reply,
            "intent": intent_data,
            "action": action_result,
            "model": model_name,
            "privacy_tier": privacy_tier.value if privacy_tier else "LOCAL",
        }
        db.add(ChatHistory(user_id=user.id, role="user", message=sanitized_message, intent=current_intent))
        db.add(ChatHistory(user_id=user.id, role="assistant", message=result["response"], intent=current_intent))
        await db.commit()
        from notes.activity_tracker import activity_tracker
        await activity_tracker.log(db, user.id, "voice_command", f"Chat: {sanitized_message[:100]}")
        return result

    # Build action context: include last action done by user for recall
    action_context = ""
    if action_result.get("executed") and not action_result.get("error") and current_intent != "chat":
        action_context = f"\n[SYSTEM: Action executed: {json.dumps(action_result)}]"

    # Check if user is asking about previous actions ("what did you do")
    asking_about_actions = any(phrase in req.message.lower() for phrase in
        ["what did you do", "what you did", "what have you done", "what happened", "what did i ask"])

    if asking_about_actions:
        # Fetch last 5 actions across any intent for recall
        try:
            from datetime import datetime, timedelta
            from sqlalchemy import select
            from core.database import ChatHistory
            cutoff = datetime.utcnow() - timedelta(minutes=30)
            action_result_db = await db.execute(
                select(ChatHistory)
                .where(ChatHistory.user_id == user.id)
                .where(ChatHistory.timestamp >= cutoff)
                .where(ChatHistory.intent != "chat")
                .order_by(ChatHistory.timestamp.desc())
                .limit(5)
            )
            recent_actions = list(action_result_db.scalars().all())
            if recent_actions:
                action_lines = []
                for a in reversed(recent_actions):
                    action_lines.append(f"[{a.timestamp.strftime('%H:%M')}] {a.role}: {a.message[:200]}")
                action_context += "\n[SYSTEM: Recent non-chat history:\n" + "\n".join(action_lines) + "\n]"
        except Exception:
            pass

    # Step 6: Build conversation history context (full history, all intents)
    messages = [
        {"role": "system", "content": (
            "You are JARVIS, a personal AI assistant. "
            "Be concise and direct. "
            "You remember our full conversation — use previous messages to answer contextually. "
            "If the user asks about something you discussed earlier, use that history. "
            "Tell the user what you actually did — do NOT invent details that didn't happen."
        ) + action_context},
    ]
    try:
        from sqlalchemy import select
        from core.database import ChatHistory
        result = await db.execute(
            select(ChatHistory)
            .where(ChatHistory.user_id == user.id)
            .order_by(ChatHistory.timestamp.desc())
            .limit(15)
        )
        recent = list(result.scalars().all())
        recent.reverse()
        for turn in recent:
            messages.append({"role": turn.role, "content": turn.message})
    except Exception:
        pass
    messages.append({"role": "user", "content": sanitized_message})

    # Step 6: Get LLM response via LiteLLM router
    try:
        model_group = "cloud" if model_name == "cloud" else get_router_model(intent_data.get("intent", "chat"))
        reply = await llm_router.acompletion(
            model=model_group,
            messages=messages,
            timeout=120,
        )
        reply = reply.choices[0].message.content
    except Exception as e:
        reply = ""
        if action_result.get("executed"):
            reply = f"Action completed: {action_result.get('action', '')}"
        else:
            reply = f"Model error: {e}"

    # Step 7: Build response with privacy metadata
    result = {
        "response": reply,
        "intent": intent_data,
        "action": action_result,
        "model": model_name,
        "privacy_tier": privacy_tier.value if privacy_tier else "LOCAL",
    }

    db.add(ChatHistory(user_id=user.id, role="user", message=sanitized_message, intent=current_intent))
    db.add(ChatHistory(user_id=user.id, role="assistant", message=result["response"], intent=current_intent))
    await db.commit()

    from notes.activity_tracker import activity_tracker
    await activity_tracker.log(db, user.id, "voice_command", f"Chat: {sanitized_message[:100]}")

    return result


@app.get("/api/chat/history")
async def get_chat_history(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token),
    limit: int = 50
):
    from sqlalchemy import select
    from core.database import ChatHistory
    result = await db.execute(
        select(ChatHistory)
        .where(ChatHistory.user_id == user.id)
        .order_by(ChatHistory.timestamp.desc())
        .limit(limit)
    )
    messages = result.scalars().all()
    return [{"role": m.role, "message": m.message, "ts": m.timestamp} for m in reversed(messages)]


# ==============================================
#  ROUTES — REMINDERS
# ==============================================
@app.get("/api/reminders")
async def list_reminders(db: AsyncSession = Depends(get_db), user: User = Depends(verify_token)):
    from reminders.manager import get_user_reminders
    items = await get_user_reminders(db, user)
    return [{"id": r.id, "title": r.title, "remind_at": r.remind_at, "repeat": r.repeat, "description": r.description} for r in items]

@app.post("/api/reminders")
async def create_reminder_route(
    req: ReminderCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token)
):
    from reminders.manager import create_reminder
    r = await create_reminder(db, user, req.title, req.remind_at, req.description, req.repeat)
    return {"id": r.id, "title": r.title, "remind_at": r.remind_at}

@app.delete("/api/reminders/{reminder_id}")
async def delete_reminder_route(
    reminder_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token)
):
    from reminders.manager import delete_reminder
    success = await delete_reminder(db, user, reminder_id)
    if not success:
        raise HTTPException(404, "Reminder not found")
    return {"deleted": True}


# ==============================================
#  ROUTES — NOTES
# ==============================================
@app.get("/api/notes")
async def list_notes(db: AsyncSession = Depends(get_db), user: User = Depends(verify_token)):
    from notes.activity_tracker import notes_manager
    items = await notes_manager.get_all(db, user)
    return [{"id": n.id, "title": n.title, "content": n.content, "tags": n.tags, "updated_at": n.updated_at} for n in items]

@app.post("/api/notes")
async def create_note(req: NoteCreate, db: AsyncSession = Depends(get_db), user: User = Depends(verify_token)):
    from notes.activity_tracker import notes_manager
    n = await notes_manager.create(db, user, req.title, req.content, req.tags)
    return {"id": n.id, "title": n.title}

@app.put("/api/notes/{note_id}")
async def update_note(note_id: int, req: NoteUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(verify_token)):
    from notes.activity_tracker import notes_manager
    n = await notes_manager.update(db, user, note_id, req.title, req.content)
    if not n:
        raise HTTPException(404, "Note not found")
    return {"id": n.id, "title": n.title}

@app.delete("/api/notes/{note_id}")
async def delete_note(note_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(verify_token)):
    from notes.activity_tracker import notes_manager
    success = await notes_manager.delete(db, user, note_id)
    if not success:
        raise HTTPException(404, "Note not found")
    return {"deleted": True}


# ==============================================
#  ROUTES — ACTIVITY & SUMMARY
# ==============================================
@app.get("/api/activity/today")
async def today_activity(db: AsyncSession = Depends(get_db), user: User = Depends(verify_token)):
    from notes.activity_tracker import activity_tracker
    items = await activity_tracker.get_today(db, user.id)
    return [{"type": a.activity_type, "description": a.description, "ts": a.timestamp} for a in items]

@app.get("/api/activity/summary")
async def daily_summary(db: AsyncSession = Depends(get_db), user: User = Depends(verify_token)):
    from notes.activity_tracker import summary_generator
    summary = await summary_generator.generate(db, user)
    return {
        "date": summary.date,
        "summary": summary.summary,
        "productivity_score": summary.productivity_score,
        "data": summary.raw_data
    }


# ==============================================
#  ROUTES — MESSAGING AUTOMATION
# ==============================================
@app.post("/api/message/send")
async def send_message(
    req: MessageRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token)
):
    from automation.messaging import messaging
    from notes.activity_tracker import activity_tracker

    if req.platform == "whatsapp":
        success = messaging.send_whatsapp(req.recipient, req.message)
    elif req.platform == "instagram":
        success = messaging.send_instagram_dm(req.recipient, req.message)
    else:
        raise HTTPException(400, "Platform must be 'whatsapp' or 'instagram'")

    await activity_tracker.log(
        db, user.id, "message_sent",
        f"Sent {req.platform} message to {req.recipient}"
    )
    return {"success": success, "platform": req.platform, "recipient": req.recipient}


# ==============================================
#  ROUTES — FACE RECOGNITION
# ==============================================
@app.post("/api/faces/register")
async def register_face(
    person_name: str = Form(...),
    relation: str = Form("unknown"),
    info: str = Form(""),
    access_level: str = Form("visitor"),
    images: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token)
):
    from vision.face_recognition import face_recognizer
    frames = []
    for img_file in images:
        data = await img_file.read()
        nparr = np.frombuffer(data, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if frame is not None:
            frames.append(frame)

    if not frames:
        raise HTTPException(400, "No valid images provided")

    kf = await face_recognizer.register_face(db, user, person_name, frames, relation, info, access_level)
    return {"id": kf.id, "person_name": kf.person_name, "image_count": kf.image_count}


@app.post("/api/faces/identify")
async def identify_face(
    image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(verify_token)
):
    from vision.face_recognition import face_recognizer
    data = await image.read()
    nparr = np.frombuffer(data, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    result = await face_recognizer.identify_and_lookup(db, user, frame)
    return result

@app.get("/api/faces")
async def list_faces(db: AsyncSession = Depends(get_db), user: User = Depends(verify_token)):
    from sqlalchemy import select
    from core.database import KnownFace
    result = await db.execute(select(KnownFace).where(KnownFace.owner_id == user.id))
    faces = result.scalars().all()
    return [{"id": f.id, "name": f.person_name, "relation": f.relation, "access_level": f.access_level, "image_count": f.image_count} for f in faces]


# ==============================================
#  ROUTES — MEDIA PLAYER
# ==============================================
@app.get("/api/media/status")
async def media_status():
    from media.player import media_player
    return media_player.get_status()

@app.post("/api/media/play")
async def media_play(track_index: Optional[int] = None, query: Optional[str] = None):
    from media.player import media_player
    if query:
        found = media_player.play_by_name(query)
        return {"playing": found}
    elif track_index is not None:
        media_player.play_by_index(track_index)
    else:
        media_player.play()
    return {"playing": True}

@app.post("/api/media/pause")
async def media_pause():
    from media.player import media_player
    media_player.pause()
    return {"paused": True}

@app.post("/api/media/next")
async def media_next():
    from media.player import media_player
    media_player.next_track()
    return media_player.get_status()

@app.post("/api/media/volume/{volume}")
async def set_volume(volume: int):
    from media.player import media_player
    media_player.set_volume(volume)
    return {"volume": volume}

@app.get("/api/media/playlist")
async def get_playlist():
    from media.player import media_player
    return media_player.get_playlist()

@app.get("/api/media/suggest/{mood}")
async def suggest_music(mood: str):
    from media.player import music_suggester, media_player
    status = media_player.get_status()
    if mood == "similar" and status.get("track"):
        return music_suggester.suggest_similar(status["track"])
    return music_suggester.suggest_by_mood(mood)


# ==============================================
#  ROUTES — FILE MANAGER
# ==============================================
@app.get("/api/files")
async def list_files(path: str = "~", user: User = Depends(verify_token)):
    import os
    resolved = os.path.expanduser(path)
    if not os.path.exists(resolved):
        raise HTTPException(404, "Path not found")
    if not os.path.isdir(resolved):
        raise HTTPException(400, "Not a directory")

    entries = []
    for entry in os.scandir(resolved):
        try:
            entries.append({
                "name":     entry.name,
                "is_dir":   entry.is_dir(),
                "size":     entry.stat().st_size if entry.is_file() else 0,
                "modified": datetime.fromtimestamp(entry.stat().st_mtime).isoformat()
            })
        except PermissionError:
            raise HTTPException(403, "Permission denied for this path")

    return {"path": resolved, "entries": sorted(entries, key=lambda x: (not x["is_dir"], x["name"]))}


@app.post("/api/files/upload")
async def upload_file(path: str = Form(...), file: UploadFile = File(...), user: User = Depends(verify_token)):
    import os
    dest_dir = os.path.expanduser(path)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, file.filename)
    data = await file.read()
    with open(dest, "wb") as f:
        f.write(data)
    return {"saved_to": dest, "size": len(data)}


# ==============================================
#  ROUTES — VOICE (STT/TTS)
# ==============================================
from assistant.stt import get_stt
from assistant.tts import get_tts

@app.post("/stt")
async def speech_to_text(file: UploadFile = File(...), user: User = Depends(verify_token)):
    audio_data = await file.read()
    text = get_stt().transcribe(audio_data)
    if not text:
        raise HTTPException(500, "Transcription failed")
    return {"transcript": text}

@app.post("/tts")
async def text_to_speech(req: dict):
    text = req.get("text", "")
    if not text:
        raise HTTPException(400, "Text is required")
    
    audio_bytes = get_tts().synthesize(text)
    if not audio_bytes:
        raise HTTPException(500, "TTS generation failed")
    
    from fastapi.responses import Response
    return Response(content=audio_bytes, media_type="audio/wav")

@app.get("/tts/stream")
async def tts_stream_websocket(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            data = await ws.receive_json()
            text = data.get("text", "")
            if text:
                audio_bytes = get_tts().synthesize(text)
                await ws.send_bytes(audio_bytes)
    except Exception as e:
        print(f"[TTS Stream] Error: {e}")
        await ws.close()


# ==============================================
#  WEBSOCKET — VOICE PIPELINE (STT + LLM + TTS)
# ==============================================
@app.websocket("/voice")
async def voice_websocket(ws: WebSocket):
    """WebSocket voice endpoint: receives raw audio, returns WAV audio.
    Flow: mic audio -> STT -> llm_router -> TTS -> speaker audio
    """
    from assistant.voice_pipeline import get_pipeline

    await ws.accept()
    pipeline = get_pipeline()
    try:
        while True:
            audio_bytes = await ws.receive_bytes()
            if not audio_bytes or len(audio_bytes) < 1024:
                continue
            audio_out = await pipeline.process_audio(audio_bytes)
            if audio_out:
                await ws.send_bytes(audio_out)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[Voice WS] Error: {e}")
        await ws.close()


# ==============================================
#  ROUTES — BROWSER AGENT
# ==============================================
@app.websocket("/ws/{device_id}/{user_id}")
async def websocket_endpoint(ws: WebSocket, device_id: str, user_id: int):
    from network.websocket_server import connection_manager, handle_message

    await connection_manager.connect(ws, device_id, user_id)
    try:
        await ws.send_json({
            "type": "connected",
            "payload": {
                "device_id": device_id,
                "user_id": user_id,
                "server_time": datetime.utcnow().isoformat()
            }
        })
        while True:
            raw = await ws.receive_text()
            await handle_message(ws, device_id, user_id, raw)
    except WebSocketDisconnect:
        connection_manager.disconnect(device_id, user_id)


# ==============================================
#  WEBSOCKET — CHAT STREAM (for real-time streaming AI responses)
# ==============================================
@app.websocket("/ws/chat_stream")
async def chat_stream_websocket(ws: WebSocket):
    """
    Unified WebSocket handler for chat + actions.
    Uses LLM intent extraction → execute → conversational response.
    """
    from core.model_router import route_request
    from assistant.engine import jarvis
    
    await ws.accept()
    try:
        while True:
            raw = await ws.receive_text()
            import json
            msg = json.loads(raw)
            msg_type = msg.get('type')
            
            if msg_type == 'chat':
                text = msg.get('text', '')
                model, tier, processed_query = route_request(text)
                
                # 1. Process text (LLM Intent → Execute Action → LLM Response)
                result = await jarvis.process_text(processed_query, user_id=1, model=model)
                response_text = result.get('response', '')
                intent = result.get('intent', 'general_chat')
                
                # 2. Stream tokens (simulated word-by-word)
                words = response_text.split()
                for i, word in enumerate(words):
                    await ws.send_json({
                        'type': 'stream_token',
                        'token': word + ' ',
                        'complete': i == len(words) - 1,
                        'privacy_tier': tier.value,
                        'model': model,
                        'intent': intent,
                    })
                    # Yield slightly for a smoother "streaming" UI effect if desired
                    # await asyncio.sleep(0.02)
                
                await ws.send_json({
                    'type': 'tier_status',
                    'tier': f'Tier {tier.value}',
                    'status': 'completed'
                })
            elif msg_type == 'ping':
                await ws.send_json({'type': 'pong'})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f'[WS Chat] Error: {e}')
        try:
            await ws.close()
        except:
            pass


# ==============================================
#  ROUTES — WEB INTELLIGENCE
# ==============================================
from tools.search_tool import search_engine, decision_gate

@app.post("/search")
async def search_route(req: dict, user: User = Depends(verify_token)):
    query = req.get("query", "")
    if not query:
        raise HTTPException(400, "Query is required")
    
    # Check decision gate
    should_search = decision_gate.should_search(query, req.get("confidence", 1.0))
    if not should_search and not req.get("force", False):
        return {"searched": False, "reason": "Decision gate rejected search"}
    
    results = search_engine.search(query)
    scraped = search_engine.scrape_top(results)
    
    return {
        "searched": True,
        "results": [vars(r) for r in results],
        "context": scraped
    }

@app.post("/browse")
async def browser_agent(req: dict, user: User = Depends(verify_token)):
    """
    Upgraded browser agent endpoint using browser-use.
    """
    instruction = req.get('instruction', req.get('task', ''))
    if not instruction:
        raise HTTPException(400, "instruction is required")
    
    from tools.browser_tool import JarvisBrowser
    browser = JarvisBrowser()
    
    result = await browser.execute(instruction)
    return result


# ==============================================
#  ROUTES — COMPUTER CONTROL
# ==============================================
from pc_agent.computer_agent import computer_agent

@app.post("/computer")
async def computer_control(req: dict, user: User = Depends(verify_token)):
    instruction = req.get("instruction", "")
    if not instruction:
        raise HTTPException(400, "Instruction is required")
    
    confirm = req.get("confirm", True)
    result = computer_agent.execute_natural_language(instruction, confirm=confirm)
    return result

# ==============================================
#  ROUTES — EXECUTIONS
# ==============================================
@app.get("/executions/recent")
async def get_recent_executions(n: int = 10):
    from autonomy.l3_executor.executor_layer import ExecutorLayer
    layer = ExecutorLayer()
    return {"executions": layer.recent(n)}


# ==============================================
#  RUN
# ==============================================
if __name__ == "__main__":
    import uvicorn
    print(f"\n[JARVIS] Server starting at http://{HOST}:{PORT}")
    print(f"[JARVIS] API docs at  http://localhost:{PORT}/docs\n")
    uvicorn.run("core.main:app", host=HOST, port=PORT, reload=True, log_level="info")
