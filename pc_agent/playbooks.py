# pc_agent/playbooks.py
"""
SMART PLAYBOOKS — Pre-built step sequences for common tasks.

Instead of asking LLava to plan from scratch every time,
playbooks give JARVIS instant reliable steps for known patterns.

Playbook matching is tried FIRST. If matched → fast & reliable.
If no match → fall back to full LLava planning (flexible).

Supports:
  amazon_buy       → open chrome → amazon → search → filter price → add to cart
  flipkart_buy     → open chrome → flipkart → search → filter → add to cart  
  instagram_dm     → open chrome → instagram → find user → message
  instagram_post   → open instagram → find post → like/comment
  whatsapp_send    → open chrome → web.whatsapp.com → find contact → send
  youtube_play     → open chrome → youtube → search → click first video
  google_search    → open chrome → google → search query
  photos_share     → open photos → select → share via whatsapp → pick contact
  photos_delete    → open photos → albums → select all → delete
  open_app         → open named app and wait
  gmail_send       → open chrome → gmail → compose → to → subject → body → send
  maps_search      → open chrome → maps → search location
  screenshot_share → take screenshot → share via whatsapp
"""

import re
from typing import Optional


def match(instruction: str) -> Optional[dict]:
    """Try to match instruction to a playbook. Returns match info or None."""
    low = instruction.lower().strip()
    for name, pb in _PB.items():
        for pat in pb["pats"]:
            m = re.search(pat, low, re.I)
            if m:
                return {"name": name, "pb": pb, "m": m, "grps": m.groups(), "raw": instruction}
    return None


def build_steps(hit: dict) -> list:
    """Build concrete steps from a matched playbook."""
    grps = hit["grps"]
    raw  = hit["raw"]
    low  = raw.lower()
    v    = hit["pb"]["vars"](grps, raw, low)
    return hit["pb"]["build"](v)


# ═══ STEP BUILDERS ═══════════════════════════════════════════

def _s(n, desc, action, **p):
    """Shorthand step creator."""
    return {"step_num": n, "desc": desc, "action": action, "params": p}


def _amazon(v):
    q, budget = v.get("q",""), v.get("budget","")
    steps = [
        _s(1,  "Open Chrome",                    "open_app",  app="chrome"),
        _s(2,  "Wait for Chrome",                "wait",      sec=2.5),
        _s(3,  "Go to Amazon India",             "navigate",  url="amazon.in"),
        _s(4,  "Wait for Amazon to load",        "wait",      sec=2.5),
        _s(5,  "Click Amazon search bar",        "click",     target="Amazon search bar at top of page"),
        _s(6,  f"Type: {q}",                     "type",      text=q),
        _s(7,  "Press Enter to search",          "press",     key="enter"),
        _s(8,  "Wait for search results",        "wait",      sec=2.0),
    ]
    if budget:
        steps += [
            _s(9,  "Click price filter dropdown",    "click",  target="price filter or high to low sort button"),
            _s(10, "Wait for filter to apply",        "wait",   sec=1.5),
        ]
    n = len(steps) + 1
    steps += [
        _s(n,   "Click first product",           "click",     target="first product image or title in search results"),
        _s(n+1, "Wait for product page",         "wait",      sec=2.0),
        _s(n+2, "Click Add to Cart button",      "click",     target="Add to Cart yellow button"),
        _s(n+3, "Wait for cart update",          "wait",      sec=1.5),
    ]
    return steps


def _flipkart(v):
    q, budget = v.get("q",""), v.get("budget","")
    return [
        _s(1,  "Open Chrome",                    "open_app",  app="chrome"),
        _s(2,  "Wait for Chrome",                "wait",      sec=2.5),
        _s(3,  "Go to Flipkart",                 "navigate",  url="flipkart.com"),
        _s(4,  "Wait for Flipkart",              "wait",      sec=2.5),
        _s(5,  "Click search bar",               "click",     target="Flipkart search bar at top"),
        _s(6,  f"Type: {q}",                     "type",      text=q),
        _s(7,  "Press Enter",                    "press",     key="enter"),
        _s(8,  "Wait for results",               "wait",      sec=2.0),
        _s(9,  "Click first product",            "click",     target="first product in search results"),
        _s(10, "Wait for product page",          "wait",      sec=2.0),
        _s(11, "Click Add to Cart",              "click",     target="Add to Cart button"),
        _s(12, "Wait",                           "wait",      sec=1.5),
    ]


def _insta_dm(v):
    user, msg = v.get("user",""), v.get("msg","")
    return [
        _s(1,  "Open Chrome",                    "open_app",  app="chrome"),
        _s(2,  "Wait",                           "wait",      sec=1.5),
        _s(3,  "Go to Instagram",                "navigate",  url="instagram.com"),
        _s(4,  "Wait for Instagram",             "wait",      sec=3.0),
        _s(5,  "Click Search in sidebar",        "click",     target="Search icon in left sidebar of Instagram"),
        _s(6,  "Wait for search to open",        "wait",      sec=1.0),
        _s(7,  f"Type username: {user}",         "type",      text=user),
        _s(8,  "Wait for results",               "wait",      sec=1.5),
        _s(9,  f"Click {user} in results",       "click",     target=f"{user} profile picture or username in search results list"),
        _s(10, "Wait for profile",               "wait",      sec=2.0),
        _s(11, "Click Message button",           "click",     target="Message button on Instagram profile page"),
        _s(12, "Wait for chat to open",          "wait",      sec=1.5),
        _s(13, "Click message input box",        "click",     target="message input box at the bottom of Instagram DM chat"),
        _s(14, f"Type message: {msg}",           "type",      text=msg),
        _s(15, "Press Enter to send",            "press",     key="enter"),
        _s(16, "Wait for send confirmation",     "wait",      sec=1.0),
    ]


def _whatsapp(v):
    contact, msg = v.get("contact",""), v.get("msg","")
    return [
        _s(1,  "Open Chrome",                    "open_app",  app="chrome"),
        _s(2,  "Wait",                           "wait",      sec=1.5),
        _s(3,  "Go to WhatsApp Web",             "navigate",  url="web.whatsapp.com"),
        _s(4,  "Wait for WhatsApp to load",      "wait",      sec=4.0),
        _s(5,  "Click search icon",              "click",     target="search icon or search contacts at top of WhatsApp left panel"),
        _s(6,  f"Type contact: {contact}",       "type",      text=contact),
        _s(7,  "Wait for results",               "wait",      sec=1.5),
        _s(8,  f"Click {contact} in list",       "click",     target=f"{contact} name in WhatsApp chat list search results"),
        _s(9,  "Click message input",            "click",     target="message input field at the bottom of WhatsApp chat"),
        _s(10, f"Type: {msg}",                   "type",      text=msg),
        _s(11, "Press Enter to send",            "press",     key="enter"),
        _s(12, "Wait",                           "wait",      sec=1.0),
    ]


def _youtube(v):
    q = v.get("q","")
    return [
        _s(1,  "Open Chrome",                    "open_app",  app="chrome"),
        _s(2,  "Wait",                           "wait",      sec=1.5),
        _s(3,  "Go to YouTube",                  "navigate",  url="youtube.com"),
        _s(4,  "Wait for YouTube",               "wait",      sec=2.0),
        _s(5,  "Click YouTube search bar",       "click",     target="YouTube search bar at top center"),
        _s(6,  f"Type: {q}",                     "type",      text=q),
        _s(7,  "Press Enter to search",          "press",     key="enter"),
        _s(8,  "Wait for results",               "wait",      sec=2.0),
        _s(9,  "Click first video",              "click",     target="first video thumbnail in YouTube search results"),
        _s(10, "Wait for video to load",         "wait",      sec=2.0),
    ]


def _google(v):
    q = v.get("q","")
    return [
        _s(1,  "Open Chrome",                    "open_app",  app="chrome"),
        _s(2,  "Wait",                           "wait",      sec=1.5),
        _s(3,  f"Search Google: {q}",            "navigate",  url=f"https://www.google.com/search?q={q.replace(' ', '+')}"),
        _s(4,  "Wait for results",               "wait",      sec=2.0),
    ]


def _photos_share(v):
    contact = v.get("contact","")
    return [
        _s(1,  "Open Photos app",                "open_app",  app="photos"),
        _s(2,  "Wait for Photos",                "wait",      sec=2.5),
        _s(3,  "Click latest photo",             "click",     target="most recent or first photo in Photos app"),
        _s(4,  "Wait",                           "wait",      sec=1.0),
        _s(5,  "Click Share button",             "click",     target="Share button or icon in Photos app toolbar"),
        _s(6,  "Wait for share options",         "wait",      sec=1.5),
        _s(7,  "Click WhatsApp in share menu",   "click",     target="WhatsApp option in share menu or share sheet"),
        _s(8,  "Wait for WhatsApp",              "wait",      sec=2.0),
        _s(9,  f"Search for {contact}",          "click",     target="search contacts or search field in WhatsApp share"),
        _s(10, f"Type {contact}",                "type",      text=contact),
        _s(11, "Wait for contact",               "wait",      sec=1.5),
        _s(12, f"Tap {contact}",                 "click",     target=f"{contact} in contacts list"),
        _s(13, "Click Send",                     "click",     target="Send button"),
        _s(14, "Wait",                           "wait",      sec=1.0),
    ]


def _photos_delete(v):
    album = v.get("album", "Screenshots")
    return [
        _s(1,  "Open Photos app",                "open_app",  app="photos"),
        _s(2,  "Wait for Photos",                "wait",      sec=2.5),
        _s(3,  f"Click {album} album",           "click",     target=f"{album} album in Photos app"),
        _s(4,  "Wait for album to open",         "wait",      sec=1.0),
        _s(5,  "Click Select or Select All",     "click",     target="Select or Select All button in Photos"),
        _s(6,  "Wait",                           "wait",      sec=0.5),
        _s(7,  "Click Delete button",            "click",     target="Delete or trash icon button"),
        _s(8,  "Wait for confirm dialog",        "wait",      sec=0.5),
        _s(9,  "Click Delete/OK to confirm",     "click",     target="Delete or OK or Move to Trash confirm button"),
        _s(10, "Wait",                           "wait",      sec=1.0),
    ]


def _gmail(v):
    to, subj, body = v.get("to",""), v.get("subj",""), v.get("body","")
    return [
        _s(1,  "Open Chrome",                    "open_app",  app="chrome"),
        _s(2,  "Wait",                           "wait",      sec=1.5),
        _s(3,  "Go to Gmail",                    "navigate",  url="mail.google.com"),
        _s(4,  "Wait for Gmail",                 "wait",      sec=3.0),
        _s(5,  "Click Compose button",           "click",     target="Compose button in Gmail"),
        _s(6,  "Wait for compose window",        "wait",      sec=1.0),
        _s(7,  "Click To field",                 "click",     target="To field in Gmail compose window"),
        _s(8,  f"Type recipient: {to}",          "type",      text=to),
        _s(9,  "Press Tab",                      "press",     key="tab"),
        _s(10, "Click Subject field",            "click",     target="Subject field in Gmail compose"),
        _s(11, f"Type subject: {subj}",          "type",      text=subj),
        _s(12, "Click body field",               "click",     target="email body text area in Gmail compose"),
        _s(13, f"Type email body",               "type",      text=body),
        _s(14, "Click Send button",              "click",     target="Send button in Gmail compose window"),
        _s(15, "Wait for send confirmation",     "wait",      sec=1.5),
    ]


def _open_only(v):
    app = v.get("app","")
    return [
        _s(1,  f"Open {app}",                    "open_app",  app=app),
        _s(2,  "Wait for app to load",           "wait",      sec=2.5),
    ]


# ═══ PATTERN REGISTRY ════════════════════════════════════════

def _extract_budget(s):
    m = re.search(r'(?:under|below|within|max|less than|upto)\s*(?:rs\.?|₹|inr)?\s*(\d+)', s, re.I)
    return m.group(1) if m else ""

def _extract_query(s, *keywords):
    for kw in keywords:
        m = re.search(rf'{kw}\s+(.+?)(?:\s+under|\s+below|\s+on\s|\s+from\s|$)', s, re.I)
        if m: return m.group(1).strip()
    return ""


_PB = {

    "amazon_buy": {
        "pats": [
            r"(?:open chrome.*)?(?:search|buy|order|book|get)\s+(.+?)\s+(?:on|in|from)\s+amazon",
            r"amazon.*(?:buy|order|search|book)\s+(.+?)(?:\s+under\s+(\d+))?$",
            r"(?:go to|open)\s+amazon.*(?:search|find|buy|order)\s+(.+)",
        ],
        "vars": lambda grps, raw, low: {
            "q":      _extract_query(low, "buy","search","order","book","get") or (grps[0] if grps else ""),
            "budget": _extract_budget(low),
        },
        "build": _amazon,
    },

    "flipkart_buy": {
        "pats": [
            r"(?:open chrome.*)?(?:search|buy|order|book)\s+(.+?)\s+(?:on|in|from)\s+flipkart",
            r"flipkart.*(?:buy|order|search)\s+(.+)",
        ],
        "vars": lambda grps, raw, low: {
            "q":      grps[0].strip() if grps else "",
            "budget": _extract_budget(low),
        },
        "build": _flipkart,
    },

    "instagram_dm": {
        "pats": [
            r"(?:open\s+)?insta(?:gram)?\s+(?:find|search|go to|open)\s+(.+?)\s+(?:and\s+)?(?:send|dm|message|msg)\s+(?:him|her|them)?\s*(.+)",
            r"(?:send|dm)\s+(?:a\s+)?(?:message|msg|dm)\s+(?:to\s+)?(.+?)\s+(?:on\s+)?insta(?:gram)?\s+(?:saying\s+)?(.+)",
            r"insta(?:gram)?\s+(.+?)\s+(?:send|msg|message|dm)\s+(.+)",
        ],
        "vars": lambda grps, raw, low: {
            "user": grps[0].strip() if len(grps)>0 else "",
            "msg":  grps[1].strip() if len(grps)>1 else "",
        },
        "build": _insta_dm,
    },

    "whatsapp_send": {
        "pats": [
            r"(?:send\s+)?whatsapp\s+(?:message\s+)?(?:to\s+)?(.+?)\s+(?:saying\s+|message\s+|msg\s+|[—\-]\s*)(.+)",
            r"(?:open\s+)?whatsapp\s+(?:and\s+)?(?:message|text|msg)\s+(.+?)[—\-:]\s*(.+)",
            r"message\s+(.+?)\s+on\s+whatsapp[:\s]+(.+)",
        ],
        "vars": lambda grps, raw, low: {
            "contact": grps[0].strip() if len(grps)>0 else "",
            "msg":     grps[1].strip() if len(grps)>1 else "",
        },
        "build": _whatsapp,
    },

    "youtube_play": {
        "pats": [
            r"(?:open|play|search)\s+(?:youtube\s+)?(.+?)\s+(?:on|in)\s+youtube",
            r"youtube\s+(?:play|search|open|find)\s+(.+)",
            r"play\s+(.+?)\s+(?:song|music|video)\s+(?:on youtube)?",
            r"open youtube\s+and\s+(?:play|search)\s+(.+)",
        ],
        "vars": lambda grps, raw, low: {"q": grps[0].strip() if grps else ""},
        "build": _youtube,
    },

    "google_search": {
        "pats": [
            r"(?:open chrome and\s+)?(?:google|search google for|search for)\s+(.+)",
            r"open chrome.*search\s+(.+?)(?:\s+on google)?$",
        ],
        "vars": lambda grps, raw, low: {"q": grps[0].strip() if grps else ""},
        "build": _google,
    },

    "photos_share": {
        "pats": [
            r"(?:open\s+)?(?:photos?|gallery|albums?)\s+(?:and\s+)?share\s+(?:latest\s+)?(?:photo|pic|image)?\s*(?:to|with)\s+(.+)",
            r"share\s+(?:latest\s+)?(?:photo|pic|image)\s+(?:to|with)\s+(.+?)\s+(?:on\s+)?whatsapp",
            r"send\s+(?:a\s+)?(?:photo|pic|image)\s+to\s+(.+?)\s+from\s+(?:gallery|photos?)",
        ],
        "vars": lambda grps, raw, low: {"contact": grps[0].strip() if grps else ""},
        "build": _photos_share,
    },

    "photos_delete": {
        "pats": [
            r"(?:open\s+)?(?:photos?|gallery|albums?)\s+(?:and\s+)?delete\s+(?:all\s+)?(?:the\s+)?(.+?)(?:\s+photos?|\s+pics?)?$",
            r"delete\s+(?:all\s+)?(.+?)\s+from\s+(?:photos?|gallery|albums?)",
            r"clear\s+(?:all\s+)?(.+?)\s+(?:photos?|pics?|images?)",
        ],
        "vars": lambda grps, raw, low: {"album": grps[0].strip().title() if grps else "Screenshots"},
        "build": _photos_delete,
    },

    "gmail_send": {
        "pats": [
            r"(?:send|compose|write)\s+(?:an?\s+)?email\s+to\s+(.+?)\s+(?:about|subject|re:)\s+(.+?)\s+(?:saying|body|content)?\s*(.+)",
            r"gmail\s+(?:send|compose)\s+to\s+(.+?)[:\s]+(.+?)[:\s]+(.+)",
        ],
        "vars": lambda grps, raw, low: {
            "to":   grps[0].strip() if len(grps)>0 else "",
            "subj": grps[1].strip() if len(grps)>1 else "",
            "body": grps[2].strip() if len(grps)>2 else "",
        },
        "build": _gmail,
    },

    "open_app": {
        "pats": [
            r"^(?:open|launch|start)\s+(chrome|firefox|browser|instagram|whatsapp|spotify|notepad|calculator|settings|photos?|gallery|files?|explorer|vscode|terminal|cmd|gmail|youtube)$",
        ],
        "vars": lambda grps, raw, low: {"app": grps[0].strip() if grps else ""},
        "build": _open_only,
    },
}
