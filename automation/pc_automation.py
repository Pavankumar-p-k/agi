# automation/pc_automation.py
#
# JARVIS PC Automation Engine
# ─────────────────────────────────────────────────────────────
#  1. Contacts DB   — save name + phone / instagram / whatsapp
#  2. WhatsApp      — send to any saved contact or new number
#  3. Instagram DM  — DM any saved contact or @username
#  4. Web browser   — open URL, Google, YouTube, Maps
#  5. App launcher  — open any Windows app by name
#  6. System ctrl   — volume, screenshot, lock, sleep, shutdown
#  7. NLP parser    — understands natural language commands
# ─────────────────────────────────────────────────────────────

import re, os, json, time, subprocess, webbrowser, platform
from pathlib import Path
from datetime import datetime
from typing import Optional
from urllib.parse import quote_plus

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import pyautogui


# ══════════════════════════════════════════════════════════
#  CONTACTS DATABASE
# ══════════════════════════════════════════════════════════

CONTACTS_FILE = Path("data/contacts.json")

class ContactsDB:
    def __init__(self):
        CONTACTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        self._c: dict = {}
        if CONTACTS_FILE.exists():
            with open(CONTACTS_FILE) as f:
                self._c = json.load(f)
        print(f"[Contacts] {len(self._c)} contacts loaded")

    def _save(self):
        with open(CONTACTS_FILE, "w") as f:
            json.dump(self._c, f, indent=2)

    def add(self, name: str, phone: str = "", instagram: str = "",
            whatsapp: str = "", email: str = "", notes: str = "") -> dict:
        key = name.lower().strip()
        self._c[key] = {
            "name":      name.strip(),
            "phone":     phone.strip(),
            "whatsapp":  whatsapp.strip() or phone.strip(),
            "instagram": instagram.strip().lstrip("@"),
            "email":     email.strip(),
            "notes":     notes.strip(),
            "added_at":  datetime.now().isoformat(),
        }
        self._save()
        print(f"[Contacts] Saved: {name}")
        return self._c[key]

    def get(self, name: str) -> Optional[dict]:
        """Find by exact or fuzzy name match."""
        k = name.lower().strip()
        if k in self._c:
            return self._c[k]
        for key, val in self._c.items():
            if k in key or key in k:
                return val
        return None

    def delete(self, name: str) -> bool:
        k = name.lower().strip()
        if k in self._c:
            del self._c[k]; self._save(); return True
        return False

    def list_all(self) -> list:
        return sorted(self._c.values(), key=lambda x: x["name"])

    def search(self, q: str) -> list:
        q = q.lower()
        return [c for c in self._c.values()
                if q in c["name"].lower()
                or q in c.get("phone","")
                or q in c.get("instagram","").lower()]

contacts_db = ContactsDB()


# ══════════════════════════════════════════════════════════
#  SHARED CHROME BROWSER
# ══════════════════════════════════════════════════════════

class BrowserManager:
    def __init__(self):
        self._driver: Optional[webdriver.Chrome] = None
        self._profile = os.path.expanduser("~/.jarvis_browser_profile")

    def get(self) -> webdriver.Chrome:
        if self._driver:
            try: _ = self._driver.title; return self._driver
            except: self._driver = None

        opts = Options()
        opts.add_argument(f"--user-data-dir={self._profile}")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)
        svc = Service(ChromeDriverManager().install())
        self._driver = webdriver.Chrome(service=svc, options=opts)
        return self._driver

    def open(self, url: str, new_tab: bool = True) -> bool:
        try:
            d = self.get()
            if new_tab and d.window_handles:
                d.execute_script("window.open('');")
                d.switch_to.window(d.window_handles[-1])
            d.get(url)
            print(f"[Browser] Opened: {url}")
            return True
        except Exception as e:
            print(f"[Browser] Fallback system browser - {e}")
            webbrowser.open(url); return True

    def google(self, q: str):
        return self.open(f"https://www.google.com/search?q={quote_plus(q)}")

    def youtube_search(self, q: str):
        return self.open(f"https://www.youtube.com/results?search_query={quote_plus(q)}")

    def youtube_play(self, q: str):
        """Search and auto-click first video."""
        self.youtube_search(q)
        try:
            d = self.get()
            time.sleep(2)
            WebDriverWait(d, 10).until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, "ytd-video-renderer a#thumbnail"))).click()
        except Exception:
            pass

    def maps(self, place: str):
        return self.open(f"https://www.google.com/maps/search/{quote_plus(place)}")

browser = BrowserManager()


# ══════════════════════════════════════════════════════════
#  WHATSAPP SENDER
# ══════════════════════════════════════════════════════════

class WhatsAppSender:
    _ready = False

    def _ensure(self) -> webdriver.Chrome:
        d = browser.get()
        if not self._ready:
            if "web.whatsapp.com" not in d.current_url:
                d.get("https://web.whatsapp.com")
            try:
                WebDriverWait(d, 90).until(
                    EC.presence_of_element_located(
                        (By.XPATH, '//div[@contenteditable="true"][@data-tab="3"]')))
                self._ready = True; print("[WhatsApp] Ready")
            except:
                print("[WhatsApp] Scan QR code in browser window...")
        return d

    def send_by_name(self, contact_name: str, message: str) -> dict:
        """Send using WhatsApp contact name (searches in WA search bar)."""
        try:
            d = self._ensure()
            box = WebDriverWait(d, 10).until(
                EC.element_to_be_clickable(
                    (By.XPATH, '//div[@contenteditable="true"][@data-tab="3"]')))
            box.click(); box.clear()
            box.send_keys(contact_name); time.sleep(1.5)

            WebDriverWait(d, 8).until(
                EC.element_to_be_clickable(
                    (By.XPATH, f'//span[@title="{contact_name}"]'))).click()
            time.sleep(1)

            msg_box = WebDriverWait(d, 8).until(
                EC.element_to_be_clickable(
                    (By.XPATH, '//div[@contenteditable="true"][@data-tab="10"]')))
            msg_box.click()
            for line in message.split("\n"):
                msg_box.send_keys(line)
                msg_box.send_keys(Keys.SHIFT + Keys.ENTER)
            msg_box.send_keys(Keys.ENTER)

            print(f"[WhatsApp] Sent -> {contact_name}: {message[:50]}")
            return {"success": True, "to": contact_name}
        except Exception as e:
            print(f"[WhatsApp] [FAIL] {e}")
            return {"success": False, "error": str(e)}

    def send_by_number(self, phone: str, message: str) -> dict:
        """Send using phone number (no need to be in WA contacts)."""
        clean = re.sub(r"[^\d+]", "", phone)
        if not clean.startswith("+"): clean = "+91" + clean  # ← change country code if needed
        try:
            d = browser.get()
            d.get(f"https://web.whatsapp.com/send?phone={clean}&text={quote_plus(message)}")
            time.sleep(4)
            WebDriverWait(d, 20).until(
                EC.element_to_be_clickable(
                    (By.XPATH, '//button[@data-testid="compose-btn-send"]'))).click()
            print(f"[WhatsApp] Sent -> {clean}: {message[:50]}")
            return {"success": True, "to": clean}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def send_to_contact(self, name: str, message: str) -> dict:
        """Try JARVIS contacts DB, then WhatsApp search, then phone number."""
        c = contacts_db.get(name)
        if c:
            wa_name = c.get("whatsapp") or c["name"]
            result  = self.send_by_name(wa_name, message)
            if not result["success"] and c.get("phone"):
                result = self.send_by_number(c["phone"], message)
            return result
        # Not in JARVIS contacts — try directly in WhatsApp
        return self.send_by_name(name, message)

wa = WhatsAppSender()


# ══════════════════════════════════════════════════════════
#  INSTAGRAM DM SENDER
# ══════════════════════════════════════════════════════════

class InstagramSender:
    _ready = False

    def _ensure(self) -> webdriver.Chrome:
        d = browser.get()
        if not self._ready:
            d.get("https://www.instagram.com"); time.sleep(2)
            try:
                d.find_element(By.XPATH, '//a[@href="/direct/inbox/"]')
                self._ready = True
            except Exception:
                un = os.getenv("INSTAGRAM_USERNAME","")
                pw = os.getenv("INSTAGRAM_PASSWORD","")
                if un and pw:
                    try:
                        WebDriverWait(d,10).until(
                            EC.element_to_be_clickable((By.NAME,"username"))).send_keys(un)
                        d.find_element(By.NAME,"password").send_keys(pw + Keys.ENTER)
                        time.sleep(4); self._ready = True
                    except Exception:
                        pass
        return d

    def send(self, username: str, message: str) -> dict:
        username = username.lstrip("@")
        try:
            d = self._ensure()
            d.get("https://www.instagram.com/direct/new/"); time.sleep(2)
            s = WebDriverWait(d,10).until(
                EC.element_to_be_clickable((By.NAME,"queryBox")))
            s.send_keys(username); time.sleep(1.5)
            WebDriverWait(d,8).until(
                EC.element_to_be_clickable(
                    (By.XPATH, f'//span[contains(text(),"{username}")]'))).click()
            time.sleep(0.8)
            WebDriverWait(d,8).until(
                EC.element_to_be_clickable(
                    (By.XPATH,'//button[text()="Next"]'))).click()
            time.sleep(1.5)
            b = WebDriverWait(d,8).until(
                EC.element_to_be_clickable((By.XPATH,'//textarea[@placeholder]')))
            b.send_keys(message + Keys.ENTER)
            print(f"[Instagram] Sent -> @{username}: {message[:50]}")
            return {"success": True, "to": f"@{username}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def send_to_contact(self, name: str, message: str) -> dict:
        c = contacts_db.get(name)
        if c and c.get("instagram"):
            return self.send(c["instagram"], message)
        return {"success": False, "error": f"No Instagram username saved for '{name}'"}

ig = InstagramSender()


# ══════════════════════════════════════════════════════════
#  APP LAUNCHER
# ══════════════════════════════════════════════════════════

APP_MAP = {
    "chrome":"chrome", "google chrome":"chrome", "firefox":"firefox",
    "edge":"msedge", "brave":"brave",
    "notepad":"notepad", "word":"winword", "excel":"excel",
    "powerpoint":"powerpnt", "outlook":"outlook",
    "vs code":"code", "vscode":"code", "visual studio code":"code",
    "terminal":"cmd", "command prompt":"cmd", "powershell":"powershell",
    "calculator":"calc", "paint":"mspaint", "task manager":"taskmgr",
    "file explorer":"explorer", "settings":"ms-settings:",
    "spotify":"spotify", "vlc":"vlc", "telegram":"telegram",
    "discord":"discord", "teams":"teams", "zoom":"zoom", "skype":"skype",
    "steam":"steam", "camera":"camera:", "photos":"ms-photos:",
    "store":"ms-windows-store:", "maps":"bingmaps:",
}

SITE_MAP = {
    "google":"https://google.com", "youtube":"https://youtube.com",
    "netflix":"https://netflix.com", "hotstar":"https://hotstar.com",
    "prime":"https://primevideo.com", "instagram":"https://instagram.com",
    "facebook":"https://facebook.com", "twitter":"https://twitter.com",
    "x":"https://x.com", "github":"https://github.com",
    "reddit":"https://reddit.com", "amazon":"https://amazon.in",
    "flipkart":"https://flipkart.com", "gmail":"https://mail.google.com",
    "maps":"https://maps.google.com", "news":"https://news.google.com",
    "whatsapp":"https://web.whatsapp.com", "spotify":"https://open.spotify.com",
    "chatgpt":"https://chat.openai.com", "wikipedia":"https://wikipedia.org",
    "linkedin":"https://linkedin.com",
}

def launch_app(name: str) -> dict:
    n = name.lower().strip()
    cmd = APP_MAP.get(n)
    if not cmd:
        cmd = next((v for k,v in APP_MAP.items() if n in k or k in n), name)
    try:
        if platform.system() == "Windows":
            if cmd.endswith(":"):
                subprocess.Popen(["start", cmd], shell=True)
            else:
                subprocess.Popen([cmd], shell=True)
        else:
            subprocess.Popen([cmd])
        print(f"[Launcher] Started {name}")
        return {"success": True, "app": name}
    except Exception as e:
        return {"success": False, "error": str(e), "app": name}


# ══════════════════════════════════════════════════════════
#  SYSTEM CONTROL
# ══════════════════════════════════════════════════════════

class SystemCtrl:
    def vol_up(self, n=2):
        for _ in range(n): pyautogui.press("volumeup")

    def vol_down(self, n=2):
        for _ in range(n): pyautogui.press("volumedown")

    def mute(self):
        pyautogui.press("volumemute")

    def screenshot(self) -> str:
        p = os.path.expanduser(f"~/Desktop/jarvis_{int(time.time())}.png")
        pyautogui.screenshot(p); return p

    def lock(self):
        if platform.system() == "Windows":
            subprocess.run(["rundll32.exe","user32.dll,LockWorkStation"])

    def sleep(self):
        if platform.system() == "Windows":
            subprocess.run(["rundll32.exe","powrprof.dll,SetSuspendState","0,1,0"])

    def shutdown(self, delay=60):
        if platform.system() == "Windows":
            subprocess.run(["shutdown","/s","/t",str(delay)])

    def cancel_shutdown(self):
        if platform.system() == "Windows":
            subprocess.run(["shutdown","/a"])

sys_ctrl = SystemCtrl()


# ══════════════════════════════════════════════════════════
#  NLP COMMAND PARSER
# ══════════════════════════════════════════════════════════

class Parser:
    def parse(self, text: str) -> dict:
        t = text.lower().strip()

        # ── WhatsApp ──
        # "send whatsapp to Rahul saying I'll be late"
        # "whatsapp Priya come home"
        # "message Arjun on whatsapp: on my way"
        patterns_wa = [
            r"(?:send\s+)?whatsapp\s+(?:to\s+)?([a-zA-Z ]+?)\s+(?:saying|say|that|:|-|message)?\s*(.+)$",
            r"(?:send\s+)?(?:message|msg|text)\s+(?:to\s+)?([a-zA-Z ]+?)\s+(?:on\s+whatsapp|via\s+whatsapp)\s+(?:saying|say|that|:|-|message)?\s*(.+)$",
            r"(?:message|msg|text)\s+([a-zA-Z ]+?)\s+(?:saying|say|that|:|-)\s*(.+)$",
        ]
        for p in patterns_wa:
            m = re.search(p, t, re.I)
            if m:
                return {"action":"whatsapp",
                        "contact": m.group(1).strip().title(),
                        "message": m.group(2).strip()}

        # ── Instagram DM ──
        # "instagram dm john123 hello"
        # "send instagram message to @priya123 saying hi"
        patterns_ig = [
            r"(?:instagram|insta|ig)\s+(?:dm|message|msg)?\s+(?:to\s+)?@?([a-zA-Z0-9_.]+?)\s+(?:saying|say|that|:|-|message)?\s*(.+)$",
            r"(?:send\s+)?dm\s+(?:to\s+)?@?([a-zA-Z0-9_.]+?)\s+(?:saying|say|that|:|-|message)?\s*(.+)$",
        ]
        for p in patterns_ig:
            m = re.search(p, t, re.I)
            if m and any(w in t for w in ["instagram","insta","ig","dm"]):
                return {"action":"instagram",
                        "contact": m.group(1).strip(),
                        "message": m.group(2).strip()}

        # ── YouTube play (auto-clicks first video) ──
        m = re.search(r"play\s+(.+?)(?:\s+on\s+youtube)?$", t, re.I)
        if m and "play" in t:
            return {"action":"youtube_play", "query": m.group(1).strip()}

        # ── YouTube search ──
        m = re.search(r"(?:search|look).+?(?:on\s+)?youtube\s+(?:for\s+)?(.+)$", t, re.I)
        if m: return {"action":"youtube_search", "query": m.group(1).strip()}
        m = re.search(r"youtube\s+(?:search\s+)?(?:for\s+)?(.+)$", t, re.I)
        if m: return {"action":"youtube_search", "query": m.group(1).strip()}

        # ── Google search ──
        m = re.search(r"(?:search|google)\s+(?:for\s+)?(.+)$", t, re.I)
        if m and any(w in t for w in ["search","google"]):
            return {"action":"google", "query": m.group(1).strip()}

        # ── Maps / Directions ──
        m = re.search(r"(?:directions?|navigate|maps?|how to reach|take me to)\s+(?:to\s+)?(.+)$", t, re.I)
        if m: return {"action":"maps", "place": m.group(1).strip()}

        # ── Open URL (with domain) ──
        m = re.search(r"open\s+(?:website\s+)?(?:https?://)?([a-zA-Z0-9.\-_]+\.[a-zA-Z]{2,}[/\S]*)", t, re.I)
        if m:
            url = m.group(1)
            if not url.startswith("http"): url = "https://" + url
            return {"action":"open_url", "url": url}

        # ── Open named site or app ──
        m = re.search(r"open\s+([a-zA-Z0-9 ]+?)(?:\s+(?:please|now|for me))?$", t, re.I)
        if m:
            name = m.group(1).strip().lower()
            if name in SITE_MAP:
                return {"action":"open_url", "url": SITE_MAP[name]}
            return {"action":"open_app", "app": name}

        # ── Save contact ──
        # "save contact Rahul with number 9876543210"
        # "add contact Priya instagram priya_123"
        m = re.search(
            r"(?:save|add|create|new)\s+contact\s+([a-zA-Z ]+?)"
            r"(?:\s+(?:with\s+)?(?:number|phone|mobile|whatsapp))?"
            r"\s+([+\d\-\s]{7,}|@?[a-zA-Z0-9_.]+)$", t, re.I)
        if m:
            val = m.group(2).strip()
            if "@" in val or re.match(r"^[a-zA-Z]", val):
                return {"action":"save_contact","name":m.group(1).strip().title(),
                        "phone":"","instagram":val.lstrip("@")}
            return {"action":"save_contact","name":m.group(1).strip().title(),
                    "phone":re.sub(r"[\s\-]","",val),"instagram":""}

        # ── Screenshot ──
        if any(w in t for w in ["screenshot","screen shot","capture screen","take screenshot"]):
            return {"action":"screenshot"}

        # ── Volume ──
        if any(w in t for w in ["volume up","louder","increase volume","turn it up","turn up"]):
            return {"action":"vol_up","steps": 4 if any(w in t for w in ["lot","more","much"]) else 2}
        if any(w in t for w in ["volume down","quieter","lower volume","turn it down","turn down"]):
            return {"action":"vol_down","steps": 4 if any(w in t for w in ["lot","more","much"]) else 2}
        if any(w in t for w in ["mute","silence","shut up","quiet"]):
            return {"action":"mute"}

        # ── System ──
        if any(w in t for w in ["lock screen","lock the screen","lock computer","lock pc"]):
            return {"action":"lock"}
        if any(w in t for w in ["sleep mode","hibernate","go to sleep","put to sleep"]):
            return {"action":"sleep"}
        if "shutdown" in t or "shut down" in t:
            return {"action":"shutdown"}
        if "cancel shutdown" in t or "abort shutdown" in t:
            return {"action":"cancel_shutdown"}

        return {"action":"unknown"}


parser = Parser()


# ══════════════════════════════════════════════════════════
#  MASTER EXECUTOR
# ══════════════════════════════════════════════════════════

def execute_command(text: str) -> dict:
    """
    Main entry point called by FastAPI and TalkBack.
    Returns { action, success, speech, ...extras }
    """
    cmd = parser.parse(text)
    act = cmd.get("action","unknown")

    # ── Messaging ──
    if act == "whatsapp":
        contact = cmd["contact"]
        message = cmd["message"]
        result  = wa.send_to_contact(contact, message)
        ok      = result.get("success", False)
        return {
            "action": "whatsapp", "success": ok,
            "to": contact, "message": message,
            "speech": f"Message sent to {contact}." if ok
                      else f"Couldn't send to {contact}. {result.get('error','')}",
        }

    if act == "instagram":
        contact = cmd["contact"]
        message = cmd["message"]
        c       = contacts_db.get(contact)
        result  = (ig.send_to_contact(contact, message)
                   if c else ig.send(contact, message))
        ok      = result.get("success", False)
        return {
            "action": "instagram", "success": ok,
            "to": contact, "message": message,
            "speech": f"Instagram DM sent to {contact}." if ok
                      else f"Instagram DM failed. {result.get('error','')}",
        }

    # ── Web ──
    if act == "youtube_play":
        q = cmd["query"]
        browser.youtube_play(q)
        return {"action":"youtube_play","success":True,"speech":f"Playing {q} on YouTube."}

    if act == "youtube_search":
        q = cmd["query"]
        browser.youtube_search(q)
        return {"action":"youtube_search","success":True,"speech":f"Searching YouTube for {q}."}

    if act == "google":
        q = cmd["query"]
        browser.google(q)
        return {"action":"google","success":True,"speech":f"Searching Google for {q}."}

    if act == "maps":
        p = cmd["place"]
        browser.maps(p)
        return {"action":"maps","success":True,"speech":f"Opening maps for {p}."}

    if act == "open_url":
        u = cmd["url"]
        browser.open(u)
        return {"action":"open_url","success":True,"speech":f"Opening {u}."}

    if act == "open_app":
        a = cmd["app"]
        r = launch_app(a)
        return {"action":"open_app","success":r["success"],
                "speech": f"Opening {a}." if r["success"] else f"Couldn't find {a}."}

    # ── Contacts ──
    if act == "save_contact":
        n = cmd["name"]
        contacts_db.add(n, phone=cmd.get("phone",""), instagram=cmd.get("instagram",""))
        details = cmd.get("phone") or cmd.get("instagram","")
        return {"action":"save_contact","success":True,
                "speech": f"Saved {n} to your contacts." +
                          (f" Number: {details}." if cmd.get("phone") else f" Instagram: {details}." if details else "")}

    # ── System ──
    if act == "screenshot":
        p = sys_ctrl.screenshot()
        return {"action":"screenshot","success":True,
                "speech":"Screenshot saved to your desktop.","path":p}

    if act == "vol_up":
        sys_ctrl.vol_up(cmd.get("steps",2))
        return {"action":"vol_up","success":True,"speech":"Volume increased."}

    if act == "vol_down":
        sys_ctrl.vol_down(cmd.get("steps",2))
        return {"action":"vol_down","success":True,"speech":"Volume decreased."}

    if act == "mute":
        sys_ctrl.mute()
        return {"action":"mute","success":True,"speech":"Muted."}

    if act == "lock":
        sys_ctrl.lock()
        return {"action":"lock","success":True,"speech":"Screen locked."}

    if act == "sleep":
        sys_ctrl.sleep()
        return {"action":"sleep","success":True,"speech":"Going to sleep."}

    if act == "shutdown":
        sys_ctrl.shutdown()
        return {"action":"shutdown","success":True,
                "speech":"Shutting down in 60 seconds. Say cancel shutdown to abort."}

    if act == "cancel_shutdown":
        sys_ctrl.cancel_shutdown()
        return {"action":"cancel_shutdown","success":True,"speech":"Shutdown cancelled."}

    return {"action":"unknown","success":False,
            "speech":"I didn't understand that command. Try: send WhatsApp to Rahul saying hello."}
