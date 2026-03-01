from __future__ import annotations

import json
import os
import re
import subprocess
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote_plus

from automation.auto_reply import auto_reply_manager
from automation.messaging import messaging


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CONTACTS_FILE = DATA_DIR / "contacts.json"


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _is_phone_like(value: str) -> bool:
    return bool(re.match(r"^[+\d][\d\s\-()]{5,}$", value.strip()))


def _clean_phone(value: str) -> str:
    return re.sub(r"[^\d+]", "", value.strip())


def _looks_like_url(value: str) -> bool:
    value = value.strip().lower()
    return value.startswith("http://") or value.startswith("https://") or "." in value


def _looks_like_path(value: str) -> bool:
    value = value.strip()
    return bool(
        value.startswith("~")
        or value.startswith(".")
        or value.startswith("\\")
        or value.startswith("/")
        or re.match(r"^[a-zA-Z]:\\", value)
    )


class ContactsDB:
    def __init__(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._contacts: dict[str, dict[str, Any]] = {}
        self._reload()

    def _reload(self) -> None:
        if not CONTACTS_FILE.exists():
            self._contacts = {}
            return
        try:
            raw = CONTACTS_FILE.read_text(encoding="utf-8")
            self._contacts = json.loads(raw) if raw.strip() else {}
        except Exception:
            self._contacts = {}

    def _save(self) -> None:
        CONTACTS_FILE.write_text(json.dumps(self._contacts, indent=2), encoding="utf-8")

    def add(
        self,
        name: str,
        phone: str = "",
        whatsapp: str = "",
        instagram: str = "",
        email: str = "",
        notes: str = "",
    ) -> dict[str, Any]:
        self._reload()
        key = _normalize_name(name)
        contact = {
            "name": name.strip(),
            "phone": _clean_phone(phone) if phone else "",
            "whatsapp": _clean_phone(whatsapp) if whatsapp else "",
            "instagram": instagram.strip().lstrip("@"),
            "email": email.strip(),
            "notes": notes.strip(),
            "added_at": _now_iso(),
        }
        if not contact["whatsapp"] and contact["phone"]:
            contact["whatsapp"] = contact["phone"]
        self._contacts[key] = contact
        self._save()
        return contact

    def get(self, name: str) -> Optional[dict[str, Any]]:
        self._reload()
        key = _normalize_name(name)
        if key in self._contacts:
            return self._contacts[key]
        for k, v in self._contacts.items():
            if key in k or k in key:
                return v
        return None

    def delete(self, name: str) -> bool:
        self._reload()
        key = _normalize_name(name)
        if key not in self._contacts:
            return False
        del self._contacts[key]
        self._save()
        return True

    def list_all(self) -> list[dict[str, Any]]:
        self._reload()
        return sorted(self._contacts.values(), key=lambda c: str(c.get("name", "")).lower())

    def search(self, query: str) -> list[dict[str, Any]]:
        self._reload()
        q = _normalize_name(query)
        if not q:
            return self.list_all()
        return [
            c
            for c in self._contacts.values()
            if q in _normalize_name(str(c.get("name", "")))
            or q in str(c.get("phone", ""))
            or q in _normalize_name(str(c.get("instagram", "")))
        ]


class BrowserManager:
    def open(self, url: str) -> bool:
        value = url.strip()
        if not value:
            return False
        if not value.startswith("http://") and not value.startswith("https://"):
            value = f"https://{value}"
        try:
            if os.name == "nt":
                result = subprocess.run(
                    ["cmd", "/c", "start", "", value],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                return result.returncode == 0
            return bool(webbrowser.open(value))
        except Exception:
            return False

    def google(self, query: str) -> bool:
        return self.open(f"https://www.google.com/search?q={quote_plus(query)}")

    def youtube_search(self, query: str) -> bool:
        return self.open(f"https://www.youtube.com/results?search_query={quote_plus(query)}")

    def youtube_play(self, query: str) -> bool:
        return self.youtube_search(query)

    def maps(self, place: str) -> bool:
        return self.open(f"https://www.google.com/maps/search/{quote_plus(place)}")

    def whatsapp(self) -> bool:
        return self.open("https://web.whatsapp.com")

    def instagram(self) -> bool:
        return self.open("https://instagram.com")


class WhatsAppBridge:
    def send_by_number(self, phone: str, message: str) -> dict[str, Any]:
        target = _clean_phone(phone)
        if not target:
            return {"success": False, "error": "Invalid phone number"}
        ok = messaging.send_whatsapp(target, message)
        return {"success": bool(ok), "to": target, "error": messaging.last_error if not ok else ""}

    def send_by_name(self, contact_name: str, message: str) -> dict[str, Any]:
        # Name-only messaging is not reliably automatable without browser session scripting.
        return {
            "success": False,
            "to": contact_name.strip(),
            "error": "Contact number required. Save contact with WhatsApp number first.",
        }

    def send_to_contact(self, name_or_number: str, message: str) -> dict[str, Any]:
        value = name_or_number.strip()
        if _is_phone_like(value):
            return self.send_by_number(value, message)
        contact = contacts_db.get(value)
        if not contact:
            return {
                "success": False,
                "to": value,
                "error": "Contact not found. Use: add contact <name> whatsapp <number>",
            }
        target = str(contact.get("whatsapp") or contact.get("phone") or "").strip()
        if not _is_phone_like(target):
            return {
                "success": False,
                "to": contact.get("name", value),
                "error": "Saved contact has no WhatsApp number.",
            }
        return self.send_by_number(target, message)


class InstagramBridge:
    def send(self, username: str, message: str) -> dict[str, Any]:
        handle = username.strip().lstrip("@")
        if not handle:
            return {"success": False, "error": "Invalid Instagram username"}
        ok = messaging.send_instagram_dm(handle, message)
        return {"success": bool(ok), "to": handle, "error": messaging.last_error if not ok else ""}

    def send_to_contact(self, name_or_username: str, message: str) -> dict[str, Any]:
        value = name_or_username.strip()
        contact = contacts_db.get(value)
        if contact and contact.get("instagram"):
            return self.send(str(contact["instagram"]), message)
        return self.send(value, message)


APP_MAP = {
    "chrome": "chrome",
    "edge": "msedge",
    "firefox": "firefox",
    "notepad": "notepad",
    "calculator": "calc",
    "paint": "mspaint",
    "terminal": "cmd",
    "powershell": "powershell",
    "vscode": "code",
    "vs code": "code",
    "file explorer": "explorer",
    "explorer": "explorer",
    "task manager": "taskmgr",
}


PROCESS_MAP = {
    "chrome": "chrome.exe",
    "edge": "msedge.exe",
    "firefox": "firefox.exe",
    "notepad": "notepad.exe",
    "calculator": "calculator.exe",
    "paint": "mspaint.exe",
    "terminal": "WindowsTerminal.exe",
    "powershell": "powershell.exe",
    "vscode": "Code.exe",
    "vs code": "Code.exe",
    "file explorer": "explorer.exe",
    "explorer": "explorer.exe",
}


SITE_MAP = {
    "google": "https://google.com",
    "youtube": "https://youtube.com",
    "instagram": "https://instagram.com",
    "whatsapp": "https://web.whatsapp.com",
    "github": "https://github.com",
    "netflix": "https://netflix.com",
    "facebook": "https://facebook.com",
    "x": "https://x.com",
}


def launch_app(app_name: str) -> dict[str, Any]:
    name = app_name.strip().lower()
    target = APP_MAP.get(name, name)
    try:
        if os.name == "nt":
            subprocess.Popen(f'start "" "{target}"', shell=True)
        else:
            subprocess.Popen([target])
        return {"success": True, "app": app_name}
    except Exception as exc:
        return {"success": False, "app": app_name, "error": str(exc)}


def close_app(app_name: str) -> dict[str, Any]:
    name = app_name.strip().lower()
    image = PROCESS_MAP.get(name, name)
    if not image.lower().endswith(".exe"):
        image = f"{image}.exe"
    try:
        if os.name == "nt":
            result = subprocess.run(
                ["taskkill", "/IM", image, "/F"],
                check=False,
                capture_output=True,
                text=True,
            )
            ok = result.returncode == 0
            if ok:
                return {"success": True, "app": app_name, "killed": image}
            return {
                "success": False,
                "app": app_name,
                "error": (result.stderr or result.stdout or "Failed to close app").strip(),
            }
        return {"success": False, "app": app_name, "error": "Close app is only implemented for Windows"}
    except Exception as exc:
        return {"success": False, "app": app_name, "error": str(exc)}


class SystemCtrl:
    def _press_vkey(self, vkey: int) -> None:
        if os.name != "nt":
            return
        try:
            import ctypes

            user32 = ctypes.windll.user32
            user32.keybd_event(vkey, 0, 0, 0)
            user32.keybd_event(vkey, 0, 2, 0)
        except Exception:
            return

    def vol_up(self, steps: int = 2) -> None:
        for _ in range(max(1, steps)):
            self._press_vkey(0xAF)  # VK_VOLUME_UP

    def vol_down(self, steps: int = 2) -> None:
        for _ in range(max(1, steps)):
            self._press_vkey(0xAE)  # VK_VOLUME_DOWN

    def mute(self) -> None:
        self._press_vkey(0xAD)  # VK_VOLUME_MUTE

    def screenshot(self) -> str:
        out = Path.home() / "Desktop" / f"jarvis_{int(datetime.now().timestamp())}.png"
        try:
            import pyautogui  # type: ignore

            pyautogui.screenshot(str(out))
            return str(out)
        except Exception:
            pass

        if os.name != "nt":
            return ""

        # Fallback: native PowerShell screenshot.
        try:
            path = str(out).replace("'", "''")
            script = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "Add-Type -AssemblyName System.Drawing; "
                "$b=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds; "
                "$bmp=New-Object System.Drawing.Bitmap $b.Width,$b.Height; "
                "$g=[System.Drawing.Graphics]::FromImage($bmp); "
                "$g.CopyFromScreen($b.Location,[System.Drawing.Point]::Empty,$b.Size); "
                f"$bmp.Save('{path}',[System.Drawing.Imaging.ImageFormat]::Png); "
                "$g.Dispose(); $bmp.Dispose();"
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0 and out.exists():
                return str(out)
            return ""
        except Exception:
            return ""

    def lock(self) -> None:
        if os.name == "nt":
            subprocess.Popen(["rundll32.exe", "user32.dll,LockWorkStation"])

    def sleep(self) -> None:
        if os.name == "nt":
            subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])

    def shutdown(self, delay: int = 60) -> None:
        if os.name == "nt":
            subprocess.Popen(["shutdown", "/s", "/t", str(max(0, int(delay)))])

    def cancel_shutdown(self) -> None:
        if os.name == "nt":
            subprocess.Popen(["shutdown", "/a"])

    def open_path(self, path: str) -> dict[str, Any]:
        raw = path.strip().strip('"').strip("'")
        resolved = os.path.expandvars(os.path.expanduser(raw))
        if not os.path.exists(resolved):
            return {"success": False, "error": f"Path not found: {resolved}"}
        try:
            if os.name == "nt":
                os.startfile(resolved)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", resolved])
            return {"success": True, "path": resolved}
        except Exception as exc:
            return {"success": False, "error": str(exc), "path": resolved}


def supported_commands() -> list[str]:
    return [
        "open google.com",
        "open https://example.com",
        "search flutter firebase auth",
        "youtube lo-fi music",
        "login whatsapp",
        "login instagram",
        "open whatsapp",
        "open instagram",
        "send whatsapp to Rahul saying hello",
        "reply whatsapp to Rahul saying I am in a meeting now",
        "send whatsapp to +919876543210 saying hello",
        "send instagram to rahul_username saying hi",
        "reply instagram to rahul_username saying Can we connect tomorrow?",
        "add contact Rahul whatsapp 9876543210",
        "open vscode",
        "close chrome",
        "take screenshot",
        "volume up",
        "lock screen",
    ]


def _extract_two_groups(patterns: list[str], text: str) -> Optional[tuple[str, str]]:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip(), match.group(2).strip()
    return None


def execute_command(text: str) -> dict[str, Any]:
    query = text.strip()
    if not query:
        return {"action": "none", "success": False, "speech": "No command provided."}

    lowered = query.lower()

    if any(token in lowered for token in ["help automation", "automation help", "list automation commands"]):
        return {
            "action": "help",
            "success": True,
            "speech": "Available automation commands ready.",
            "examples": supported_commands(),
        }

    if lowered in {"login whatsapp", "whatsapp login", "connect whatsapp"}:
        ok = messaging.login("whatsapp")
        return {
            "action": "whatsapp_login",
            "success": ok,
            "speech": "WhatsApp login session ready."
            if ok
            else f"WhatsApp login failed: {messaging.last_error}",
        }

    if lowered in {"login instagram", "instagram login", "connect instagram"}:
        ok = messaging.login("instagram")
        return {
            "action": "instagram_login",
            "success": ok,
            "speech": "Instagram login session ready."
            if ok
            else f"Instagram login failed: {messaging.last_error}",
        }

    wa_auto_reply_match = _extract_two_groups(
        [
            r"(?:auto\s*reply|reply)\s+(?:on\s+)?whatsapp\s+(?:to\s+)?(.+?)\s+(?:saying|say|for|:)\s*(.+)$",
            r"(?:auto\s*reply|reply)\s+(.+?)\s+(?:on|via)\s+whatsapp\s+(?:saying|say|for|:)\s*(.+)$",
        ],
        query,
    )
    if wa_auto_reply_match:
        contact, incoming_message = wa_auto_reply_match
        generated = auto_reply_manager.generate_reply(
            incoming_message=incoming_message,
            platform="whatsapp",
            sender=contact,
        )
        if not generated.get("success"):
            return {
                "action": "whatsapp_auto_reply",
                "success": False,
                "speech": f"Could not generate auto reply: {generated.get('error', 'unknown error')}",
                **generated,
            }
        reply_text = str(generated.get("reply", "")).strip()
        result = wa.send_to_contact(contact, reply_text)
        return {
            "action": "whatsapp_auto_reply",
            "success": bool(result.get("success")),
            "speech": "WhatsApp auto reply sent."
            if result.get("success")
            else f"WhatsApp auto reply failed: {result.get('error', 'unknown error')}",
            "incoming_message": incoming_message,
            "generated_reply": reply_text,
            **result,
        }

    ig_auto_reply_match = _extract_two_groups(
        [
            r"(?:auto\s*reply|reply)\s+(?:on\s+)?(?:instagram|insta|ig)\s+(?:to\s+)?@?(.+?)\s+(?:saying|say|for|:)\s*(.+)$",
            r"(?:auto\s*reply|reply)\s+@?(.+?)\s+(?:on|via)\s+(?:instagram|insta|ig)\s+(?:saying|say|for|:)\s*(.+)$",
        ],
        query,
    )
    if ig_auto_reply_match:
        contact, incoming_message = ig_auto_reply_match
        generated = auto_reply_manager.generate_reply(
            incoming_message=incoming_message,
            platform="instagram",
            sender=contact,
        )
        if not generated.get("success"):
            return {
                "action": "instagram_auto_reply",
                "success": False,
                "speech": f"Could not generate auto reply: {generated.get('error', 'unknown error')}",
                **generated,
            }
        reply_text = str(generated.get("reply", "")).strip()
        result = ig.send_to_contact(contact, reply_text)
        return {
            "action": "instagram_auto_reply",
            "success": bool(result.get("success")),
            "speech": "Instagram auto reply sent."
            if result.get("success")
            else f"Instagram auto reply failed: {result.get('error', 'unknown error')}",
            "incoming_message": incoming_message,
            "generated_reply": reply_text,
            **result,
        }

    # WhatsApp / Instagram messaging
    wa_match = _extract_two_groups(
        [
            r"(?:send\s+)?whatsapp\s+(?:to\s+)?(.+?)\s+(?:saying|say|:)\s*(.+)$",
            r"(?:message|text)\s+(.+?)\s+(?:on\s+whatsapp|via\s+whatsapp)\s+(?:saying|say|:)\s*(.+)$",
        ],
        query,
    )
    if wa_match:
        contact, message = wa_match
        result = wa.send_to_contact(contact, message)
        return {
            "action": "whatsapp",
            "success": bool(result.get("success")),
            "speech": "WhatsApp message sent."
            if result.get("success")
            else f"WhatsApp failed: {result.get('error', 'unknown error')}",
            **result,
        }

    ig_match = _extract_two_groups(
        [
            r"(?:send\s+)?instagram(?:\s+(?:dm|message|msg))?\s+(?:to\s+)?@?(.+?)\s+(?:saying|say|:)\s*(.+)$",
            r"(?:send\s+)?(?:ig|insta)(?:\s+(?:dm|message|msg))?\s+(?:to\s+)?@?(.+?)\s+(?:saying|say|:)\s*(.+)$",
            r"(?:send\s+)?instagram\s+(?:to\s+)?@?(.+?)\s+(.+)$",
        ],
        query,
    )
    if ig_match:
        contact, message = ig_match
        result = ig.send_to_contact(contact, message)
        return {
            "action": "instagram",
            "success": bool(result.get("success")),
            "speech": "Instagram message sent."
            if result.get("success")
            else f"Instagram failed: {result.get('error', 'unknown error')}",
            **result,
        }

    # Add / save contact
    add_contact = re.search(
        r"(?:add|save|create)\s+contact\s+([a-zA-Z ]+?)(?:\s+(?:phone|number|whatsapp|instagram)\s+(.+))?$",
        query,
        re.IGNORECASE,
    )
    if add_contact:
        name = add_contact.group(1).strip().title()
        value = (add_contact.group(2) or "").strip()
        if value:
            if _is_phone_like(value):
                contact = contacts_db.add(name=name, phone=value, whatsapp=value)
            else:
                contact = contacts_db.add(name=name, instagram=value.lstrip("@"))
        else:
            contact = contacts_db.add(name=name)
        return {"action": "save_contact", "success": True, "speech": f"Saved contact {name}.", "contact": contact}

    # Open website shortcuts first
    if lowered in {"open whatsapp", "open whatsapp web", "whatsapp"}:
        ok = browser.whatsapp()
        return {
            "action": "open_whatsapp",
            "success": ok,
            "speech": "Opening WhatsApp Web." if ok else "Failed to open WhatsApp Web.",
        }

    if lowered in {"open instagram", "instagram"}:
        ok = browser.instagram()
        return {
            "action": "open_instagram",
            "success": ok,
            "speech": "Opening Instagram." if ok else "Failed to open Instagram.",
        }

    # Search commands
    yt_play = re.search(r"play\s+(.+?)(?:\s+on\s+youtube)?$", query, re.IGNORECASE)
    if yt_play:
        q = yt_play.group(1).strip()
        ok = browser.youtube_play(q)
        return {
            "action": "youtube_play",
            "success": ok,
            "speech": f"Playing {q} on YouTube." if ok else "Failed to open YouTube.",
        }

    yt_search = re.search(r"(?:search\s+youtube\s+for|youtube\s+search\s+for|youtube)\s+(.+)$", query, re.IGNORECASE)
    if yt_search:
        q = yt_search.group(1).strip()
        ok = browser.youtube_search(q)
        return {
            "action": "youtube_search",
            "success": ok,
            "speech": f"Searching YouTube for {q}." if ok else "Failed to open YouTube.",
        }

    google = re.search(r"(?:search|google)\s+(?:for\s+)?(.+)$", query, re.IGNORECASE)
    if google:
        q = google.group(1).strip()
        ok = browser.google(q)
        return {
            "action": "google",
            "success": ok,
            "speech": f"Searching Google for {q}." if ok else "Failed to open Google search.",
        }

    maps = re.search(r"(?:maps?|directions?|navigate|take me to)\s+(?:to\s+)?(.+)$", query, re.IGNORECASE)
    if maps:
        place = maps.group(1).strip()
        ok = browser.maps(place)
        return {
            "action": "maps",
            "success": ok,
            "speech": f"Opening maps for {place}." if ok else "Failed to open maps.",
        }

    # Close app
    close_name = re.search(r"(?:close|quit|exit)\s+(.+)$", query, re.IGNORECASE)
    if close_name:
        name = close_name.group(1).strip().lower()
        result = close_app(name)
        return {
            "action": "close_app",
            "success": bool(result.get("success")),
            "speech": f"Closed {name}." if result.get("success") else f"Could not close {name}.",
            **result,
        }

    # Open URL/path/app
    open_target = re.search(r"open\s+(.+)$", query, re.IGNORECASE)
    if open_target:
        name = open_target.group(1).strip()
        low = name.lower()
        if low in SITE_MAP:
            ok = browser.open(SITE_MAP[low])
            return {
                "action": "open_url",
                "success": ok,
                "speech": f"Opening {low}." if ok else f"Failed to open {low}.",
            }
        if _looks_like_path(name):
            opened = sys_ctrl.open_path(name)
            return {
                "action": "open_path",
                "success": bool(opened.get("success")),
                "speech": "Opened path." if opened.get("success") else str(opened.get("error", "Could not open path.")),
                **opened,
            }
        if _looks_like_url(name):
            ok = browser.open(name)
            return {
                "action": "open_url",
                "success": ok,
                "speech": f"Opening {name}." if ok else f"Failed to open {name}.",
            }
        launched = launch_app(name)
        return {
            "action": "open_app",
            "success": bool(launched.get("success")),
            "speech": f"Opening {name}." if launched.get("success") else f"Could not open {name}.",
            **launched,
        }

    # System actions
    if any(token in lowered for token in ["screenshot", "screen shot", "capture screen"]):
        path = sys_ctrl.screenshot()
        return {
            "action": "screenshot",
            "success": bool(path),
            "speech": "Screenshot captured." if path else "Screenshot failed.",
            "path": path,
        }

    if any(token in lowered for token in ["volume up", "turn up", "louder", "increase volume"]):
        sys_ctrl.vol_up()
        return {"action": "volume_up", "success": True, "speech": "Volume increased."}

    if any(token in lowered for token in ["volume down", "turn down", "quieter", "decrease volume"]):
        sys_ctrl.vol_down()
        return {"action": "volume_down", "success": True, "speech": "Volume decreased."}

    if "mute" in lowered:
        sys_ctrl.mute()
        return {"action": "mute", "success": True, "speech": "Muted."}

    if "lock" in lowered and "screen" in lowered:
        sys_ctrl.lock()
        return {"action": "lock", "success": True, "speech": "Screen locked."}

    if "sleep" in lowered:
        sys_ctrl.sleep()
        return {"action": "sleep", "success": True, "speech": "Going to sleep."}

    if "cancel shutdown" in lowered:
        sys_ctrl.cancel_shutdown()
        return {"action": "cancel_shutdown", "success": True, "speech": "Shutdown cancelled."}

    if "shutdown" in lowered or "shut down" in lowered:
        delay_match = re.search(r"shutdown\s+(?:in\s+)?(\d+)", lowered)
        delay = int(delay_match.group(1)) if delay_match else 60
        sys_ctrl.shutdown(delay)
        return {"action": "shutdown", "success": True, "speech": f"Shutting down in {delay} seconds."}

    return {
        "action": "unknown",
        "success": False,
        "speech": "I did not understand that command. Say 'help automation' for examples.",
        "examples": supported_commands()[:6],
    }


contacts_db = ContactsDB()
browser = BrowserManager()
wa = WhatsAppBridge()
ig = InstagramBridge()
sys_ctrl = SystemCtrl()
